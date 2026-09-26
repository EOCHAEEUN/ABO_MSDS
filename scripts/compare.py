# 저장 위치: <프로젝트 루트>/scripts/compare.py
"""두 라벨 뭉치를 대조한다.

  사람 vs 모델   → 모델 채점
  사람 vs 사람   → 이중 라벨링 일치율 (강덕우 ↔ 김건하)

둘은 같은 일이라 스크립트도 하나다.

사용법
  python scripts/compare.py --a 라벨링_어채은.csv,성분표_어채은.csv \
                            --b model_out.jsonl \
                            --name-a 사람 --name-b 모델 \
                            --out reports/

내는 것
  · 화면   : 문서별 요약 + 전체 지표
  · review.csv : 어긋난 항목만. 이것만 눈으로 보면 된다.
"""
import argparse, csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.compare_norm import (norm_loose, norm_cas, norm_ke, norm_amount,
                            cas_checkdigit, UNDECIDED)
from scripts.load_labels import load

SCALARS = [("product_name", "제품명"), ("signal_word", "신호어")]
SETS    = [("ghs", "GHS분류"), ("hazard", "유해위험문구")]


def f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def compare_docs(a, b, rows, tally):
    """한 문서를 대조하고 어긋난 항목을 rows 에 쌓는다."""
    doc = a["doc_id"]

    for key, label in SCALARS:
        va, vb = a.get(key) or "", b.get(key) or ""
        same = norm_loose(va) == norm_loose(vb)
        tally[label]["n"] += 1
        tally[label]["hit"] += int(same)
        if not same:
            rows.append([doc, label, "불일치", va, vb, ""])

    for key, label in SETS:
        ka = {norm_loose(x): x for x in a.get(key, [])}
        kb = {norm_loose(x): x for x in b.get(key, [])}
        tp = len(ka.keys() & kb.keys())
        for k in ka.keys() - kb.keys():
            rows.append([doc, label, "B에 없음", ka[k], "", ""])
        for k in kb.keys() - ka.keys():
            rows.append([doc, label, "A에 없음", "", kb[k], ""])
        t = tally[label]
        t["tp"] += tp
        t["fp"] += len(kb.keys() - ka.keys())
        t["fn"] += len(ka.keys() - kb.keys())

    ca = {norm_loose(c["name"]): c for c in a.get("components", []) if c.get("name")}
    cb = {norm_loose(c["name"]): c for c in b.get("components", []) if c.get("name")}
    t = tally["성분"]
    t["tp"] += len(ca.keys() & cb.keys())
    t["fp"] += len(cb.keys() - ca.keys())
    t["fn"] += len(ca.keys() - cb.keys())
    for k in ca.keys() - cb.keys():
        rows.append([doc, "성분", "B에 없음", ca[k]["name"], "", "성분 누락"])
    for k in cb.keys() - ca.keys():
        rows.append([doc, "성분", "A에 없음", "", cb[k]["name"], "성분 과생성"])

    for k in ca.keys() & cb.keys():
        for fld, label, fn in (("cas", "성분-CAS", norm_cas),
                               ("ke", "성분-KE", norm_ke),
                               ("amount", "성분-함유량", norm_amount)):
            va, vb = ca[k].get(fld) or "", cb[k].get(fld) or ""
            na, nb = fn(va), fn(vb)
            tally[label]["n"] += 1
            if na == nb:
                tally[label]["hit"] += 1
            else:
                rows.append([doc, label, "불일치", va, vb, f'성분 "{ca[k]["name"]}"'])
            if fld == "cas":
                for side, val, nval in (("A", va, na), ("B", vb, nb)):
                    if nval == UNDECIDED:
                        rows.append([doc, "성분-CAS", "미판정", va, vb,
                                     f'{side} 값이 "-"/빈칸 — 자료없음인지 해당없음인지 사람이 정할 것'])
                    elif cas_checkdigit(nval) is False:
                        rows.append([doc, "성분-CAS", "체크디짓 오류", va, vb,
                                     f'{side} 의 CAS 가 검증에 실패 — 오타 의심'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="기준 쪽. 'main.csv,comp.csv' 또는 'x.jsonl'")
    ap.add_argument("--b", required=True, help="비교 쪽. 같은 형식")
    ap.add_argument("--name-a", default="A")
    ap.add_argument("--name-b", default="B")
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()

    A, B = load(args.a), load(args.b)
    os.makedirs(args.out, exist_ok=True)

    only_a = sorted(set(A) - set(B))
    only_b = sorted(set(B) - set(A))
    both = sorted(set(A) & set(B))

    labels = ([l for _, l in SCALARS] + [l for _, l in SETS]
              + ["성분", "성분-CAS", "성분-KE", "성분-함유량"])
    tally = {l: {"n": 0, "hit": 0, "tp": 0, "fp": 0, "fn": 0} for l in labels}
    rows = []
    for doc in both:
        compare_docs(A[doc], B[doc], rows, tally)

    path = os.path.join(args.out, "review.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["문서ID", "항목", "구분", f"{args.name_a} 값", f"{args.name_b} 값", "비고"])
        w.writerows(sorted(rows, key=lambda r: (r[0], r[1])))

    print(f"\n대조: {args.name_a}  ↔  {args.name_b}")
    print(f"공통 문서 {len(both)}건" +
          (f" / {args.name_a}에만 {len(only_a)}건 {only_a}" if only_a else "") +
          (f" / {args.name_b}에만 {len(only_b)}건 {only_b}" if only_b else ""))
    print("-" * 66)
    print(f"{'항목':<14}{'지표':>34}")
    print("-" * 66)
    for l in labels:
        t = tally[l]
        if t["n"]:
            pct = 100 * t["hit"] / t["n"]
            print(f"{l:<14}일치 {t['hit']:>3}/{t['n']:<3}  ({pct:5.1f}%)")
        elif t["tp"] or t["fp"] or t["fn"]:
            p, r, s = f1(t["tp"], t["fp"], t["fn"])
            print(f"{l:<14}정밀도 {p:5.3f}  재현율 {r:5.3f}  F1 {s:5.3f}"
                  f"   (일치 {t['tp']} / 누락 {t['fn']} / 과생성 {t['fp']})")
        else:
            print(f"{l:<14}(값 없음)")
    print("-" * 66)
    print(f"검토할 항목 {len(rows)}건 → {path}")
    if not rows:
        print("어긋난 항목이 없습니다.")


if __name__ == "__main__":
    main()

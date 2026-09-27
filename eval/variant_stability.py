"""
val 형식 변형 안정성 비교 — report/decisions.md "평가 기준 사전 고정" B절 그대로

  python eval/variant_stability.py base_fs qlora_r1 qlora_r2

먼저 돌려 둘 것: eval/score.py --condition X --split val / --split val_var (문서별 상세 _score_detail.json)
보는 것 (문서별 → 조건별)
  1. 원본 문서 완전 정답 여부
  2. 변형 정답률: 변형 5개 중 문서 완전 정답 비율(기존 기준 · 확장 기준)
  3. 원본과 결과가 달라진 변형: 원본 정답→변형 오답 / 원본 오답→변형 정답
     원본 정답 문서의 변형 유지: 원본을 맞힌 문서의 변형 중 정답 비율(이것이 "유지율")
  5. 변형에서 새로 생긴 오류 유형(원본 출력에는 없던 것)
필드별 지표(4번)는 report/scores.csv의 split=val_var 행을 본다.
같은 6개 문서의 표기 변형이므로 독립된 30건 성능으로 해석하지 않는다.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("ghs", "hcode", "htext", "cas", "pair", "nocas")


def errors(d):
    """문서 상세 → 오류 유형 집합"""
    if d.get("parse_error"):
        return {"parse"}
    e = set()
    if d.get("schema_errors"):
        e.add("schema")
    if not d["product_name"]["ok"]:
        e.add("product_name")
    if not d["signal_word"]["ok"]:
        e.add("signal_word")
    e |= {k for k in ("ghs_status", "hazard_status") if k in d}
    e |= {k for k in FIELDS if d.get(k, "ok") != "ok"}
    if d.get("misplaced"):
        e |= {f"misplace_{k}" for k, v in d["misplaced"].items() if v}
    if d.get("fabricated"):
        e.add("fabricated")
    return e


def load(cond, split):
    return json.loads((ROOT / "outputs" / cond / split / "_score_detail.json").read_text(encoding="utf-8"))["docs"]


def main(conds):
    print("## 문서별 (원본 정답 / 변형 5개 중 정답 수)\n")
    rows, summary = defaultdict(dict), {}
    for c in conds:
        orig, var = load(c, "val"), load(c, "val_var")
        by_doc = defaultdict(list)
        for key, d in var.items():
            by_doc[key.split("__", 1)[0]].append((key.split("__", 1)[1], d))
        n_var = keep = keep_ext = lost = gained = kept_from_ok = n_from_ok = 0
        new_err = Counter()
        for doc in sorted(orig):
            o_ok, o_err = orig[doc]["exact"], errors(orig[doc])
            vs = by_doc[doc]
            ok = sum(d["exact"] for _, d in vs)
            rows[doc][c] = f"{'O' if o_ok else 'X'} / {ok}/{len(vs)}"
            n_var += len(vs)
            keep += ok
            keep_ext += sum(d["exact_ext"] for _, d in vs)
            if o_ok:
                n_from_ok += len(vs)
                kept_from_ok += ok
            lost += sum(o_ok and not d["exact"] for _, d in vs)
            gained += sum((not o_ok) and d["exact"] for _, d in vs)
            for name, d in vs:
                for e in errors(d) - o_err:
                    new_err[e] += 1
        summary[c] = {"orig_exact": sum(orig[d]["exact"] for d in orig), "n_orig": len(orig),
                      "orig_ext": sum(orig[d]["exact_ext"] for d in orig), "var_exact": keep, "var_ext": keep_ext,
                      "n_var": n_var, "kept": kept_from_ok, "n_kept": n_from_ok,
                      "lost": lost, "gained": gained, "new_err": new_err}

    print("| 문서 | " + " | ".join(conds) + " |")
    print("|---|" + "---|" * len(conds))
    for doc in sorted(rows):
        print(f"| {doc} | " + " | ".join(rows[doc].get(c, "") for c in conds) + " |")

    print("\n## 조건별\n")
    print("| 지표 | " + " | ".join(conds) + " |")
    print("|---|" + "---|" * len(conds))
    s = summary
    print("| 원본 완전 정답 (기존 기준) | " + " | ".join(f"{s[c]['orig_exact']}/{s[c]['n_orig']}" for c in conds) + " |")
    print("| 원본 완전 정답 (확장 기준) | " + " | ".join(f"{s[c]['orig_ext']}/{s[c]['n_orig']}" for c in conds) + " |")
    print("| 변형 정답률 (기존 기준) | " + " | ".join(f"{s[c]['var_exact']}/{s[c]['n_var']}" for c in conds) + " |")
    print("| 변형 정답률 (확장 기준) | " + " | ".join(f"{s[c]['var_ext']}/{s[c]['n_var']}" for c in conds) + " |")
    print("| 원본 정답 문서의 변형 유지 | " + " | ".join(f"{s[c]['kept']}/{s[c]['n_kept']}" for c in conds) + " |")
    print("| 원본 정답 → 변형 오답 | " + " | ".join(str(s[c]["lost"]) for c in conds) + " |")
    print("| 원본 오답 → 변형 정답 | " + " | ".join(str(s[c]["gained"]) for c in conds) + " |")
    print("\n## 변형에서 새로 생긴 오류 유형 (원본 출력에 없던 것, 변형 수)\n")
    for c in conds:
        items = ", ".join(f"{k} {v}" for k, v in s[c]["new_err"].most_common()) or "없음"
        print(f"- **{c}**: {items}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["base_fs", "qlora_r1", "qlora_r2"])

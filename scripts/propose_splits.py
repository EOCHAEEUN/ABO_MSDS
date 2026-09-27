"""신규 문서의 분할 배정 제안표를 만든다(결정적 균형 배정). splits.csv는 고치지 않는다.

규칙은 docs/plan_c.md 4절 5항. 요약:
  - 사전 메타데이터(doc_id · lang · form · manufacturer · split_group)만 읽는다. 정답 · 모델 결과와
    sources.csv의 집계 열(n_ingredients · signal_word 등)은 읽지 않는다.
  - 기존 배정은 그대로 둔다. splits.csv에 이미 있는 split_group의 신규 문서는 그 그룹을 따르고,
    신규 그룹만 균형 배정한다.
  - 신규 국문 그룹 순서: sha256(JSON [SEED, split_group]) 오름차순. SEED는 고정(바꾸면 decisions.md에 기록).
  - 그룹마다 들어갈 수 있는 분할 중 부족분 비율 (목표 − 현재) / 목표가 가장 큰 곳. 그룹이 남은 부족분 안에
    들어가는 분할을 먼저 보고, 동률이면 test2 > val > train.
  - 사람이 제안표에서 적격성 · 중복 · 규칙 위반을 확인한 뒤 splits.csv에 옮기고 check_splits.py로 검사한다.
    원하는 구성이 나올 때까지 SEED를 바꾸지 않는다.

  python scripts/propose_splits.py                        # data/sources.csv 중 splits.csv에 없는 문서
  python scripts/propose_splits.py --candidates new.csv   # 후보 목록을 따로 줄 때(같은 열 이름)
  python scripts/propose_splits.py --out proposal.csv
"""
import argparse
import collections
import csv
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.check_splits import exposure, norm_mfr  # noqa: E402

SEED = "C-2026-09-27"
META = ("doc_id", "lang", "form", "manufacturer", "split_group")
# 목표: plan_c 3절(train 총 약 50, val 15) + test2 주 분석 대상 40건을 현행 : 수입품 국문판 = 3 : 1로
TARGET = {"train": 50, "val": 15, "test2/현행": 30, "test2/수입품 국문판": 10}
PRIORITY = ("test2", "val", "train")          # 동률일 때 앞쪽. train은 기존 train 제조사로도 채울 수 있다
FORM_ORDER = ("현행", "수입품 국문판", "구서식")  # 그룹 주 서식이 동수일 때 앞쪽


def cell(split, form):
    return f"test2/{form}" if split == "test2" else split


def group_order(groups, seed=SEED):
    """[(sha256 앞 8자리, 그룹)] — 그룹 이름을 이어 붙이지 않도록 JSON 배열로 해시한다"""
    h = {g: hashlib.sha256(json.dumps([seed, g], ensure_ascii=False).encode("utf-8")).hexdigest() for g in groups}
    return sorted(((h[g][:8], g) for g in groups), key=lambda x: (h[x[1]], x[1]))


def follow(lang, splits_of_group):
    """이미 splits.csv에 있는 그룹의 신규 문서 → (제안, 근거, 확인). 균형 배정 대상이면 None"""
    ss = splits_of_group
    dev = sorted(ss & {"train", "val"})
    if lang == "ko":
        if "test2" in ss:
            return "test2", "기존 test2 그룹", "적격성 · 중복 · 개정판 확인"
        if dev:
            return dev[0], f"기존 {dev[0]} 그룹", ""
        if "test" in ss:
            return "excluded", "기존 test 그룹", "test는 동결, 다른 분할은 제조사 규칙 위반 → excluded 권고"
        if ss == {"val_en"}:
            return None                                   # 국문 신규: train · val 중 균형 배정(test2 불가)
        return "", f"기존 {'·'.join(sorted(ss))} 그룹", "사람 판단"
    if lang == "en":
        if dev:
            return "val_en", f"국문 {dev[0]} 그룹의 영문판", ""
        if "test2" in ss:
            return "excluded", "test2 그룹의 영문판", "excluded 권고: val_en에 두면 test2 서식이 개발에 노출"
        if "test" in ss:
            return "", "기존 test 그룹의 영문판", "사람 판단: val_en에 두면 test 제조사 서식이 개발에 노출"
        if "val_en" in ss:
            return "val_en", "기존 val_en 그룹", ""
        return "", f"기존 {'·'.join(sorted(ss))} 그룹", "사람 판단"
    return "excluded", f"범위 밖 언어({lang})", "확인"


def propose(existing, candidates, seen=None, seed=SEED):
    """existing: splits.csv 행, candidates: 신규 문서(META 열), seen: {doc_id: 노출 경로}.
    반환 (제안 행 목록, 배정 전 건수, 배정 후 건수)"""
    seen = seen or {}
    live = [r for r in existing if r["split"] != "excluded"]
    n = collections.Counter(cell(r["split"], r["form"]) for r in live if r["split"] in ("train", "val", "test2"))
    before = {c: n[c] for c in TARGET}
    grp_splits = collections.defaultdict(set)
    for r in existing:
        grp_splits[r["split_group"]].add(r["split"])
    mfr_at = collections.defaultdict(set)          # 제조사 → {(split_group, split)} (이번 제안 포함)
    for r in live:
        mfr_at[norm_mfr(r["manufacturer"])].add((r["split_group"], r["split"]))

    out = {}

    def put(r, split, why, check, order="-"):
        out[r["doc_id"]] = {"순서": order, **{k: r[k] for k in META}, "제안": split, "근거": why, "확인": check}
        if split in ("train", "val", "test2") and r["lang"] == "ko":
            n[cell(split, r["form"])] += 1
        if split and split != "excluded":
            mfr_at[norm_mfr(r["manufacturer"])].add((r["split_group"], split))

    # 1) 기존 그룹을 따르는 문서
    new_groups = collections.defaultdict(list)
    for r in candidates:
        if r["split_group"] in grp_splits:
            got = follow(r["lang"], grp_splits[r["split_group"]])
            if got is not None:
                if got[0] == "test2" and r["doc_id"] in seen:
                    got = ("", got[1], f"개발 노출({', '.join(seen[r['doc_id']])}) → test2 불가, 사람 판단")
                put(r, *got)
                continue
        new_groups[r["split_group"]].append(r)

    # 2) 신규 그룹: 영문만이면 val_en, 영문 외 외국어는 범위 밖, 국문이 있으면 균형 배정
    ko_groups = []
    for g, rs in new_groups.items():
        if not any(r["lang"] == "ko" for r in rs):
            for r in rs:
                put(r, *(("val_en", "신규 영문 그룹", "") if r["lang"] == "en" else follow(r["lang"], set())))
        else:
            ko_groups.append(g)

    for order, (h8, g) in enumerate(group_order(ko_groups, seed), 1):
        rs = new_groups[g]
        ko = [r for r in rs if r["lang"] == "ko"]
        forms = collections.Counter(r["form"] for r in ko)
        mfrs = {norm_mfr(r["manufacturer"]) for r in rs}
        used = {s for m in mfrs for gg, s in mfr_at[m] if gg != g}   # 다른 그룹에서 같은 제조사가 간 분할
        notes = []
        if used:
            notes.append(f"같은 제조사가 다른 그룹으로 {'·'.join(sorted(used))}에 있음 — split_group 확인")
        if g in grp_splits:
            notes.append(f"기존 {'·'.join(sorted(grp_splits[g]))} 그룹의 국문판 → test2 불가")
        if len(forms) > 1:
            notes.append("서식 혼합 그룹")

        allowed = []
        if not used & {"val", "test", "test2"}:
            allowed.append("train")
        if not used & {"train", "test2"}:
            allowed.append("val")
        exposed = [r["doc_id"] for r in rs if r["doc_id"] in seen]
        if exposed:
            notes.append(f"개발 노출 {','.join(exposed)} → test2 불가")
        elif not used and g not in grp_splits:
            allowed.append("test2")

        options = []
        for s in allowed:
            if s == "test2":
                main = [f for f in forms if cell("test2", f) in TARGET]
                if not main:
                    continue                              # 구서식만 있는 그룹은 test2 목표가 없다
                major = max(main, key=lambda f: (forms[f], -FORM_ORDER.index(f)))
                need = TARGET[cell(s, major)] - n[cell(s, major)]
                ratio = Fraction(max(need, 0), TARGET[cell(s, major)])
                fits = all(forms[f] <= TARGET[cell(s, f)] - n[cell(s, f)] for f in main)
                label = f"test2 {major}"
            else:
                need = TARGET[s] - n[s]
                ratio = Fraction(max(need, 0), TARGET[s])
                fits = len(ko) <= need
                label = s
            if need > 0:
                options.append((s, ratio, fits, label))

        why_opts = " > ".join(f"{lab} {float(r):.2f}" for _, r, _, lab in
                              sorted(options, key=lambda o: (-o[1], PRIORITY.index(o[0]))))
        pick = sorted(options, key=lambda o: (not o[2], -o[1], PRIORITY.index(o[0])))
        if pick:
            split = pick[0][0]
            if not pick[0][2]:
                notes.append("남은 부족분보다 큰 그룹 — 목표 초과")
            why = f"신규 그룹 {h8}, 부족분 비율 {why_opts}"
        else:
            split, why = "", f"신규 그룹 {h8}, 들어갈 수 있는 분할에 부족분 없음"
            notes.append("사람 판단")
        for r in ko:
            put(r, split, why, "; ".join(notes), order)
        for r in rs:
            if r["lang"] == "ko":
                continue
            if r["lang"] != "en":
                put(r, *follow(r["lang"], set()), order)
            elif split in ("train", "val"):
                put(r, "val_en", f"국문 {split} 그룹의 영문판", "", order)
            elif split == "test2":
                put(r, "excluded", "test2 그룹의 영문판",
                    "excluded 권고: val_en에 두면 test2 서식이 개발에 노출", order)
            else:
                put(r, "", "국문 배정 미정 그룹의 영문판", "사람 판단", order)

    rows = [out[r["doc_id"]] for r in candidates]
    return rows, before, {c: n[c] for c in TARGET}


def read_candidates(path, assigned):
    """META 열만 남긴다. splits.csv에 이미 있는 doc_id는 뺀다"""
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if rows and (missing := [k for k in META if k not in rows[0]]):
        sys.exit(f"{path}에 열이 없음: {missing}")
    out = [{k: (r.get(k) or "").strip() for k in META} for r in rows if r["doc_id"].strip() not in assigned]
    dup = [d for d, c in collections.Counter(r["doc_id"] for r in out).items() if c > 1]
    blank = [r["doc_id"] for r in out if not all(r[k] for k in META)]
    if dup or blank:
        sys.exit(f"후보 오류 — doc_id 중복 {dup}, 빈 칸(split_group · form 등) {blank}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--splits", default=str(ROOT / "data" / "splits.csv"))
    ap.add_argument("--candidates", default=str(ROOT / "data" / "sources.csv"))
    ap.add_argument("--out", help="제안표 CSV 경로(없으면 화면에만)")
    args = ap.parse_args()

    existing = list(csv.DictReader(open(args.splits, encoding="utf-8-sig")))
    cands = read_candidates(args.candidates, {r["doc_id"] for r in existing})
    if not cands:
        print("배정할 신규 문서 없음")
        return
    rows, before, after = propose(existing, cands, exposure())

    print(f"SEED {SEED} · 신규 {len(rows)}건")
    cols = ["순서", "doc_id", "split_group", "manufacturer", "lang", "form", "제안", "근거", "확인"]
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))
    print("\n건수(목표): " + ", ".join(f"{c} {before[c]} → {after[c]} ({TARGET[c]})" for c in TARGET))
    print("확인 칸이 빈 행도 사람이 적격성 · 중복을 확인한 뒤 splits.csv에 옮긴다.")
    if args.out:
        with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print("저장:", args.out)


if __name__ == "__main__":
    main()

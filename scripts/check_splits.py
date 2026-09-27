"""splits.csv가 분할 규칙(plan.md 3장 + docs/plan_c.md 3·4절)을 지키는지 검사한다.

  python scripts/check_splits.py            # 수집 중: 구조 규칙은 오류, 건수·비율은 경고
  python scripts/check_splits.py --final    # 분할 확정 전: 건수·비율까지 오류로

규칙
  [기존] 영문은 train·val 금지 / split_group이 train과 평가용(val·test·test2)에 걸치면 안 됨(노루 구서식 예외)
         val 제조사는 train과 불겹침 / test 제조사는 노루 예외만 허용 / 사전 검증 3건은 test·test2 금지
         기존 test는 동결: eval/test/ 파일 목록과 같아야 하고 국문 15 + 영문 5
  [C안]  test2 제조사·split_group은 다른 어느 분할(train·val·test·val_en)에도 없어야 함
         test2는 국문 회사 제품 MSDS(현행·수입품 국문판·구서식)만
         test2는 개발 노출 이력이 없어야 함: 정답이 data/labels/·eval/test/·eval/val_en/에 있거나,
         few-shot(eval/fewshot.json)이거나, 학습 JSONL(data/*.jsonl)·모델 출력(outputs/*/*/)에 나온 문서는 불가
         (splits.csv에서 split만 바꿔도 이력은 남으므로 파일 이름·doc_id로 본다. 내용은 열지 않음)
         few-shot 문서는 항상 train
         excluded: 범위 밖·결함으로 뺀 문서. note에 사유 필수, 다른 규칙에서는 없는 문서로 본다
         --final: test2 30~40건, 현행:수입품 국문판 = 3:1(±1건, 구서식 제외 건수 기준), val 15건, train 47~52건
         (구서식 20% 목표는 09-27 삭제 — 구서식은 모두 노루이고 노루가 train에 있음. report/decisions.md)
"""
import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLITS = {"train", "val", "test", "val_en", "test2", "excluded"}
EVAL = {"val", "test", "test2"}
TEST2_FORMS = ("현행", "수입품 국문판", "구서식")                # test2에 넣을 수 있는 서식
TEST2_RATIO = {"현행": 0.75, "수입품 국문판": 0.25}               # 구서식을 뺀 건수 기준 목표(원래 60:20)
PRECHECK_DOCS = ("KR-THERMO-001", "KR-NOROO-004", "KR-NOROO-005")  # 9/22 사전 검증에 Base를 돌린 문서


def norm_mfr(s):
    """제조사 표기 흔들림 제거: 공백·(주)·주식회사·대소문자"""
    return re.sub(r"\s+|\(주\)|㈜|주식회사", "", s or "").lower()


def exposure():
    """{doc_id: [개발 중 노출 경로]} — 파일 이름과 JSONL의 doc_id만 읽는다"""
    seen = collections.defaultdict(list)
    for d, where in (("data/labels", "train·val 정답"), ("eval/test", "기존 test 정답"), ("eval/val_en", "val_en 정답")):
        for f in (ROOT / d).glob("*.json"):
            seen[f.stem].append(where)
    fs = ROOT / "eval" / "fewshot.json"
    if fs.exists():
        for d in json.loads(fs.read_text(encoding="utf-8")).get("fewshot_doc_ids", []):
            seen[d].append("few-shot")
    for f in (ROOT / "data").glob("*.jsonl"):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                seen[json.loads(line)["doc_id"]].append(f"학습 JSONL {f.name}")
    for f in (ROOT / "outputs").glob("*/*/*.json"):
        if not f.name.startswith("_"):
            seen[f.stem.split("__")[0]].append(f"모델 출력 {f.parent.parent.name}/{f.parent.name}")
    return {d: sorted(set(w)) for d, w in seen.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=str(ROOT / "data" / "splits.csv"))
    ap.add_argument("--final", action="store_true", help="건수·비율 미달도 오류로(분할 확정 전에 실행)")
    ap.add_argument("--sources", default=str(ROOT / "data" / "sources.csv"))
    args = ap.parse_args()

    all_rows = list(csv.DictReader(open(args.path, encoding="utf-8-sig")))
    excluded = [r for r in all_rows if r["split"] == "excluded"]
    rows = [r for r in all_rows if r["split"] != "excluded"]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["split"]].append(r)
    err, warn = [], []
    goal = err if args.final else warn

    # ---- 형식
    ids = collections.Counter(r["doc_id"] for r in all_rows)
    err += [f"doc_id 중복: {d}" for d, n in ids.items() if n > 1]
    err += [f"excluded {r['doc_id']}: note에 제외 사유가 없음" for r in excluded if not (r.get("note") or "").strip()]
    err += [f"{r['doc_id']}: 알 수 없는 split '{r['split']}'" for r in rows if r["split"] not in SPLITS]

    # ---- [기존] 언어
    for s in ("train", "val", "test2"):
        err += [f"{r['doc_id']}: 영문은 {s}에 들어갈 수 없음" for r in by[s] if r["lang"] != "ko"]

    # ---- [기존] split_group이 train과 평가용에 걸치면 안 됨 (예외: 노루 구서식 train 2 / test 3)
    grp = collections.defaultdict(set)
    for r in rows:
        grp[r["split_group"]].add(r["split"])
    for g, ss in grp.items():
        both = ss & EVAL
        if "train" in ss and both and not (g == "NOROO" and both == {"test"}):
            err.append(f"split_group {g}가 train과 {sorted(both)}에 걸침")
        if len(both) > 1:
            err.append(f"split_group {g}가 평가용 여러 분할 {sorted(both)}에 걸침")

    # ---- [기존] 제조사
    train_mfr = {norm_mfr(r["manufacturer"]) for r in by["train"]}
    err += [f"val {r['doc_id']} 제조사가 train과 겹침" for r in by["val"] if norm_mfr(r["manufacturer"]) in train_mfr]
    err += [f"test {r['doc_id']} 제조사가 train과 겹침" for r in by["test"]
            if norm_mfr(r["manufacturer"]) in train_mfr and r["split_group"] != "NOROO"]
    err += [f"{d}는 사전 검증 문서라 {r['split']} 불가" for d in PRECHECK_DOCS for r in rows
            if r["doc_id"] == d and r["split"] in ("test", "test2")]

    # ---- [기존] test 동결: 노출 이력이 있는 평가셋이라 구성을 바꾸지 않는다(파일 이름만 본다, 내용은 열지 않음)
    test_files = {p.stem for p in (ROOT / "eval" / "test").glob("*.json")}
    test_ids = {r["doc_id"] for r in by["test"]}
    if test_ids != test_files:
        err.append(f"splits의 test와 eval/test/ 파일 목록이 다름: splits에만 {sorted(test_ids - test_files)}, "
                   f"파일에만 {sorted(test_files - test_ids)}")
    ko_test = [r for r in by["test"] if r["lang"] == "ko"]
    if len(ko_test) != 15 or len(by["test"]) - len(ko_test) != 5:
        err.append("기존 test는 국문 15 + 영문 5로 동결")

    # ---- [C안] test2
    other_mfr = {norm_mfr(r["manufacturer"]) for r in rows if r["split"] != "test2"}
    other_grp = {r["split_group"] for r in rows if r["split"] != "test2"}
    for r in by["test2"]:
        if norm_mfr(r["manufacturer"]) in other_mfr:
            err.append(f"test2 {r['doc_id']} 제조사({r['manufacturer']})가 다른 분할에 있음")
        if r["split_group"] in other_grp:
            err.append(f"test2 {r['doc_id']} split_group({r['split_group']})이 다른 분할에 있음")
        if r["form"] not in TEST2_FORMS:
            err.append(f"test2 {r['doc_id']} 서식 '{r['form']}'은 test2 대상이 아님({'/'.join(TEST2_FORMS)})")

    # ---- [C안] test2 노출 이력 · few-shot은 train
    seen = exposure()
    for r in by["test2"]:
        if r["doc_id"] in seen:
            err.append(f"test2 {r['doc_id']}는 개발 중 노출됨: {', '.join(seen[r['doc_id']])}")
    split_of = {r["doc_id"]: r["split"] for r in all_rows}
    err += [f"few-shot {d}가 {split_of[d]}에 있음(train만 가능)" for d, w in seen.items()
            if "few-shot" in w and d in split_of and split_of[d] != "train"]

    # ---- [C안] 건수·비율 (수집 중에는 경고)
    n2 = len(by["test2"])
    if not 30 <= n2 <= 40:
        goal.append(f"test2 {n2}건 — 목표 30~40건")
    forms = collections.Counter(r["form"] for r in by["test2"])
    base = n2 - forms.get("구서식", 0)
    if base:
        for f, share in TEST2_RATIO.items():
            want = round(base * share)
            if abs(forms.get(f, 0) - want) > 1:
                goal.append(f"test2 {f} {forms.get(f, 0)}건 — 구서식 뺀 {base}건 기준 목표 {want}건(3:1, ±1)")
    if len(by["val"]) != 15:
        goal.append(f"val {len(by['val'])}건 — 목표 15건(기존 6 + 9)")
    if not 47 <= len(by["train"]) <= 52:
        goal.append(f"train {len(by['train'])}건 — 목표 47~52건(기존 22 + 25~30)")

    # ---- sources.csv 대응 (수집 중에는 한쪽에만 있을 수 있음)
    src_path = Path(args.sources)
    if src_path.exists():
        src = {r["doc_id"] for r in csv.DictReader(open(src_path, encoding="utf-8-sig"))}
        if only := sorted(ids.keys() - src):
            err.append(f"sources.csv에 없는 doc_id: {only}")
        if only := sorted(src - ids.keys()):
            goal.append(f"splits.csv에 아직 배정 안 된 문서: {only}")

    print("건수:", {s: len(by[s]) for s in sorted(by)} | ({"excluded": len(excluded)} if excluded else {}))
    if by["test2"]:
        print("test2 서식:", dict(collections.Counter(r["form"] for r in by["test2"])))
    for w in warn:
        print("[경고]", w)
    print("\n".join(f"[오류] {e}" for e in err) if err else "규칙 위반 없음")
    sys.exit(1 if err else 0)


if __name__ == "__main__":
    main()

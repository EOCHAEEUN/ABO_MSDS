"""splits.csv가 재시작 분할 규칙(docs/plan.md 3.2)을 지키는지 검사한다.

  python3 scripts/check_splits.py                                  # 규칙만
  python3 scripts/check_splits.py --labels data/labels             # + 정답 파일 누락을 경고
  python3 scripts/check_splits.py --labels data/labels --final     # split-frozen 직전: 누락도 위반

규칙
- split은 train · val · val_en만. test는 저장소 밖에 두므로 splits.csv에 넣지 않는다.
- doc_id 중복 없음, 형식 KR|EN-약칭-번호.
- 영문은 train · val에 넣지 않는다(학습 · few-shot · 조건 선택은 국문).
- 같은 split_group · 같은 제조사가 train과 val에 걸치지 않는다.
- val에 수입품 국문판이 1건 이상 있다. (구서식은 전부 노루 계열이라 val에 넣지 않음 — report/decisions.md)
- eval/fewshot.json의 예시는 train 문서다.
"""
import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = {"train", "val", "val_en"}
DOC_ID = re.compile(r"(KR|EN)-[A-Z0-9]+-\d{3}")

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("path", nargs="?", default=str(ROOT / "data" / "splits.csv"))
ap.add_argument("--labels", help="정답 폴더. 주면 train · val 문서의 {doc_id}.json이 있는지 본다")
ap.add_argument("--final", action="store_true", help="정답 누락도 위반으로 본다(split-frozen 직전, --labels 필요)")
ap.add_argument("--fewshot", default=str(ROOT / "eval" / "fewshot.json"))
args = ap.parse_args()
if args.final and not args.labels:
    ap.error("--final에는 --labels가 필요함")

rows = list(csv.DictReader(open(args.path, encoding="utf-8-sig", newline="")))
by = collections.defaultdict(list)
for r in rows:
    by[r["split"]].append(r)
err, warn = [], []

for d, n in collections.Counter(r["doc_id"] for r in rows).items():
    if n > 1:
        err.append(f"doc_id 중복: {d}")
for r in rows:
    if not DOC_ID.fullmatch(r["doc_id"]):
        err.append(f"doc_id 형식 오류: {r['doc_id']}")
    if r["split"] not in ALLOWED:
        err.append(f"{r['doc_id']}: split '{r['split']}'은 쓸 수 없음(train · val · val_en만, test는 저장소 밖)")

for s in ("train", "val"):
    for r in by[s]:
        if r["lang"] != "ko":
            err.append(f"{r['doc_id']}: 영문은 {s}에 넣지 않음")

for key, label in (("split_group", "split_group"), ("manufacturer", "제조사")):
    sides = collections.defaultdict(set)
    for r in by["train"] + by["val"]:
        sides[r[key]].add(r["split"])
    for k, ss in sorted(sides.items()):
        if len(ss) > 1:
            err.append(f"{label} '{k}'가 train과 val에 걸침")

if not any(r["form"] == "수입품 국문판" for r in by["val"]):
    err.append("val에 수입품 국문판이 없음")

fs_path = Path(args.fewshot)
fewshot = json.loads(fs_path.read_text(encoding="utf-8")).get("fewshot_doc_ids", []) if fs_path.exists() else []
train_ids = {r["doc_id"] for r in by["train"]}
for d in fewshot:
    if d not in train_ids:
        err.append(f"few-shot 예시 {d}가 train 문서가 아님")

if args.labels:
    missing = [r["doc_id"] for r in by["train"] + by["val"] if not (Path(args.labels) / f"{r['doc_id']}.json").exists()]
    if missing:
        (err if args.final else warn).append(f"정답 파일 없음 {len(missing)}건({args.labels}): {missing}")

print("건수:", {s: len(v) for s, v in by.items()})
for s in ("train", "val"):
    print(f"{s} 서식:", dict(collections.Counter(r["form"] for r in by[s])),
          f"· 그룹 {len({r['split_group'] for r in by[s]})}개")
print("few-shot:", fewshot or "미정")
for w in warn:
    print("[경고]", w)
print("\n".join(err) if err else "규칙 위반 없음")
sys.exit(1 if err else 0)

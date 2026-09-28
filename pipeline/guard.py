"""
[강덕우] 데이터 용도 검사 — 학습 · 증강 · few-shot 스크립트가 시작할 때 부른다.

data/splits.csv가 데이터 용도의 유일한 기준이다(CLAUDE.md). 사람이 조심하는 대신 코드가 멈춘다.
  splits = load_splits(path)
  require_splits(doc_ids, {"train"}, splits, who="train.jsonl")   # 하나라도 벗어나면 GuardError
  refuse_sealed(path, ...)                                        # test 봉인 경로면 GuardError
"""
import csv
from pathlib import Path

# test 자료는 저장소 밖에 있어야 하지만, 실수로 들어온 경로도 열기 전에 막는다
SEALED_PARTS = ("sealed", "eval/test", "eval\\test")


class GuardError(RuntimeError):
    pass


def load_splits(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    splits = {}
    for r in rows:
        if r["doc_id"] in splits:
            raise GuardError(f"splits.csv에 doc_id 중복: {r['doc_id']}")
        splits[r["doc_id"]] = r
    return splits


def require_splits(doc_ids, allowed, splits, who):
    """doc_ids가 모두 splits.csv에 있고 split이 allowed 안에 있어야 한다."""
    bad = sorted({d for d in doc_ids if d not in splits or splits[d]["split"] not in allowed})
    if bad:
        detail = ", ".join(f"{d}({splits[d]['split'] if d in splits else 'splits.csv에 없음'})" for d in bad)
        raise GuardError(f"{who}: 허용 split {sorted(allowed)} 밖의 문서 {len(bad)}건 — {detail}")


def refuse_sealed(*paths):
    for p in paths:
        s = Path(p).resolve().as_posix().lower()
        if any(part.replace("\\", "/") in s for part in SEALED_PARTS):
            raise GuardError(f"test 봉인 경로는 개발 스크립트가 열지 않는다: {p}")

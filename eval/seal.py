"""
[양세윤 작성 · 어채은 실행]
--write : eval/test/ 해시 → report/test_manifest.csv
--verify: manifest와 현재 파일 대조

해시는 파일 바이트 그대로의 sha256이다(.gitattributes가 *.json 줄바꿈을 LF로 고정).
infer.py(--split test)와 score.py(--split test)는 verify()가 통과해야만 돈다.

  python eval/seal.py --write      # 2일차 17:30, Test 정답 확정 직후 1회
  python eval/seal.py --verify
"""
import argparse
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = ROOT / "eval" / "test"
MANIFEST = ROOT / "report" / "test_manifest.csv"
SPLITS_CSV = ROOT / "data" / "splits.csv"


def current_hashes():
    return {p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(TEST_DIR.glob("*.json"))}


def read_manifest():
    if not MANIFEST.exists():
        return {}
    with open(MANIFEST, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r["sha256"] for r in csv.DictReader(f) if r.get("doc_id")}


def verify():
    """(통과 여부, 메시지)"""
    saved = read_manifest()
    if not saved:
        return False, "report/test_manifest.csv가 비어 있음 — 아직 봉인 전이다(eval/seal.py --write)"
    now = current_hashes()
    problems = []
    if missing := sorted(set(saved) - set(now)):
        problems.append(f"없어진 파일 {missing}")
    if extra := sorted(set(now) - set(saved)):
        problems.append(f"봉인 뒤 추가된 파일 {extra}")
    if changed := sorted(d for d in set(saved) & set(now) if saved[d] != now[d]):
        problems.append(f"봉인 뒤 수정된 파일 {changed}")
    if problems:
        return False, "; ".join(problems)
    return True, f"봉인 대조 통과 ({len(now)}건)"


def write(force=False):
    if read_manifest() and not force:
        sys.exit("이미 봉인돼 있음. 다시 봉인하려면 사유를 report/decisions.md에 적고 --force")
    with open(SPLITS_CSV, encoding="utf-8-sig", newline="") as f:
        expected = {r["doc_id"] for r in csv.DictReader(f) if r["split"] == "test"}
    now = current_hashes()
    if set(now) != expected:
        sys.exit(f"eval/test/ 파일과 splits.csv의 test가 다름: "
                 f"파일에만 {sorted(set(now) - expected)}, splits에만 {sorted(expected - set(now))}")
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["doc_id", "sha256"])
        for doc_id in sorted(now):
            w.writerow([doc_id, now[doc_id]])
    print(f"봉인 완료: {len(now)}건 → {MANIFEST.relative_to(ROOT)}  (다음: git tag test-sealed)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    ap.add_argument("--force", action="store_true", help="기존 봉인 덮어쓰기(비상용)")
    args = ap.parse_args()
    if args.write:
        write(args.force)
    else:
        ok, msg = verify()
        print(("OK  " if ok else "FAIL  ") + msg)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
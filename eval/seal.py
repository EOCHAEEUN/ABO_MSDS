"""
[양세윤 작성 · 어채은 실행] + C안 test2 확장(2026-09-27)

기존 test (동작 그대로)
  --write : eval/test/ 정답 해시 → report/test_manifest.csv
  --verify: manifest와 현재 파일 대조

test2 (docs/plan_c.md 4·7절) — 두 단계로 봉인한다
  1단계 --split test2 --write-docs : 분할 직후·라벨링 전. test2 문서 목록 + 원본 PDF 해시
                                     → report/test2_docs_manifest.csv  ("어떤 문서가 test2인지"를 고정)
  2단계 --split test2 --write      : 2차 검수 뒤. 정답(eval/test2/) 해시 + 모델 입력 텍스트(data/text/) 해시
                                     + 추출 상태(_cut_log.csv의 status) → report/test2_manifest.csv
                                     (결과를 보고 정답·입력을 고치지 못하게. 추출 상태는 추론을 할지 말지 정하므로 함께 고정)
                                     텍스트가 없는 문서는 _cut_log.csv에 실패 기록이 있어야 하고(평가 분모에 남음),
                                     텍스트가 있는 문서는 SUCCESS여야 한다(있는 입력을 추론에서 건너뛰지 않게)
  --split test2 --verify           : 두 manifest를 모두 대조. 1단계 목록 · 2단계 목록 · 현재 splits.csv의 test2가 같아야 함

해시는 파일 바이트 그대로의 sha256이다(.gitattributes가 *.json 줄바꿈을 LF로 고정).
infer.py·score.py는 --split test / test2 에서 verify()가 통과해야만 돈다.
이 스크립트는 파일 내용을 읽어 해시만 계산하고, 정답 값을 출력하지 않는다.

  python eval/seal.py --write                          # 기존 test
  python eval/seal.py --split test2 --write-docs       # test2 1단계
  python eval/seal.py --split test2 --write            # test2 2단계
  python eval/seal.py --split test2 --verify
"""
import argparse
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLITS_CSV = ROOT / "data" / "splits.csv"
SOURCES_CSV = ROOT / "data" / "sources.csv"
RAW_DIR = ROOT / "data" / "raw"
TEXT_DIR = ROOT / "data" / "text"

TEST_DIR = ROOT / "eval" / "test"
MANIFEST = ROOT / "report" / "test_manifest.csv"
TEST2_DIR = ROOT / "eval" / "test2"
TEST2_DOCS = ROOT / "report" / "test2_docs_manifest.csv"
TEST2_MANIFEST = ROOT / "report" / "test2_manifest.csv"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_ids(split):
    with open(SPLITS_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"] for r in csv.DictReader(f) if r["split"] == split}


def read_csv(path, key="doc_id"):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r[key]: r for r in csv.DictReader(f) if r.get(key)}


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def diff(saved, now, what):
    """두 {doc_id: 해시} 비교 → 문제 목록"""
    problems = []
    if missing := sorted(set(saved) - set(now)):
        problems.append(f"{what}: 없어진 문서 {missing}")
    if extra := sorted(set(now) - set(saved)):
        problems.append(f"{what}: 봉인 뒤 추가된 문서 {extra}")
    if changed := sorted(d for d in set(saved) & set(now) if saved[d] != now[d]):
        problems.append(f"{what}: 봉인 뒤 바뀐 문서 {changed}")
    return problems


# ---------------------------------------------------------------- 기존 test
def current_hashes():
    return {p.stem: sha(p) for p in sorted(TEST_DIR.glob("*.json"))}


def read_manifest():
    return {d: r["sha256"] for d, r in read_csv(MANIFEST).items()}


def _verify_test():
    saved = read_manifest()
    if not saved:
        return False, "report/test_manifest.csv가 비어 있음 — 아직 봉인 전이다(eval/seal.py --write)"
    problems = diff(saved, current_hashes(), "정답")
    if problems:
        return False, "; ".join(problems)
    return True, f"봉인 대조 통과 ({len(saved)}건)"


def _write_test(force):
    if read_manifest() and not force:
        sys.exit("이미 봉인돼 있음. 다시 봉인하려면 사유를 report/decisions.md에 적고 --force")
    expected = split_ids("test")
    now = current_hashes()
    if set(now) != expected:
        sys.exit(f"eval/test/ 파일과 splits.csv의 test가 다름: "
                 f"파일에만 {sorted(set(now) - expected)}, splits에만 {sorted(expected - set(now))}")
    write_csv(MANIFEST, ["doc_id", "sha256"], [[d, now[d]] for d in sorted(now)])
    print(f"봉인 완료: {len(now)}건 → {MANIFEST.relative_to(ROOT)}  (다음: git tag test-sealed)")


# ---------------------------------------------------------------- test2
def _pdf_hashes(ids):
    """{doc_id: (원본 파일명, PDF 해시)}. sources.csv에 없거나 PDF가 없으면 종료."""
    src = read_csv(SOURCES_CSV)
    out, problems = {}, []
    for d in sorted(ids):
        if d not in src:
            problems.append(f"{d}: sources.csv에 없음")
            continue
        p = RAW_DIR / src[d]["source_file"]
        if not p.exists():
            problems.append(f"{d}: 원본 PDF 없음 ({p.relative_to(ROOT)})")
            continue
        out[d] = (src[d]["source_file"], sha(p))
    return out, problems


def _write_docs(force):
    if TEST2_DOCS.exists() and read_csv(TEST2_DOCS) and not force:
        sys.exit("test2 문서 목록이 이미 봉인돼 있음. 다시 하려면 사유를 report/decisions.md에 적고 --force")
    if list(TEST2_DIR.glob("*.json")) and not force:
        sys.exit("eval/test2/에 정답 파일이 이미 있음 — 문서 목록 봉인은 라벨링 전에 해야 한다(docs/plan_c.md 4절)")
    ids = split_ids("test2")
    if not ids:
        sys.exit("splits.csv에 test2 문서가 없음")
    hashes, problems = _pdf_hashes(ids)
    if problems:
        sys.exit("봉인 중단:\n  " + "\n  ".join(problems))
    write_csv(TEST2_DOCS, ["doc_id", "source_file", "pdf_sha256"],
              [[d, f, h] for d, (f, h) in sorted(hashes.items())])
    print(f"test2 문서 목록 봉인: {len(ids)}건 → {TEST2_DOCS.relative_to(ROOT)}  (다음: git tag test2-docs-sealed, 그 뒤 라벨링)")


def _verify_docs():
    saved = read_csv(TEST2_DOCS)
    if not saved:
        return ["report/test2_docs_manifest.csv가 없음 — 1단계(--write-docs) 전"]
    problems = []
    now_ids = split_ids("test2")
    if now_ids != set(saved):
        problems.append(f"splits.csv의 test2가 봉인 목록과 다름: 봉인에만 {sorted(set(saved) - now_ids)}, "
                        f"splits에만 {sorted(now_ids - set(saved))}")
    hashes, missing = _pdf_hashes(set(saved) & now_ids)
    problems += missing
    problems += diff({d: r["pdf_sha256"] for d, r in saved.items() if d in hashes},
                     {d: h for d, (_, h) in hashes.items()}, "원본 PDF")
    return problems


def cut_status():
    """{doc_id: 추출 상태} — data/text/_cut_log.csv (pipeline/extract_text.py가 씀)"""
    return {d: r.get("status", "") for d, r in read_csv(TEXT_DIR / "_cut_log.csv").items()}


def _test2_now(ids):
    """{doc_id: (정답 해시, 입력 텍스트 해시, 추출 상태)}와 문제 목록(정답 없음 · 추출 기록 불일치)"""
    out, problems = {}, []
    cut = cut_status()
    for d in sorted(ids):
        lab, txt = TEST2_DIR / f"{d}.json", TEXT_DIR / f"{d}.txt"
        status = cut.get(d, "")
        if not lab.exists():
            problems.append(f"{d}: 정답 없음(eval/test2/)")
        if txt.exists() and status != "SUCCESS":
            problems.append(f"{d}: 입력 텍스트가 있는데 _cut_log.csv 상태가 {status or '기록 없음'} — 추론에서 건너뛰게 됨")
        if not txt.exists() and status in ("", "SUCCESS"):
            problems.append(f"{d}: 입력 텍스트가 없는데 _cut_log.csv에 추출 실패 기록이 없음(상태 {status or '기록 없음'})")
        out[d] = (sha(lab) if lab.exists() else "", sha(txt) if txt.exists() else "", status)
    return out, problems


def _write_test2(force):
    if TEST2_MANIFEST.exists() and read_csv(TEST2_MANIFEST) and not force:
        sys.exit("test2 정답이 이미 봉인돼 있음. 다시 하려면 사유를 report/decisions.md에 적고 --force")
    if problems := _verify_docs():
        sys.exit("1단계 봉인 대조 실패 — 먼저 해결:\n  " + "\n  ".join(problems))
    ids = set(read_csv(TEST2_DOCS))
    extra = sorted({p.stem for p in TEST2_DIR.glob("*.json")} - ids)
    if extra:
        sys.exit(f"eval/test2/에 봉인 목록 밖 파일: {extra}")
    now, problems = _test2_now(ids)
    if problems:
        sys.exit("봉인할 수 없음:\n  " + "\n  ".join(problems))
    failed = sorted(d for d, (_, th, _) in now.items() if not th)
    if failed:
        # 추출 실패 문서도 정답은 있어야 하고, 채점에서 실패로 센다(분모에서 빼지 않음)
        print(f"[알림] 추출 실패로 입력 텍스트가 없는 문서(채점에서 실패로 셈): {failed}")
    write_csv(TEST2_MANIFEST, ["doc_id", "label_sha256", "text_sha256", "cut_status"],
              [[d, lh, th, st] for d, (lh, th, st) in sorted(now.items())])
    print(f"test2 정답·입력 봉인: {len(now)}건 → {TEST2_MANIFEST.relative_to(ROOT)}  (다음: git tag test2-sealed)")


def _verify_test2():
    problems = _verify_docs()
    saved = read_csv(TEST2_MANIFEST)
    if not saved:
        problems.append("report/test2_manifest.csv가 없음 — 2단계(--write) 전")
    else:
        stage1 = set(read_csv(TEST2_DOCS))
        if stage1 != set(saved):
            problems.append(f"2단계 목록이 1단계와 다름: 1단계에만 {sorted(stage1 - set(saved))}, "
                            f"2단계에만 {sorted(set(saved) - stage1)}")
        now, _ = _test2_now(stage1 | set(saved))
        problems += diff({d: r["label_sha256"] for d, r in saved.items()}, {d: v[0] for d, v in now.items()}, "정답")
        problems += diff({d: r["text_sha256"] for d, r in saved.items()}, {d: v[1] for d, v in now.items()}, "입력 텍스트")
        problems += diff({d: r.get("cut_status", "") for d, r in saved.items()}, {d: v[2] for d, v in now.items()},
                         "추출 상태(_cut_log.csv)")
    if problems:
        return False, "; ".join(problems)
    return True, f"test2 봉인 대조 통과 ({len(saved)}건: 문서 목록 · 원본 PDF · 정답 · 입력 텍스트)"


# ---------------------------------------------------------------- 공통 진입점
def verify(split="test"):
    """(통과 여부, 메시지). infer.py·score.py가 부른다."""
    return _verify_test2() if split == "test2" else _verify_test()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("test", "test2"), default="test")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true", help="정답 봉인(test2는 2단계: 정답 + 입력 텍스트)")
    g.add_argument("--write-docs", action="store_true", help="test2 1단계: 분할 직후 문서 목록 + 원본 PDF")
    g.add_argument("--verify", action="store_true")
    ap.add_argument("--force", action="store_true", help="기존 봉인 덮어쓰기(비상용)")
    args = ap.parse_args()
    if args.write_docs:
        if args.split != "test2":
            sys.exit("--write-docs는 test2 전용")
        _write_docs(args.force)
    elif args.write:
        _write_test2(args.force) if args.split == "test2" else _write_test(args.force)
    else:
        ok, msg = verify(args.split)
        print(("OK  " if ok else "FAIL  ") + msg)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

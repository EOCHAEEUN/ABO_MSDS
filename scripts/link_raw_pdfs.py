"""data/raw/에 data/sources.csv의 파일명(예: KR-3DSYS-001.pdf)으로 원본 PDF 바로가기를 만든다.

PR #41(546644b)에서 sources.csv의 source_file을 doc_id 이름으로 바꿨다. PDF를 원래 파일명으로 받아 둔
컴퓨터에서는 검토 화면의 원본 PDF · 쪽수 · 서버 적재가 파일을 못 찾는다. 원래 파일명은 그 직전 커밋의
sources.csv에 있으므로, 거기서 찾아 같은 폴더 안 상대 경로 심볼릭 링크를 만든다(파일 복사 · 이름 변경 없음).
data/raw/는 git 제외라 링크도 커밋되지 않는다. 이미 있는 파일 · 링크는 건드리지 않는다.

  python3 scripts/link_raw_pdfs.py            # 만들 링크를 보여 주고 만든다
  python3 scripts/link_raw_pdfs.py --dry-run  # 보여 주기만
"""
import argparse
import csv
import io
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RENAME_COMMIT = "546644b"  # sources.csv의 source_file을 doc_id 이름으로 바꾼 커밋


def rows(text):
    return {r["doc_id"]: r["source_file"] for r in csv.DictReader(io.StringIO(text.lstrip("﻿")))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    old = rows(subprocess.run(["git", "show", f"{RENAME_COMMIT}^:data/sources.csv"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout)
    now = rows((ROOT / "data" / "sources.csv").read_text(encoding="utf-8-sig"))
    made, missing = [], []
    for doc_id, name in now.items():
        if (RAW / name).exists():
            continue
        orig = old.get(doc_id)
        if orig and orig != name and (RAW / orig).is_file():
            if not args.dry_run:
                os.symlink(orig, RAW / name)
            made.append(f"{name} → {orig}")
        else:
            missing.append(doc_id)
    print(f"{'만들 링크' if args.dry_run else '만든 링크'} {len(made)}개")
    for m in made:
        print("  ", m)
    if missing:
        print(f"원본 PDF도 이 컴퓨터에 없음 {len(missing)}건(팀 드라이브에서 받을 것): {missing}")


if __name__ == "__main__":
    main()

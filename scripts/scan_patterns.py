# 저장 위치: <프로젝트 루트>/scripts/scan_patterns.py
"""0단계 — 실문서에서 실제로 쓰인 항목 제목·P문구 라벨을 훑어본다.

코드 짜기 전에 한 번 돌리고, 출력을 보고 core/preprocess.py의 패턴 상수를 확정한다.
파이프라인에 포함되지 않는 조사용 스크립트다. (출력 결과는 저장소에 커밋하지 않는다)

실행: python scripts/scan_patterns.py --raw data/raw
      python scripts/scan_patterns.py --raw data/text --ext .txt
"""
import argparse
import glob
import os
import re
from collections import Counter

PROBES = {
    "2항": r"(^\s*2\s*[.\)\-–]?\s*(유해|Hazard))|제\s*2\s*항|SECTION\s*2",
    "3항": r"(^\s*3\s*[.\)\-–]?\s*(구성|Composition))|제\s*3\s*항|SECTION\s*3",
    "4항": r"(^\s*4\s*[.\)\-–]?\s*(응급|First))|제\s*4\s*항|SECTION\s*4",
    "P라벨": r"예방\s*조치|Precautionary",
    "H라벨": r"유해\s*[·ㆍ‧./]?\s*위험\s*문구|Hazard\s+statements?",
}


def read(path):
    if path.lower().endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description="MSDS 항목 제목 패턴 실측")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--ext", default=".pdf")
    ap.add_argument("--max-len", type=int, default=70, help="출력할 줄 길이 제한")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.raw, f"*{args.ext}")))
    if not paths:
        print(f"파일이 없습니다: {args.raw}/*{args.ext}")
        return

    seen = {k: Counter() for k in PROBES}
    missing = {k: [] for k in PROBES}

    for path in paths:
        doc_id = os.path.splitext(os.path.basename(path))[0]
        try:
            text = read(path)
        except Exception as e:
            print(f"[읽기 실패] {doc_id}: {type(e).__name__}")
            continue
        lines = text.splitlines()
        for label, pattern in PROBES.items():
            hits = [ln.strip()[:args.max_len] for ln in lines
                    if re.search(pattern, ln, re.IGNORECASE)]
            if hits:
                seen[label][hits[0]] += 1          # 문서당 첫 줄만 집계
            else:
                missing[label].append(doc_id)

    print(f"문서 {len(paths)}건 조사\n")
    for label in PROBES:
        print(f"=== {label} — 실제로 쓰인 표현 (건수) ===")
        for line, n in seen[label].most_common():
            print(f"  {n:3d}  {line}")
        if missing[label]:
            print(f"  [미발견 {len(missing[label])}건] " + ", ".join(missing[label][:10])
                  + (" ..." if len(missing[label]) > 10 else ""))
        print()

    print("위 목록을 보고 core/preprocess.py의 패턴 상수를 채운다.")
    print("특히 '4항 미발견' 문서는 NOT_FOUND가 되어 모델에 투입되지 않으니 원본을 직접 확인할 것.")


if __name__ == "__main__":
    main()
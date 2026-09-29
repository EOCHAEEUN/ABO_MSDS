"""PDF → 1~3항 텍스트. GPU 없이 일괄 평가 입력과 업로드 입력에 공통 사용.

일괄 실행 예시 (test의 세 경로는 모두 저장소 밖에 둔다)::

    python3 -m pipeline.extract_text --raw-dir <pdf 폴더> \
        --sources <doc_id,source_file CSV> --text-dir <출력 폴더> --expected-count 18

성공 문서는 {doc_id}.txt, 실패 문서는 review_required/{doc_id}.txt에 사유를
남긴다. _cut_log.csv에는 성공/실패 문서를 모두 기록한다. 이 명령은 모델을 부르지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

import pdfplumber

from core.preprocess import (SECTION2_PATTERNS, SECTION3_PATTERNS, SECTION4_PATTERNS,
                             find_first, preprocess)

MIN_TEXT_LEN = 200
# 문서마다 배수가 다르다(대부분 5회, KR-THERMO-001은 4회 확인됨) — 고정값 대신 문서별로 잰다.
_RUN_RE = re.compile(r"([가-힣ㆍ․])\1+")
_MIN_RUN_LEN = 3          # 이보다 짧은 반복(길이 2)은 "성성"처럼 원래 겹치는 낱말일 수 있어 배수 추정에서 뺀다
_MIN_RUN_COUNT = 20       # 이보다 적게 나오면 우연한 반복으로 보고 배수를 매기지 않는다(원문 그대로 둠)
LOG_COLUMNS = ("doc_id", "status", "section4_pattern", "p_block_pattern", "cut_page",
               "char_count", "token_count", "h_code_before", "h_code_after", "note", "reason")


def bold_repeat_factor(text: str) -> int:
    """pdfplumber가 굵은 글씨를 글자당 몇 번 겹쳐 뽑았는지 이 문서에서 실측한다.

    길이 3 이상인 반복 구간의 최빈 길이를 배수로 본다("구성성분"처럼 원래 두 번 연달아
    나오는 낱말은 배수 k의 문서에서 길이 2k로 나타나 최빈값보다 드물다). 반복이 거의
    없으면(스캔이 아닌 정상 텍스트) 1을 돌려줘 아무것도 접지 않는다.
    """
    lengths = Counter(len(m.group(0)) for m in _RUN_RE.finditer(text) if len(m.group(0)) >= _MIN_RUN_LEN)
    if not lengths:
        return 1
    factor, count = lengths.most_common(1)[0]
    return factor if count >= _MIN_RUN_COUNT else 1


def undouble(text: str) -> str:
    """굵은 글씨가 글자당 k번 겹쳐 뽑힌 것을 복원한다. k는 이 문서에서 잰 값(bold_repeat_factor).

    k 단위로만 줄이므로 "구성성분"처럼 같은 글자가 원래 두 번 연달아 나오는 진짜 단어는
    2k번 겹침으로 남아 올바르게 2개로 줄어든다(1개로 뭉개지지 않는다).
    """
    factor = bold_repeat_factor(text)
    if factor <= 1:
        return text
    return re.compile(r"([가-힣ㆍ․])\1{%d}" % (factor - 1)).sub(r"\1", text)


def _failed(reason: str, raw_text: str = "", note: str = "") -> dict:
    return {"status": "NOT_FOUND", "reason": reason, "text": None, "raw_text": raw_text,
            "section4_pattern": None, "p_block_pattern": None, "cut_page": None,
            "h_code_before": None, "h_code_after": None, "note": note or reason}


def extract_pdf(pdf_path: str | Path) -> dict:
    """PDF 하나를 읽어 core.preprocess로 자른다. 실패하면 모델에 넣을 text를 주지 않는다."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        return _failed("PDF_NOT_FOUND")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:
        return _failed("PDF_UNREADABLE", note=f"PDF 판독 실패: {type(exc).__name__}: {exc}")

    raw = undouble("\n".join(pages))
    if len(raw.strip()) < MIN_TEXT_LEN:
        return _failed("TEXT_TOO_SHORT", raw, f"추출 텍스트 {len(raw.strip())}자 < {MIN_TEXT_LEN}자")

    result = preprocess(raw)
    if result["status"] != "SUCCESS":
        return _failed("NOT_FOUND_SECTION4", raw, result.get("note") or "4항 제목을 찾지 못함")
    text = result["text"]
    lines = text.splitlines()
    if find_first(SECTION2_PATTERNS, lines)[0] is None:
        return _failed("NOT_FOUND_SECTION2", raw, "2항 제목을 찾지 못함")
    if find_first(SECTION3_PATTERNS, lines)[0] is None:
        return _failed("NOT_FOUND_SECTION3", raw, "3항 제목을 찾지 못함")
    if len(text.strip()) < MIN_TEXT_LEN:
        return _failed("TEXT_TOO_SHORT", raw, f"1~3항 텍스트 {len(text.strip())}자 < {MIN_TEXT_LEN}자")

    raw_lines = raw.splitlines()
    section3, _ = find_first(SECTION3_PATTERNS, raw_lines)
    section4, _ = find_first(SECTION4_PATTERNS, raw_lines, (section3 + 1) if section3 is not None else 0)
    cut_page = None
    if section4 is not None:
        line_end = 0
        for page_number, page in enumerate(pages, 1):
            line_end += len(page.splitlines())
            if section4 < line_end:
                cut_page = page_number
                break
    return {**result, "reason": "", "raw_text": raw, "cut_page": cut_page}


def _sources(path: Path, raw_dir: Path) -> list[tuple[str, Path]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"doc_id", "source_file"}.issubset(reader.fieldnames or []):
            raise ValueError("sources CSV에는 doc_id,source_file 열이 필요합니다")
        rows = list(reader)
    if not rows:
        raise ValueError("sources CSV에 문서가 없습니다")
    seen = set()
    sources = []
    for row in rows:
        doc_id = (row["doc_id"] or "").strip()
        source_file = (row["source_file"] or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", doc_id) or doc_id in seen:
            raise ValueError(f"문서 ID가 비었거나 중복됐거나 허용되지 않는 문자 포함: {doc_id!r}")
        seen.add(doc_id)
        pdf = (raw_dir / source_file).resolve()
        if not source_file or not pdf.is_relative_to(raw_dir.resolve()):
            raise ValueError(f"PDF 경로는 raw-dir 안에 있어야 합니다: {source_file!r}")
        sources.append((doc_id, pdf))
    return sources


def extract_directory(raw_dir: str | Path, sources_csv: str | Path, text_dir: str | Path,
                      expected_count: int | None = None, overwrite: bool = False) -> tuple[int, int]:
    """명시된 전체 문서를 처리하고 결과 로그를 쓴다. 기존 결과는 명시적 overwrite 없이는 보존."""
    text_dir = Path(text_dir)
    sources = _sources(Path(sources_csv), Path(raw_dir))
    if expected_count is not None and len(sources) != expected_count:
        raise ValueError(f"문서 수가 예상과 다릅니다: {len(sources)} != {expected_count}")
    existing = [p for doc_id, _ in sources for p in
                (text_dir / f"{doc_id}.txt", text_dir / "review_required" / f"{doc_id}.txt") if p.exists()]
    if (existing or (text_dir / "_cut_log.csv").exists()) and not overwrite:
        raise FileExistsError("기존 텍스트/로그가 있습니다. 다른 출력 폴더를 쓰거나 --overwrite를 명시하세요")
    text_dir.mkdir(parents=True, exist_ok=True)
    review_dir = text_dir / "review_required"
    review_dir.mkdir(exist_ok=True)
    rows = []
    success = 0
    for doc_id, pdf in sources:
        text_path = text_dir / f"{doc_id}.txt"
        review_path = review_dir / f"{doc_id}.txt"
        if overwrite:
            text_path.unlink(missing_ok=True)
            review_path.unlink(missing_ok=True)
        result = extract_pdf(pdf)
        if result["status"] == "SUCCESS":
            text_path.write_text(result["text"], encoding="utf-8")
            success += 1
        else:
            review_path.write_text(f"reason: {result['reason']}\nsource_file: {pdf.name}\n"
                                   f"note: {result['note']}\n\n{result['raw_text']}", encoding="utf-8")
        rows.append({"doc_id": doc_id, "status": result["status"], "reason": result["reason"],
                     "section4_pattern": result["section4_pattern"], "p_block_pattern": result["p_block_pattern"],
                     "cut_page": result["cut_page"], "char_count": len(result["text"] or ""),
                     "token_count": "", "h_code_before": result["h_code_before"],
                     "h_code_after": result["h_code_after"], "note": result["note"]})
    with (text_dir / "_cut_log.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return success, len(sources) - success


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, required=True, help="원본 PDF 폴더")
    parser.add_argument("--sources", type=Path, required=True, help="doc_id,source_file 열을 가진 전체 문서 CSV")
    parser.add_argument("--text-dir", type=Path, required=True, help="텍스트·로그 출력 폴더")
    parser.add_argument("--expected-count", type=int, help="예상 문서 수. 다르면 쓰기 전에 중단")
    parser.add_argument("--overwrite", action="store_true", help="기존 텍스트·로그를 명시적으로 다시 생성")
    args = parser.parse_args(argv)
    ok, failed = extract_directory(args.raw_dir, args.sources, args.text_dir,
                                   args.expected_count, args.overwrite)
    print(f"PDF {ok + failed}건: 성공 {ok}건, 수동 확인 {failed}건 → {args.text_dir}")


if __name__ == "__main__":
    main()

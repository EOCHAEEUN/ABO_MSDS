"""train·val 원문 PDF 전체(1~16항)를 RAG 검색 인덱스로 만든다.

봉인된 test는 data/splits.csv에 없으므로 대상이 될 수 없다. 원본 PDF와 생성된
ChromaDB는 git 제외 대상이며 로컬 실행용이다.

    python3 -m app.rag.index
    python3 -m app.rag.index --overwrite
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

import pdfplumber
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag import settings
from pipeline.extract_text import undouble

HEADING_RE = re.compile(
    r"^\s*\|?\s*(?:#{1,6}\s*)?\**\s*(?:SECTION\s*|항목\s*)?(\d{1,2})\s*[.:)\-](?!\d)\s*(.+)$",
    re.IGNORECASE,
)
SECTION_KEYWORDS = {
    1: ["회사", "identification"], 2: ["유해", "hazard"], 3: ["구성", "composition"],
    4: ["응급", "first"], 5: ["화재", "폭발", "fire"], 6: ["누출", "release"],
    7: ["취급", "저장", "handling"], 8: ["노출", "보호구", "exposure"],
    9: ["물리", "physical"], 10: ["안정성", "반응성", "stability"],
    11: ["독성", "toxicolog"], 12: ["환경", "ecolog"], 13: ["폐기", "disposal"],
    14: ["운송", "transport"], 15: ["법적", "규제", "regulatory"], 16: ["참고", "other"],
}


def find_headings(lines: list[str]):
    candidates = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line) if len(line) <= 100 else None
        if not match or not 1 <= int(match.group(1)) <= 16:
            continue
        number, title = int(match.group(1)), match.group(2).strip(" #*|")
        keyword = any(word in title.lower() for word in SECTION_KEYWORDS[number])
        styled = line.lstrip().startswith(("#", "**", "|"))
        candidates.append((index, number, title, 1 + 2 * keyword + styled, keyword or styled))

    best, previous = [None] * len(candidates), [-1] * len(candidates)
    for right, (_, number, _, score, can_jump) in enumerate(candidates):
        if number == 1 or can_jump:
            best[right] = score
        for left in range(right):
            prior = candidates[left][1]
            if best[left] is None or number <= prior:
                continue
            if (number == prior + 1 or can_jump) and (best[right] is None or best[left] + score > best[right]):
                best[right], previous[right] = best[left] + score, left
    ends = [index for index, score in enumerate(best) if score is not None]
    if not ends:
        return []
    cursor = max(ends, key=lambda index: best[index])
    chosen = []
    while cursor != -1:
        chosen.append(candidates[cursor][:3])
        cursor = previous[cursor]
    return chosen[::-1]


def split_sections(text: str):
    lines = text.splitlines()
    headings = find_headings(lines)
    bounds = [(-1, 0, "문서 앞부분"), *headings]
    sections = []
    for position, (start, number, title) in enumerate(bounds):
        end = bounds[position + 1][0] if position + 1 < len(bounds) else len(lines)
        body = "\n".join(lines[start + 1:end]).strip()
        if body:
            sections.append((number, title, body))
    return sections


def _rows(path: Path, key: str) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row[key]: row for row in csv.DictReader(handle)}


def sealed_hashes(root: Path = settings.ROOT) -> set[str]:
    """봉인 manifest의 모든 SHA-256. PDF 또는 추출 텍스트와 일치하면 인덱싱하지 않는다."""
    manifest = root / "report" / "test_manifest.csv"
    if not manifest.is_file():
        return set()
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        return {row.get("sha256", "").lower() for row in csv.DictReader(handle) if row.get("sha256")}


def _documents_from_pdf(pdf_path: Path, doc_id: str, product: str, split: str,
                        splitter: RecursiveCharacterTextSplitter, blocked: set[str]):
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest() in blocked:
        return [], f"{pdf_path.name}: 봉인된 test 해시와 일치"
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = undouble("\n".join(page.extract_text() or "" for page in pdf.pages))
    except Exception as issue:
        return [], f"{pdf_path.name}: PDF 판독 실패({type(issue).__name__})"
    if hashlib.sha256(text.encode("utf-8")).hexdigest() in blocked:
        return [], f"{pdf_path.name}: 추출 텍스트가 봉인된 test 해시와 일치"
    if len(text.strip()) < 200:
        return [], f"{pdf_path.name}: 추출 텍스트가 너무 짧음"
    documents = []
    for number, title, body in split_sections(text):
        label_text = f"{number}. {title}" if number else title
        for chunk_number, chunk in enumerate(splitter.split_text(body)):
            documents.append(Document(
                page_content=f"[출처: {product} · {label_text}]\n{chunk}",
                metadata={"doc_id": doc_id, "product_name": product, "section": number,
                          "section_title": title, "chunk": chunk_number, "split": split},
            ))
    return documents, None


def build_documents(root: Path = settings.ROOT) -> tuple[list[Document], list[str]]:
    splits = _rows(root / "data" / "splits.csv", "doc_id")
    sources = _rows(root / "data" / "sources.csv", "doc_id")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP
    )
    blocked = sealed_hashes(root)
    documents, skipped = [], []
    for doc_id, split in sorted(splits.items()):
        if split.get("split") not in {"train", "val"}:
            continue
        source_file = (sources.get(doc_id) or {}).get("source_file")
        pdf_path = root / "data" / "raw" / (source_file or "")
        label_path = root / "data" / "labels" / f"{doc_id}.json"
        if not source_file or not pdf_path.is_file() or not label_path.is_file():
            skipped.append(f"{doc_id}: 원본 PDF 또는 라벨 없음")
            continue
        label = json.loads(label_path.read_text(encoding="utf-8"))
        product = (label.get("product_name") or {}).get("value") or doc_id
        chunks, reason = _documents_from_pdf(pdf_path, doc_id, product, split["split"], splitter, blocked)
        documents.extend(chunks)
        if reason:
            skipped.append(reason)
    return documents, skipped


def build_pdf_directory(pdf_dir: Path, root: Path = settings.ROOT) -> tuple[list[Document], list[str]]:
    """사용자가 지정한 폴더의 PDF를 직접 인덱싱한다. 파일명이 제품명이 된다."""
    pdf_dir = pdf_dir.expanduser().resolve()
    if not pdf_dir.is_dir():
        return [], [f"PDF 폴더가 없습니다: {pdf_dir}"]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP
    )
    blocked = sealed_hashes(root)
    documents, skipped = [], []
    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        product = pdf_path.stem
        chunks, reason = _documents_from_pdf(
            pdf_path, pdf_path.stem, product, "local", splitter, blocked
        )
        documents.extend(chunks)
        if reason:
            skipped.append(reason)
    return documents, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="기존 로컬 RAG 인덱스를 지우고 다시 생성")
    parser.add_argument("--pdf-dir", type=Path,
                        help="이 폴더의 *.pdf를 직접 인덱싱. 파일명을 제품명으로 사용")
    args = parser.parse_args(argv)
    documents, skipped = (build_pdf_directory(args.pdf_dir) if args.pdf_dir else build_documents())
    if not documents:
        detail = f" 첫 사유: {skipped[0]}" if skipped else ""
        raise SystemExit(f"인덱싱할 PDF가 없습니다.{detail}")
    if settings.INDEX_DIR.exists():
        if not args.overwrite:
            raise SystemExit(f"인덱스가 이미 있습니다: {settings.INDEX_DIR} (--overwrite로 재생성)")
        shutil.rmtree(settings.INDEX_DIR)
    from langchain_chroma import Chroma

    settings.INDEX_DIR.parent.mkdir(parents=True, exist_ok=True)
    Chroma.from_documents(
        documents, embedding=settings.get_embeddings(), collection_name=settings.COLLECTION_NAME,
        persist_directory=str(settings.INDEX_DIR),
    )
    print(f"RAG 청크 {len(documents)}개 → {settings.INDEX_DIR}")
    for message in skipped:
        print(f"[건너뜀] {message}")


if __name__ == "__main__":
    main()

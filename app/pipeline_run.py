"""
[김건하] PDF 1건 -> 텍스트 추출 -> 모델 출력 -> 스키마 검사 -> Rule Engine -> DB 적재 -> JSON 출력.

실행: python3 -m app.pipeline_run --pdf data/raw/<파일>.pdf --model mock --doc-id KR-KUMHO-002

실제 모델(app/model.py의 predict())은 아직 없어서 --model mock으로 data/labels/{doc-id}.json을
"모델 출력인 척" 문자열로 쓴다(작업지시서 "하지 않는 것").

core/preprocess.py의 preprocess()는 이제 구현돼 있어 그대로 가져다 쓴다(새로 만들지 않음).
다만 preprocess()는 "굵은 글씨 겹침 복원(undouble)은 pipeline/extract_text.py가 preprocess()
전에 한다"고 자기 docstring에 명시했는데, pipeline/extract_text.py는 아직 빈 파일이다.
그래서 undouble만 get_text()에 [임시]로 넣었다 — pipeline/extract_text.py가 채워지면
그쪽 걸 쓰도록 이 부분만 지우면 된다(_undouble 함수 참고, 이번에 KR-3DSYS-001 원문 텍스트를
직접 고치면서 검증한 것과 같은 규칙: 굵은 글씨 문서는 글자당 정확히 5번 겹쳐 뽑힌다).
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pdfplumber

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.db import connect, init_db, save_extraction  # noqa: E402
from app.export import export_json  # noqa: E402
from app.rules.engine import run_rules  # noqa: E402
from core.preprocess import preprocess  # noqa: E402
from core.schema import check_schema, extract_json  # noqa: E402

_MIN_TEXT_LEN = 200
_UNDOUBLE_RE = re.compile(r"([가-힣ㆍ․])\1{4}")


def _undouble(text: str) -> str:
    """[임시] 굵은 글씨가 글자당 5번 겹쳐 뽑힌 것을 되돌린다("물물물물물"→"물").

    pipeline/extract_text.py가 이 일을 하게 되면(강덕우 담당) 이 함수는 지우고 그쪽을 쓴다.
    5개 단위로만 줄이므로 "구성성분"처럼 같은 글자가 원래 두 번 연달아 나오는 진짜 단어는
    10개 겹침으로 남아 올바르게 2개로 줄어든다(1개로 뭉개지지 않는다).
    """
    return _UNDOUBLE_RE.sub(r"\1", text)


def _raw_pdf_text(pdf_path: Path) -> Optional[str]:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return None


def get_text(pdf_path: Path, doc_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(source_text, failure_reason)을 반환한다. 실패면 source_text는 None.

    우선순위:
      1) data/text/{doc_id}.txt — 강덕우 파이프라인(pipeline/extract_text.py) 결과물이 있으면 최우선
      2) pdfplumber 원문 -> [임시] undouble -> core.preprocess.preprocess() (1~3항 절단, NOT_FOUND 판정)
    """
    if doc_id:
        cached = _REPO_ROOT / "data" / "text" / f"{doc_id}.txt"
        if cached.exists():
            text = cached.read_text(encoding="utf-8")
            if len(text) < _MIN_TEXT_LEN:
                return None, "TEXT_TOO_SHORT"
            return text, None

    raw_text = _raw_pdf_text(pdf_path)
    if raw_text is None:
        return None, "PDF_UNREADABLE"
    if len(raw_text) < _MIN_TEXT_LEN:
        return None, "TEXT_TOO_SHORT"

    result = preprocess(_undouble(raw_text))
    if result["status"] == "NOT_FOUND":
        return None, "NOT_FOUND_SECTION4"
    return result["text"], None


def _mock_predict(doc_id: str) -> str:
    label_path = _REPO_ROOT / "data" / "labels" / f"{doc_id}.json"
    if not label_path.exists():
        raise FileNotFoundError(
            f"mock 모드는 data/labels/(train·val)만 씁니다. {doc_id}.json을 찾을 수 없습니다 "
            "(test 문서는 이 경로에 없습니다 — 의도된 제한, 작업지시서 2절)."
        )
    return label_path.read_text(encoding="utf-8")


def predict(text: str, model_name: str, doc_id: Optional[str]) -> str:
    if model_name == "mock":
        if not doc_id:
            raise ValueError("--model mock은 --doc-id가 있어야 합니다")
        return _mock_predict(doc_id)
    from app.model import predict as real_predict  # 아직 미구현일 수 있음(양세윤 담당)

    return real_predict(text, model_name)


def _log_failure(reason: str, pdf_path: Path, model_name: str, out_dir: Path, detail: str = "") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "_failures.csv"
    is_new = not log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "file_name", "model_name", "reason", "detail"])
        w.writerow([datetime.now(timezone.utc).isoformat(), pdf_path.name, model_name, reason, detail])


def run_pdf(
    pdf_path: str | Path,
    model_name: str,
    doc_id: Optional[str] = None,
    db_path: str | Path = "data/db/msds.sqlite",
    out_dir: str | Path = "outputs/exports",
) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """PDF 1건을 끝까지 처리한다. (document_id, export_path, failure_reason)을 반환한다.

    실패하면 document_id·export_path는 None이고 failure_reason에 사유가 담긴다.
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)

    if not pdf_path.exists():
        _log_failure("PDF_NOT_FOUND", pdf_path, model_name, out_dir, str(pdf_path))
        return None, None, "PDF_NOT_FOUND"

    text, reason = get_text(pdf_path, doc_id)
    if text is None:
        _log_failure(reason or "TEXT_EXTRACTION_FAILED", pdf_path, model_name, out_dir)
        return None, None, reason or "TEXT_EXTRACTION_FAILED"

    raw_output = predict(text, model_name, doc_id)

    parsed_obj, parse_err = extract_json(raw_output)
    if parsed_obj is None:
        parsed = None
        rule_result = {"review_status": "SCHEMA_ERROR", "reason_code": "FORMAT_ERROR", "detail": parse_err}
    else:
        schema_ok, schema_errors = check_schema(parsed_obj)
        if schema_ok:
            parsed = parsed_obj
            rule_result = run_rules(parsed, source_text=text, doc_id=doc_id)
        else:
            parsed = None
            rule_result = {"review_status": "SCHEMA_ERROR", "reason_code": "SCHEMA_INVALID", "detail": schema_errors}

    conn = connect(db_path)
    try:
        init_db(conn)
        document_id = save_extraction(conn, pdf_path, model_name, raw_output, parsed, rule_result)
        export_path = export_json(conn, document_id, out_dir=out_dir)
    finally:
        conn.close()

    return document_id, export_path, None


def _cli() -> None:
    parser = argparse.ArgumentParser(description="PDF 1건 -> SQLite 적재 -> JSON 출력")
    parser.add_argument("--pdf", required=True, help="원본 PDF 경로 (예: data/raw/foo.pdf)")
    parser.add_argument("--model", required=True, choices=["mock", "base", "qlora"])
    parser.add_argument("--doc-id", default=None, help="mock 모드는 필수. data/labels/{doc-id}.json을 모델 출력으로 씀")
    parser.add_argument("--db", default="data/db/msds.sqlite")
    parser.add_argument("--out-dir", default="outputs/exports")
    args = parser.parse_args()

    document_id, export_path, failure_reason = run_pdf(
        args.pdf, args.model, doc_id=args.doc_id, db_path=args.db, out_dir=args.out_dir
    )
    if failure_reason:
        print(f"실패: {failure_reason} ({args.out_dir}/_failures.csv에 기록)", file=sys.stderr)
        sys.exit(1)
    print(f"document_id={document_id}")
    print(f"export={export_path}")


if __name__ == "__main__":
    _cli()

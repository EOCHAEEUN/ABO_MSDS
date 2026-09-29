"""PDF 1건 → 공통 PDF 전처리 → 모델(또는 명시적 mock) → 검증 → DB → JSON.

실행: python3 -m app.pipeline_run --pdf data/raw/<파일>.pdf --model qlora
업로드 API와 일괄 평가 입력은 pipeline.extract_text.extract_pdf를 공유한다.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.db import connect, init_db, save_extraction  # noqa: E402
from app.export import export_json  # noqa: E402
from app.rules.engine import run_rules  # noqa: E402
from pipeline.extract_text import extract_pdf  # noqa: E402
from core.schema import check_schema, extract_json  # noqa: E402

def get_text(pdf_path: Path, doc_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """PDF에서 매번 1~3항을 만든다. doc_id는 mock 출력 선택에만 사용한다."""
    result = extract_pdf(pdf_path)
    return result["text"], result["reason"] or None


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
    from app.model import predict as real_predict

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

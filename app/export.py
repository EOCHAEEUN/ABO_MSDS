"""
[김건하] SQLite → JSON 파일 내보내기.

raw_json을 그대로 내보내지 않고 테이블에서 다시 조립한다 — 저장이 맞았는지
왕복으로 확인하기 위해서다(작업지시서 4절). 단, list_status와
recommended_use·use_restrictions의 source_status는 테이블에 열이 없으므로
(3절 "스키마 빈 곳", PM 승인 대기 — 현재 기본값은 raw_json에서 읽는 것)
core.schema.extract_json으로 raw_json을 다시 파싱해서 채운다.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from core.schema import extract_json
from src.schema import MSDSLabel


def _rows(conn: sqlite3.Connection, table: str, document_id: int, order_by: str) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT * FROM {table} WHERE document_id = ? ORDER BY {order_by}",  # noqa: S608 (table은 상수 4개뿐)
        (document_id,),
    ).fetchall()


def _build_extraction(conn: sqlite3.Connection, doc: dict[str, Any]) -> Optional[dict[str, Any]]:
    """테이블 값으로 MSDSLabel 모양 dict를 다시 조립한다. 조립 불가면 None."""
    if doc["product_name_status"] is None:
        return None  # save_extraction이 parsed=None으로 저장한 문서(스키마 실패 등)

    raw_obj, _err = extract_json(doc["raw_json"])
    raw_obj = raw_obj or {}

    document_id = doc["id"]
    ingredients = [
        {
            "chemical_name": r["chemical_name"],
            "cas_number": r["cas_number"],
            "ke_number": r["ke_number"],
            "content": r["content"],
            "is_substitute_data": bool(r["is_substitute_data"]),
        }
        for r in _rows(conn, "msds_ingredients", document_id, "seq")
    ]
    classifications = [
        {"hazard_class": r["hazard_class"], "category": r["category"]}
        for r in _rows(conn, "msds_classifications", document_id, "id")
    ]
    hazard_statements = [
        {"code": r["code"], "text": r["text"]}
        for r in _rows(conn, "msds_hazard_statements", document_id, "id")
    ]

    extraction = {
        "product_name": {"value": doc["product_name"], "source_status": doc["product_name_status"]},
        "recommended_use": {
            "value": doc["recommended_use"],
            "source_status": (raw_obj.get("recommended_use") or {}).get("source_status"),
        },
        "use_restrictions": {
            "value": doc["use_restrictions"],
            "source_status": (raw_obj.get("use_restrictions") or {}).get("source_status"),
        },
        "supplier": {
            "company_name": doc["supplier_name"],
            "address": doc["supplier_address"],
            "emergency_phone": doc["supplier_phone"],
        },
        "ingredients": ingredients,
        "ghs_classification": classifications,
        "signal_word": {"value": doc["signal_word"], "source_status": doc["signal_word_status"]},
        "hazard_statements": hazard_statements,
        "list_status": raw_obj.get("list_status"),
    }

    try:
        MSDSLabel.model_validate(extraction)
    except ValidationError:
        return None  # 조립 결과가 스키마를 못 지키면 null로 내보낸다(왕복 실패를 숨기지 않음)
    return extraction


def export_json(conn: sqlite3.Connection, document_id: int, out_dir: str | Path = "outputs/exports") -> str:
    """문서 1건을 JSON 파일로 내보내고 만든 파일 경로를 반환한다."""
    row = conn.execute("SELECT * FROM msds_documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise ValueError(f"document_id {document_id}가 msds_documents에 없습니다")
    doc = dict(row)

    extraction = _build_extraction(conn, doc)
    review = json.loads(doc["rule_json"]) if doc["rule_json"] else None

    payload = {
        "document": {
            "document_id": doc["id"],
            "file_name": doc["file_name"],
            "file_hash": doc["file_hash"],
            "revision": doc["revision"],
            "model_name": doc["model_name"],
            "extracted_at": doc["extracted_at"],
        },
        "extraction": extraction,
        "review": review,
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(doc["file_name"]).stem
    out_path = out_dir / f"{stem}_{doc['model_name']}_r{doc['revision']}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)

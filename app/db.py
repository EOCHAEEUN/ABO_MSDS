"""
[김건하] PDF 추출 결과 SQLite 적재. 테이블 스키마는 동결 — 열·테이블 추가/변경 금지
(작업지시서 "PDF → SQLite 적재 → JSON 출력" 3절 참고).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS msds_documents (
    id INTEGER PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    product_name TEXT, product_name_status TEXT,
    recommended_use TEXT, use_restrictions TEXT,
    supplier_name TEXT, supplier_address TEXT, supplier_phone TEXT,
    signal_word TEXT, signal_word_status TEXT,
    model_name TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    rule_json TEXT,
    extracted_at TEXT NOT NULL,
    UNIQUE (file_hash, revision, model_name)
);

CREATE TABLE IF NOT EXISTS msds_ingredients (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES msds_documents(id),
    seq INTEGER NOT NULL,
    chemical_name TEXT, cas_number TEXT, ke_number TEXT, content TEXT,
    is_substitute_data INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS msds_classifications (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES msds_documents(id),
    hazard_class TEXT, category TEXT
);

CREATE TABLE IF NOT EXISTS msds_hazard_statements (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES msds_documents(id),
    code TEXT, text TEXT
);

CREATE TABLE IF NOT EXISTS msds_reviews (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES msds_documents(id),
    field_path TEXT NOT NULL,
    extracted_value TEXT, confirmed_value TEXT,
    review_status TEXT, reason_code TEXT,
    confirmed_at TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _next_revision(conn: sqlite3.Connection, file_hash: str, model_name: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(revision), 0) FROM msds_documents WHERE file_hash = ? AND model_name = ?",
        (file_hash, model_name),
    ).fetchone()
    return row[0] + 1


def save_extraction(
    conn: sqlite3.Connection,
    pdf_path: str | Path,
    model_name: str,
    raw_output: str,
    parsed: Optional[dict[str, Any]],
    rule_result: Optional[dict[str, Any]],
) -> int:
    """추출 결과 1건을 테이블 4개에 저장한다. parsed가 None이면 문서 행만 넣는다.

    document + ingredients + classifications + hazard_statements를 트랜잭션
    하나로 묶는다. 중간에 예외가 나면 문서 행을 포함해 전부 롤백된다.
    """
    import hashlib

    pdf_path = Path(pdf_path)
    file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    file_name = pdf_path.name
    extracted_at = datetime.now(timezone.utc).isoformat()
    revision = _next_revision(conn, file_hash, model_name)

    product_name = product_name_status = None
    recommended_use = use_restrictions = None
    supplier_name = supplier_address = supplier_phone = None
    signal_word = signal_word_status = None
    if parsed is not None:
        pn = parsed.get("product_name") or {}
        product_name, product_name_status = pn.get("value"), pn.get("source_status")
        recommended_use = (parsed.get("recommended_use") or {}).get("value")
        use_restrictions = (parsed.get("use_restrictions") or {}).get("value")
        supplier = parsed.get("supplier") or {}
        supplier_name = supplier.get("company_name")
        supplier_address = supplier.get("address")
        supplier_phone = supplier.get("emergency_phone")
        sw = parsed.get("signal_word") or {}
        signal_word, signal_word_status = sw.get("value"), sw.get("source_status")

    rule_json = json.dumps(rule_result, ensure_ascii=False) if rule_result is not None else None

    with conn:
        cur = conn.execute(
            """
            INSERT INTO msds_documents (
                file_name, file_hash, revision,
                product_name, product_name_status,
                recommended_use, use_restrictions,
                supplier_name, supplier_address, supplier_phone,
                signal_word, signal_word_status,
                model_name, raw_json, rule_json, extracted_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                file_name, file_hash, revision,
                product_name, product_name_status,
                recommended_use, use_restrictions,
                supplier_name, supplier_address, supplier_phone,
                signal_word, signal_word_status,
                model_name, raw_output, rule_json, extracted_at,
            ),
        )
        document_id = cur.lastrowid

        if parsed is not None:
            for i, ing in enumerate(parsed.get("ingredients") or []):
                conn.execute(
                    """
                    INSERT INTO msds_ingredients (
                        document_id, seq, chemical_name, cas_number, ke_number, content, is_substitute_data
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        document_id, i + 1,
                        ing.get("chemical_name"), ing.get("cas_number"), ing.get("ke_number"), ing.get("content"),
                        1 if ing.get("is_substitute_data") else 0,
                    ),
                )
            for c in parsed.get("ghs_classification") or []:
                conn.execute(
                    "INSERT INTO msds_classifications (document_id, hazard_class, category) VALUES (?,?,?)",
                    (document_id, c.get("hazard_class"), c.get("category")),
                )
            for hs in parsed.get("hazard_statements") or []:
                conn.execute(
                    "INSERT INTO msds_hazard_statements (document_id, code, text) VALUES (?,?,?)",
                    (document_id, hs.get("code"), hs.get("text")),
                )

    return document_id


def save_confirmation(
    conn: sqlite3.Connection,
    document_id: int,
    field_path: str,
    extracted_value: Any,
    confirmed_value: Any,
    review_status: Optional[str],
    reason_code: Optional[str],
    confirmed_at: Optional[str] = None,
) -> int:
    """사람이 확정·수정한 값을 msds_reviews에 넣는다. POST /confirm(app/main.py)이 호출한다.
    confirmed_at을 주면 그 값을 쓴다 — 한 번 저장한 여러 행을 같은 시각으로 묶어 "마지막 저장분"을 다시 읽기 위해서."""

    def _ser(v: Any) -> Optional[str]:
        if v is None or isinstance(v, str):
            return v
        return json.dumps(v, ensure_ascii=False)

    confirmed_at = confirmed_at or datetime.now(timezone.utc).isoformat()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO msds_reviews (
                document_id, field_path, extracted_value, confirmed_value,
                review_status, reason_code, confirmed_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (document_id, field_path, _ser(extracted_value), _ser(confirmed_value), review_status, reason_code, confirmed_at),
        )
    return cur.lastrowid


def list_documents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """파일명·제품명·모델·revision 목록. 나중에 GET /documents가 호출할 자리."""
    rows = conn.execute(
        """
        SELECT id, file_name, model_name, revision, product_name, product_name_status,
               signal_word, extracted_at
        FROM msds_documents
        ORDER BY id
        """
    ).fetchall()
    return [dict(r) for r in rows]

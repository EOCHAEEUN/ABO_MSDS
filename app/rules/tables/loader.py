"""
[김건하] app/rules/tables/*.csv 로더 (캐시). 표 내용·출처는 tables/README.md 참고.
"""
from __future__ import annotations

import csv
import functools
from pathlib import Path

_TABLES_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TABLES_DIR.parent.parent.parent  # tables -> rules -> app -> repo root


@functools.lru_cache(maxsize=1)
def load_h_code_phrases() -> dict[str, dict[str, object]]:
    """{h_code: {"phrase": str, "variants": set[str]}}"""
    path = _TABLES_DIR / "h_code_phrases.csv"
    result: dict[str, dict[str, object]] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["h_code"].strip()
            phrase = row["phrase_ko"].strip()
            variants = {v.strip() for v in row["accepted_variants"].split("|") if v.strip()}
            result[code] = {"phrase": phrase, "variants": {phrase} | variants}
    return result


@functools.lru_cache(maxsize=1)
def load_classification_table() -> dict[tuple[str, str], dict[str, object]]:
    """{(hazard_class_norm, category_또는_빈문자열): {"signal_word": str|None, "h_codes": [str,...], "source": str, "note": str}}"""
    path = _TABLES_DIR / "classification_signal_word.csv"
    result: dict[tuple[str, str], dict[str, object]] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["hazard_class_norm"].strip(), row["category"].strip())
            codes = [c.strip() for c in row["expected_h_codes"].split("|") if c.strip()]
            result[key] = {
                "signal_word": row["signal_word"].strip() or None,
                "h_codes": codes,
                "source": row["source"].strip(),
                "note": row["note"].strip(),
            }
    return result


@functools.lru_cache(maxsize=1)
def load_hazard_class_alias() -> dict[str, str]:
    """{원문 hazard_class: 정규 분류명(고시 기준)} — eval/hazard_class_alias.csv 재사용(중복 유지보수 방지)."""
    path = _REPO_ROOT / "eval" / "hazard_class_alias.csv"
    result: dict[str, str] = {}
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            src = (row.get("hazard_class_원문") or "").strip()
            norm = (row.get("정규 분류명(고시 기준)") or "").strip()
            if src and norm:
                result[src] = norm
    return result


def normalize_hazard_class(raw: str) -> str:
    """원문 hazard_class를 정규 분류명으로 바꾼다. 별칭표에 없으면 원문 그대로 반환."""
    alias = load_hazard_class_alias()
    raw = (raw or "").strip()
    return alias.get(raw, raw)

"""
[김건하] 검사 규칙: evidence — 원문 대조로 근거 스니펫을 만들어 최상위 evidence 배열을 채운다.

not_found 검사와 짝을 이룬다: 여기서 만든 locate()/iter_evidence_targets()를 그대로 가져다
쓴다. 이 모듈의 run()은 Finding을 거의 만들지 않는다(원문이 없을 때 정보성 1건만) —
실제 evidence 배열은 engine.py가 build_evidence()를 직접 호출해서 채운다.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..types import CheckContext, EvidenceItem, Finding

_SNIPPET_RADIUS = 40
_SEP_RE = re.compile(r"[∼～–—]")
_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = _SEP_RE.sub("~", text)
    return _WS_RE.sub("", text)


def locate(source_text: Optional[str], value: str) -> tuple[bool, str, Optional[str]]:
    """(found, match_type, snippet)를 반환한다. source_text가 없으면 (False, "not_found", None)."""
    if not source_text or not value:
        return False, "not_found", None

    idx = source_text.find(value)
    if idx >= 0:
        start = max(0, idx - _SNIPPET_RADIUS)
        end = min(len(source_text), idx + len(value) + _SNIPPET_RADIUS)
        return True, "exact", source_text[start:end].strip()

    norm_value = _normalize(value)
    if norm_value and norm_value in _normalize(source_text):
        return True, "normalized", None  # 정규화 좌표는 원문 좌표와 달라 스니펫은 생략

    return False, "not_found", None


def iter_evidence_targets(label: dict) -> list[tuple[str, str]]:
    """원문에서 확인해야 하는 (JSON 경로, 값) 목록."""
    out: list[tuple[str, str]] = []

    def add(path: str, v: Any) -> None:
        if isinstance(v, str) and v.strip():
            out.append((path, v))

    for name in ("product_name", "recommended_use", "use_restrictions"):
        field = label.get(name)
        if isinstance(field, dict):
            add(f"$.{name}.value", field.get("value"))

    supplier = label.get("supplier")
    if isinstance(supplier, dict):
        for key in ("company_name", "address", "emergency_phone"):
            add(f"$.supplier.{key}", supplier.get(key))

    for i, ing in enumerate(label.get("ingredients") or []):
        if not isinstance(ing, dict):
            continue
        add(f"$.ingredients[{i}].chemical_name", ing.get("chemical_name"))
        add(f"$.ingredients[{i}].cas_number", ing.get("cas_number"))
        add(f"$.ingredients[{i}].content", ing.get("content"))

    for i, hs in enumerate(label.get("hazard_statements") or []):
        if isinstance(hs, dict):
            add(f"$.hazard_statements[{i}].text", hs.get("text"))

    return out


def build_evidence(label: dict, source_text: Optional[str]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for path, value in iter_evidence_targets(label):
        found, match_type, snippet = locate(source_text, value)
        items.append(EvidenceItem(field=path, value=value, found=found, match_type=match_type, snippet=snippet))
    return items


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    if not ctx.source_text:
        return [
            Finding(
                check="evidence",
                severity="info",
                code="EVIDENCE_SKIPPED_NO_SOURCE",
                field=None,
                message="원문(source_text)이 없어 근거 대조를 건너뛰었습니다.",
            )
        ]
    return []

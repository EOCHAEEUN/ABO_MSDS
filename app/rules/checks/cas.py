"""
[김건하] 검사 규칙: cas — CAS 형식·체크디지트 재검증.

src/schema.py에도 같은 검증이 있지만(스키마 위반 시 전체가 SCHEMA_ERROR로 묶임),
화면에서 CAS 전용 배지를 띄우려면 별도 사유 코드가 필요해서 여기서 다시 검사한다.
"""
from __future__ import annotations

import re

from ..types import CheckContext, Finding

_CAS_RE = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")


def _checksum_ok(cas: str) -> bool:
    m = _CAS_RE.match(cas)
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum((i + 1) * int(d) for i, d in enumerate(digits)) % 10 == int(m.group(3))


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    for i, ing in enumerate(label.get("ingredients") or []):
        if not isinstance(ing, dict):
            continue
        cas = ing.get("cas_number")
        if not isinstance(cas, str):
            continue
        path = f"$.ingredients[{i}].cas_number"
        if not _CAS_RE.match(cas):
            findings.append(
                Finding(
                    check="cas",
                    severity="error",
                    code="CAS_FORMAT_INVALID",
                    field=path,
                    message=f"CAS 형식이 올바르지 않습니다: {cas!r}",
                    detail={"value": cas},
                )
            )
        elif not _checksum_ok(cas):
            findings.append(
                Finding(
                    check="cas",
                    severity="error",
                    code="CAS_CHECKSUM_INVALID",
                    field=path,
                    message=f"CAS 체크디지트가 올바르지 않습니다: {cas!r}",
                    detail={"value": cas},
                )
            )
    return findings

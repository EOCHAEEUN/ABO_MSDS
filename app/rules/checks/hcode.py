"""
[김건하] 검사 규칙: hcode — H코드 형식 + app/rules/tables/h_code_phrases.csv 등재 여부 검사.
"""
from __future__ import annotations

import re

from ..tables.loader import load_h_code_phrases
from ..types import CheckContext, Finding

_H_RE = re.compile(r"^H\d{3}[A-Za-z]{0,2}(\+H\d{3}[A-Za-z]{0,2})*$")


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    table = load_h_code_phrases()
    for i, hs in enumerate(label.get("hazard_statements") or []):
        if not isinstance(hs, dict):
            continue
        code = hs.get("code")
        if code is None:
            continue  # code가 null인 문구는 정상 케이스(라벨링 규칙 8) — 형식 검사 대상 아님
        if not isinstance(code, str):
            continue
        path = f"$.hazard_statements[{i}].code"
        if not _H_RE.match(code):
            findings.append(
                Finding(
                    check="hcode",
                    severity="error",
                    code="HCODE_FORMAT_INVALID",
                    field=path,
                    message=f"H코드 형식이 올바르지 않습니다: {code!r}",
                    detail={"value": code},
                )
            )
            continue
        if code not in table:
            findings.append(
                Finding(
                    check="hcode",
                    severity="warning",
                    code="HCODE_UNKNOWN_CODE",
                    field=path,
                    message=(
                        f"{code!r}가 app/rules/tables/h_code_phrases.csv에 없습니다. "
                        "새 코드이거나 오탈자일 수 있습니다."
                    ),
                    detail={"value": code},
                )
            )
    return findings

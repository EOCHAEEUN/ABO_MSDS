"""
[김건하] 검사 규칙: not_found — 원문 대조 실패(추출 오류·환각 후보) 표시.

evidence.py의 locate()/iter_evidence_targets()를 그대로 쓴다. source_text가 없으면
아무것도 검사하지 않는다(EVIDENCE_SKIPPED_NO_SOURCE는 evidence 검사가 이미 알린다).
"""
from __future__ import annotations

from ..types import CheckContext, Finding
from .evidence import iter_evidence_targets, locate


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    if not ctx.source_text:
        return []

    findings: list[Finding] = []
    for path, value in iter_evidence_targets(label):
        found, _match_type, _snippet = locate(ctx.source_text, value)
        if not found:
            findings.append(
                Finding(
                    check="not_found",
                    severity="warning",
                    code="VALUE_NOT_FOUND_IN_SOURCE",
                    field=path,
                    message=f"{value!r}이(가) 원문에서 찾아지지 않습니다. 추출 오류나 환각 가능성이 있습니다.",
                    detail={"value": value},
                )
            )
    return findings

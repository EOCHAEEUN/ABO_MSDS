"""
[김건하] 검사 규칙: phrase_to_hcode — code가 있는 유해·위험 문구가 대응표 문구와 일치하는지 검사.

code가 null인 문구는 원문 자체에 코드가 없는 정상 케이스(라벨링 규칙 8, 예: KR-HANIL-003의
"17"처럼 코드가 깨져 나온 경우)이므로 검사하지 않는다.
"""
from __future__ import annotations

import re

from ..tables.loader import load_h_code_phrases
from ..types import CheckContext, Finding

_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    text = _WS_RE.sub("", text or "")
    return text.rstrip(".。")


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    table = load_h_code_phrases()
    for i, hs in enumerate(label.get("hazard_statements") or []):
        if not isinstance(hs, dict):
            continue
        code = hs.get("code")
        text = hs.get("text")
        if not isinstance(code, str) or code not in table or not isinstance(text, str):
            continue
        accepted = {_norm(v) for v in table[code]["variants"]}
        if _norm(text) not in accepted:
            findings.append(
                Finding(
                    check="phrase_to_hcode",
                    severity="error",
                    code="HCODE_PHRASE_MISMATCH",
                    field=f"$.hazard_statements[{i}].text",
                    message=f"H코드 {code}의 문구가 대응표와 다릅니다: {text!r}",
                    detail={
                        "code": code,
                        "expected_variants": sorted(table[code]["variants"]),
                        "actual": text,
                    },
                )
            )
    return findings

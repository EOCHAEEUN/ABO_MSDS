"""
[김건하] 검사 규칙: empty_value — source_status가 '기재'인데 값이 사실상 빈 값(자료없음류)인 경우 검사.

src/schema.py의 ValueField 검증은 "기재인데 value가 None"만 막는다. "기재"이면서
value에 "자료없음"·"-" 같은 문자열이 그대로 들어간 표기 실수는 스키마를 통과하므로
여기서 따로 잡는다.
"""
from __future__ import annotations

from typing import Any

from ..types import CheckContext, Finding

_SENTINELS = {
    "자료없음", "해당없음", "없음", "-", "--", "―", "‐", "미기재", "미상",
    "n/a", "na", "none", "unknown", "not available", "not applicable", "tbd",
}

_VALUE_FIELDS = ("product_name", "recommended_use", "use_restrictions", "signal_word")


def _is_sentinel(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return True
    return text.lower() in _SENTINELS


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    for name in _VALUE_FIELDS:
        field = label.get(name)
        if not isinstance(field, dict):
            continue
        value = field.get("value")
        if field.get("source_status") == "기재" and _is_sentinel(value):
            findings.append(
                Finding(
                    check="empty_value",
                    severity="warning",
                    code="EMPTY_VALUE_SUSPECT",
                    field=f"$.{name}.value",
                    message=(
                        f"{name}이(가) '기재'로 표시됐지만 값이 {value!r}로 사실상 빈 값입니다. "
                        "source_status를 자료없음/해당없음으로 바꿔야 하는지 확인하세요."
                    ),
                    detail={"value": value},
                )
            )
    return findings

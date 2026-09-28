"""
[김건하] 검사 규칙: content_sum — 성분 함유량 "하한" 합계가 100%를 넘는지 검사.

상한 합계는 검사하지 않는다: data/README.md 채점기 구현 메모에 "범위 표기 특성상
27개 문서에서 100%를 넘으니 Rule Engine은 하한 합계만 검사해야 한다"고 명시돼 있다.
"""
from __future__ import annotations

import re

from ..types import CheckContext, Finding

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_TOLERANCE = 0.5  # 반올림 오차 허용


def _parse_lower_bound(content) -> float | None:
    """content 문자열에서 하한값을 읽는다. 숫자가 하나뿐이고 '미만/이하/<'가 있으면 0으로 본다."""
    if not isinstance(content, str) or not content.strip():
        return None
    nums = [float(x) for x in _NUM_RE.findall(content)]
    if not nums:
        return None
    if len(nums) == 1:
        return 0.0 if re.search(r"미만|이하|<", content) else nums[0]
    return min(nums)


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    total = 0.0
    any_value = False

    for i, ing in enumerate(label.get("ingredients") or []):
        if not isinstance(ing, dict):
            continue
        content = ing.get("content")
        if content is None:
            continue
        lb = _parse_lower_bound(content)
        if lb is None:
            findings.append(
                Finding(
                    check="content_sum",
                    severity="warning",
                    code="CONTENT_SUM_UNPARSEABLE",
                    field=f"$.ingredients[{i}].content",
                    message=f"함유량 {content!r}에서 하한값을 읽을 수 없어 합계 검사에서 제외했습니다.",
                    detail={"value": content},
                )
            )
            continue
        total += lb
        any_value = True

    if any_value and total > 100 + _TOLERANCE:
        findings.append(
            Finding(
                check="content_sum",
                severity="error",
                code="CONTENT_SUM_EXCEEDS_100",
                field="$.ingredients",
                message=f"함유량 하한 합계가 {total:.2f}%로 100%를 넘습니다.",
                detail={"lower_bound_sum": round(total, 2)},
            )
        )
    return findings

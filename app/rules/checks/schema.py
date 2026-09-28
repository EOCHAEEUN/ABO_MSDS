"""
[김건하] 검사 규칙: schema — src/schema.py(MSDSLabel)로 필드 단위 구조 검사.

pydantic이 던지는 예외를 그대로 전체 실패로 쓰지 않고, 필드마다 Finding으로 풀어낸다.
다른 8개 검사는 label 원본 dict를 직접 들여다보므로 여기서 막지 않아도 계속 실행된다.
review_status는 engine.py가 이 검사의 error 유무로 SCHEMA_ERROR를 결정한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

_SRC_DIR = Path(__file__).resolve().parents[3] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from schema import MSDSLabel  # noqa: E402

from ..types import CheckContext, Finding  # noqa: E402


def run(label: dict, ctx: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    try:
        MSDSLabel.model_validate(label)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            findings.append(
                Finding(
                    check="schema",
                    severity="error",
                    code="SCHEMA_FIELD_INVALID",
                    field=f"$.{loc}" if loc else "$",
                    message=f"{loc}: {err['msg']}" if loc else err["msg"],
                    detail={"pydantic_type": err.get("type")},
                )
            )
    except Exception as e:  # label이 dict가 아니거나 그 밖의 구조적 문제
        findings.append(
            Finding(
                check="schema",
                severity="error",
                code="SCHEMA_FIELD_INVALID",
                field=None,
                message=f"라벨 구조를 검사할 수 없습니다: {e}",
            )
        )
    return findings

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

_SEP_RE = re.compile(r"[∼～–—]")
_WS_RE = re.compile(r"\s+")
_TOKEN_SPLIT_RE = re.compile(r"[:\s]+")


def _normalize(text: str) -> str:
    text = _SEP_RE.sub("~", text)
    return _WS_RE.sub("", text)


def _last_token(line: str) -> str:
    tokens = [t for t in _TOKEN_SPLIT_RE.split(line.strip()) if t]
    return tokens[-1].rstrip(".)") if tokens else ""


# 이 필드들은 값 줄과 함께 라벨 줄도 원문 그대로 같이 보여준다. 원문이
# "o 신호어 위험"처럼 한 줄이면 그 줄 그대로, "○ 신호어" 다음 줄에 "- 경고"처럼
# 라벨과 값이 줄바꿈으로 떨어져 있으면 라벨 줄을 원문 표기 그대로 앞에 붙여서
# "○ 신호어\n- 경고"로 보여준다 — 지어낸 "라벨: 값" 문자열이 아니라 원문 두 줄이다.
_FIELD_LABELS = {
    "product_name": ("제품명", "상품명"),  # 혼합물 서식은 "상품명"을 씀(예: KR-NEOGEN-002)
    "signal_word": ("신호어",),
}


def _has_label(line: str, label_hints: tuple[str, ...]) -> bool:
    return any(h in line for h in label_hints)


def _preceding_label_line(lines: list[str], value_line_idx: int, label_hints: tuple[str, ...]) -> Optional[str]:
    """value_line_idx 줄 위쪽에서 라벨 힌트가 있는 첫 비어있지 않은 줄을 원문 그대로 찾는다."""
    j = value_line_idx - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j >= 0 and _has_label(lines[j], label_hints):
        return lines[j].strip()
    return None


def locate(
    source_text: Optional[str], value: str, label_hint: Optional[tuple[str, ...]] = None
) -> tuple[bool, str, Optional[str]]:
    """(found, match_type, snippet)를 반환한다. source_text가 없으면 (False, "not_found", None).

    스니펫은 매칭된 위치 앞뒤 고정폭이 아니라 그 줄 전체다. 유해·위험 문구처럼 줄이
    짧고 촘촘한 구간에서 고정폭(문자 수)으로 자르면 옆 줄 내용이 섞여 들어오거나
    단어 중간이 잘리는 문제가 있었다(app/web_results.py가 여러 필드의 스니펫을
    이어붙일 때 겹침·잘림으로 드러남).

    "신호어"의 "경고"처럼 짧은 값은 2항 나. 항목 제목("...경고 표지 항목")처럼 엉뚱한
    곳에 부분 문자열로 먼저 걸릴 수 있다. 그래서 불릿·라벨을 뗀 줄의 "마지막 토큰"이
    정확히 value와 같은 줄("- 경고", "경고.", "신호어: 경고" 등)을 최우선으로 찾고,
    없을 때만 첫 부분 문자열 매칭으로 내려간다. 여러 단어로 된 값(제품명 등)은 이
    조건에 애초에 안 걸리므로 기존 동작 그대로다.

    label_hint가 있는데(product_name·signal_word) 값 줄에 그 라벨이 안 보이면, 바로 위
    줄에서 라벨을 찾아 원문 그대로 앞에 붙인다("○ 신호어" + "- 경고" → 두 줄 그대로).
    """
    if not source_text or not value:
        return False, "not_found", None

    lines = source_text.split("\n")

    def with_label(i: int, value_line: str) -> Optional[str]:
        """라벨까지 붙은 스니펫을 만든다. label_hint가 있는데 라벨을 못 찾으면 None(이 매치는 버림)."""
        if not label_hint:
            return value_line
        if _has_label(value_line, label_hint):
            return value_line
        label_line = _preceding_label_line(lines, i, label_hint)
        return f"{label_line}\n{value_line}" if label_line else None

    # label_hint가 있으면(product_name·signal_word) 같은 값이 문서 안에 여러 번 나올 때
    # 라벨이 붙는 매치를 최우선으로 찾는다. 예: "요소"가 문서 제목으로 한 번, "가. 제품명"
    # 절에서 한 번 나오면 제목 줄이 먼저 걸려도 라벨 있는 쪽을 택한다.
    fallback: Optional[tuple[bool, str, str]] = None
    for i, line in enumerate(lines):
        if _last_token(line) != value:
            continue
        snippet = with_label(i, line.strip())
        if snippet is not None:
            return True, "exact", snippet
        if fallback is None:
            fallback = (True, "exact", line.strip())

    for i, line in enumerate(lines):
        if value not in line:
            continue
        snippet = with_label(i, line.strip())
        if snippet is not None:
            return True, "exact", snippet
        if fallback is None:
            fallback = (True, "exact", line.strip())

    if fallback is not None:
        return fallback

    norm_value = _normalize(value)
    if norm_value and norm_value in _normalize(source_text):
        return True, "normalized", None  # 정규화 좌표는 원문 좌표와 달라 스니펫은 생략

    return False, "not_found", None


def iter_evidence_targets(label: dict) -> list[tuple[str, str, Optional[tuple[str, ...]]]]:
    """원문에서 확인해야 하는 (JSON 경로, 값, 라벨 힌트) 목록. 라벨 힌트는 대부분 None."""
    out: list[tuple[str, str, Optional[tuple[str, ...]]]] = []

    def add(path: str, v: Any, label_hint: Optional[tuple[str, ...]] = None) -> None:
        if isinstance(v, str) and v.strip():
            out.append((path, v, label_hint))

    for name in ("product_name", "recommended_use", "use_restrictions"):
        field = label.get(name)
        if isinstance(field, dict):
            add(f"$.{name}.value", field.get("value"), _FIELD_LABELS.get(name))

    supplier = label.get("supplier")
    if isinstance(supplier, dict):
        for key in ("company_name", "address", "emergency_phone"):
            add(f"$.supplier.{key}", supplier.get(key))

    sw = label.get("signal_word")
    if isinstance(sw, dict):
        add("$.signal_word.value", sw.get("value"), _FIELD_LABELS.get("signal_word"))

    for i, c in enumerate(label.get("ghs_classification") or []):
        if isinstance(c, dict):
            # category("구분 3")는 문서 전체에 똑같은 표기가 반복돼 원문 대조 의미가 없어 뺀다.
            add(f"$.ghs_classification[{i}].hazard_class", c.get("hazard_class"))

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
    for path, value, label_hint in iter_evidence_targets(label):
        found, match_type, snippet = locate(source_text, value, label_hint)
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

"""
[양세윤] + 김건하 — 동결 스키마 정의 + 스키마 준수 검사

스키마 정의는 src/schema.py(Pydantic) 하나뿐이다. 여기서 다시 정의하지 않고 가져다 쓴다.
이 파일은 "모델이 뱉은 문자열 → JSON → 스키마 검사" 두 단계만 맡는다. 채점·서빙 공용.
"""
import json
import re

from pydantic import ValidationError

from src.schema import MSDSLabel  # noqa: F401  (다른 모듈이 core.schema에서 꺼내 쓸 수 있게 재노출)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json)?", re.I)


def extract_json(raw):
    """모델 출력 문자열 → (dict | None, 실패 사유 | None).

    <think> 블록과 ```json 코드펜스는 걷어내고, 앞뒤에 군말이 붙어 있으면
    첫 '{'부터 마지막 '}'까지를 잘라 다시 시도한다. 최상위가 객체가 아니면 실패.
    """
    if raw is None:
        return None, "출력 없음"
    s = _FENCE.sub("", _THINK.sub("", raw)).strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        i, j = s.find("{"), s.rfind("}")
        if i < 0 or j <= i:
            return None, "JSON 객체를 찾지 못함"
        try:
            obj = json.loads(s[i : j + 1])
        except json.JSONDecodeError as e:
            return None, f"JSON 파싱 실패: {e.msg} (pos {e.pos})"
    if not isinstance(obj, dict):
        return None, "최상위가 객체가 아님"
    return obj, None


def check_schema(obj):
    """dict → (통과 여부, 오류 메시지 목록)."""
    try:
        MSDSLabel.model_validate(obj)
        return True, []
    except ValidationError as e:
        return False, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
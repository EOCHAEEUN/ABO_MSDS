"""
[양세윤] + 강덕우 — 시스템 프롬프트, few-shot 조립, enable_thinking=False

학습 JSONL(pipeline/build_jsonl.py)·추론(eval/infer.py)·서빙(app/)이 모두 이 파일만 쓴다.
- 학습 데이터의 system/user 문구와 정답 직렬화(format_target)가 추론 때와 한 글자라도 다르면
  QLoRA 비교가 무의미해진다. build_jsonl.py도 반드시 build_messages()·format_target()을 쓸 것.
- train.jsonl을 만든 뒤에는 이 파일을 고치지 않는다(고치면 JSONL·어댑터를 다시 만들어야 함).

[v1 초안] SYSTEM_PROMPT 문구는 data/README.md 표기 규칙을 옮긴 것이다. 학습 전 강덕우 확인 필요.

프롬프트 버전 (2026-09-29, report/decisions.md)
- v1: SYSTEM_PROMPT. r1 학습 · main의 val 결과가 이 문구다. 한 글자도 바꾸지 않는다(test/test_prompt.py가 해시로 확인).
- v2: v1 + 규칙 10~14(PM 결정). v1을 고치지 않고 뒤에 붙였다. val Base 결과(outputs/prompt_v2/)가 있으므로
  이 문구도 바꾸지 않는다(test/test_prompt.py가 해시로 확인).
- v2_1: v2의 규칙 12(제품명 칸 우선) · 13(원문에 없는 "KE-"를 붙이지 않음)을 고친 것. 10 · 11 · 14는 v2와 같다.
- 문구를 고칠 때는 기존 버전을 바꾸지 않고 새 버전을 추가한다(결과 폴더 · 점수 파일이 버전별로 따로 생긴다).
- 버전마다 결과 폴더를 나눈다(prompt_subdir). v1은 기존 위치 그대로, v2는 그 아래 prompt_v2/ —
  v2 결과가 v1 결과(outputs/ · report/scores.csv · data/train.jsonl)를 덮어쓰지 않게.
"""
import hashlib
import json

# Qwen3 chat template에 넘길 인자. 세 조건(base_zs/base_fs/qlora) 모두 thinking 끔
CHAT_TEMPLATE_KWARGS = {"enable_thinking": False}

SYSTEM_PROMPT = """너는 MSDS(물질안전보건자료) 1~3항 텍스트에서 정보를 뽑아 JSON 하나로만 답하는 추출기다.
설명, 마크다운, 코드블록 없이 JSON 객체만 출력한다.

출력 형식(키 이름과 순서 고정):
{"product_name":{"value":문자열|null,"source_status":상태},
"recommended_use":{"value":문자열|null,"source_status":상태},
"use_restrictions":{"value":문자열|null,"source_status":상태},
"supplier":{"company_name":문자열|null,"address":문자열|null,"emergency_phone":문자열|null},
"ingredients":[{"chemical_name":문자열,"cas_number":문자열|null,"ke_number":문자열|null,"content":문자열|null,"is_substitute_data":true|false}],
"ghs_classification":[{"hazard_class":문자열,"category":문자열|null}],
"signal_word":{"value":"위험"|"경고"|null,"source_status":상태},
"hazard_statements":[{"code":문자열|null,"text":문자열}],
"list_status":{"ingredients":상태,"ghs_classification":상태,"hazard_statements":상태}}

규칙:
1. 주어진 1~3항 안에 적힌 내용만 쓴다. 없는 값을 추측하거나 만들지 않는다.
2. 상태는 "기재", "자료없음", "해당없음" 중 하나다. 원문에 값이 있으면 기재, 원문이 "자료없음"이거나 아무것도 적혀 있지 않으면 자료없음, 원문이 "해당없음"·"분류되지 않음"·"Not applicable"이면 해당없음. 기재가 아니면 value는 null, 목록은 []이다.
3. 값은 원문 표기 그대로 옮긴다. 번역하거나 요약하지 않는다. 아래 정규화만 적용한다.
4. signal_word는 위험 또는 경고로 쓴다(Danger→위험, Warning→경고).
5. ghs_classification은 2항의 제품 분류만 쓴다. 3항 성분별 분류 열은 넣지 않는다. hazard_class는 원문 분류명 그대로, 한 줄에 분류가 둘이면 두 항목으로 나눈다. category는 "구분 N" 형식(예: 구분 2, 구분 1B)이고 괄호 부기와 나열형은 뺀다. 고압가스는 액화가스·압축가스·냉동액화가스·용해가스 중 하나로 쓴다.
6. ingredients는 3항 구성성분 표에서만 뽑는다(2항 NFPA 표의 물질명은 성분이 아니다). 성분 한 행이 한 항목이다. chemical_name은 표의 주 물질명 열을 그대로 쓴다.
7. cas_number에는 CAS 번호만 쓴다. 옆에 붙은 KE 번호는 ke_number에 쓰고, EC·REACH 번호는 버린다. 한 칸에 CAS가 여러 개면 첫 번째만 쓴다. 영업비밀·비공개가 명시된 성분은 is_substitute_data를 true, cas_number를 null로 쓴다.
8. content는 원문 함유량에서 %와 공백만 빼고 그대로 쓴다(예: "80 이상 ~ 90 % 미만" → "80이상~90미만").
9. hazard_statements는 유해·위험 문구(H문구)만 쓴다. 예방조치 문구(P문구)는 넣지 않는다. 원문에 H코드가 없으면 code는 null이고 코드를 추정해서 붙이지 않는다. 문구 끝 마침표는 뺀다."""

SYSTEM_PROMPT_V2 = SYSTEM_PROMPT + """
10. 상태는 그 항목 자리에 적힌 문구로만 판단한다. 항목이나 칸이 비었거나 항목 자체가 없으면 "자료없음"이다. "해당없음"은 그 항목에 "해당없음"·"분류되지 않음"·"라벨 부착 규정 없음"·"없음" 같은 문구가 실제로 있을 때만 쓴다. 다른 항목(예: 그림문자)의 "해당없음"을 분류·신호어·유해·위험 문구의 상태로 옮기지 않는다.
11. hazard_statements는 경고표지 항목의 유해·위험 문구 목록에서만 뽑는다. "분류기준에 포함되지 않는 기타 유해성·위험성" 항목의 문장은 H문구가 아니다.
12. product_name은 1항의 제품명 값이다(제품명·상품명·물질명·제품 설명 칸, 또는 그 제목 바로 아래 줄). "용도"·"권고 용도" 칸의 문구는 product_name이 아니라 recommended_use에 쓴다.
13. ke_number에는 "KE-"로 시작하는 번호만 쓴다. KE 자리에 다른 번호(EC 등)가 있으면 null로 둔다.
14. hazard_class에는 분류명만 쓰고 "구분 N"은 category에 쓴다. "물리적 위험성"·"건강 유해성" 같은 묶음 제목은 항목으로 넣지 않는다. 분류명 옆에 "분류되지 않음"·"해당없음"이 적힌 줄은 분류가 아니므로 넣지 않는다."""

SYSTEM_PROMPT_V2_1 = SYSTEM_PROMPT + """
10. 상태는 그 항목 자리에 적힌 문구로만 판단한다. 항목이나 칸이 비었거나 항목 자체가 없으면 "자료없음"이다. "해당없음"은 그 항목에 "해당없음"·"분류되지 않음"·"라벨 부착 규정 없음"·"없음" 같은 문구가 실제로 있을 때만 쓴다. 다른 항목(예: 그림문자)의 "해당없음"을 분류·신호어·유해·위험 문구의 상태로 옮기지 않는다.
11. hazard_statements는 경고표지 항목의 유해·위험 문구 목록에서만 뽑는다. "분류기준에 포함되지 않는 기타 유해성·위험성" 항목의 문장은 H문구가 아니다.
12. product_name은 1항의 제품명 값이다. 제품명 칸(또는 그 제목 바로 아래 줄)이 있으면 그 값을 쓰고, 없을 때만 상품명·물질명·제품 설명 칸의 값을 쓴다. "용도"·"권고 용도" 칸의 문구는 product_name이 아니라 recommended_use에 쓴다.
13. ke_number에는 원문에 "KE-"로 시작하게 적힌 번호만 그대로 쓴다. 원문에 없는 "KE-"를 붙이지 않는다. KE 자리에 다른 번호(EC 등)가 있으면 null로 둔다.
14. hazard_class에는 분류명만 쓰고 "구분 N"은 category에 쓴다. "물리적 위험성"·"건강 유해성" 같은 묶음 제목은 항목으로 넣지 않는다. 분류명 옆에 "분류되지 않음"·"해당없음"이 적힌 줄은 분류가 아니므로 넣지 않는다."""

PROMPTS = {"v1": SYSTEM_PROMPT, "v2": SYSTEM_PROMPT_V2, "v2_1": SYSTEM_PROMPT_V2_1}
DEFAULT_PROMPT = "v1"  # 서빙 · r1 · 기존 스크립트 기본값. v2는 --prompt v2 / 설정 prompt: v2로만 쓴다
# 버전을 기록하기 전(09-29 이전)의 _run.jsonl은 core/prompt.py 파일 해시만 남겼다. 그 해시 = v1
LEGACY_V1_FILE_SHA256 = "f69f229829e4199aebad4e0aa0d0ee228b3575a2d8bcd54eb076bb78f2e7bb19"


def prompt_subdir(version):
    """버전별 결과 하위 폴더. v1은 ""(기존 위치 그대로), 그 밖은 "prompt_{버전}"."""
    if version not in PROMPTS:
        raise ValueError(f"알 수 없는 프롬프트 버전: {version} (있는 버전: {sorted(PROMPTS)})")
    return "" if version == "v1" else f"prompt_{version}"


def prompt_sha256(version):
    """모델이 실제로 받는 문구(system + user 틀)의 해시. 파일 해시와 달리 다른 버전을 추가해도 바뀌지 않는다."""
    msgs = build_messages("<MSDS 본문>", prompt=version)
    return hashlib.sha256(json.dumps(msgs, ensure_ascii=False).encode("utf-8")).hexdigest()


def recorded_prompt_version(run):
    """_run.jsonl 첫 줄 → 그 폴더를 만든 프롬프트 버전. 버전 기록이 없는 옛 기록은 파일 해시로 판정(모르면 None)."""
    if run.get("prompt_version"):
        return run["prompt_version"]
    return "v1" if run.get("prompt_sha256") == LEGACY_V1_FILE_SHA256 else None


def format_user(doc_text):
    return f"다음 MSDS 1~3항에서 정보를 추출해 JSON으로만 답하라.\n\n<MSDS>\n{doc_text.strip()}\n</MSDS>"


def format_target(label):
    """정답 라벨 dict → assistant 응답 문자열. 학습 정답과 few-shot 예시가 모두 이 형식이다."""
    return json.dumps(label, ensure_ascii=False, separators=(",", ":"))


def build_messages(doc_text, fewshot=(), prompt=DEFAULT_PROMPT):
    """fewshot: [(예시 문서 텍스트, 예시 정답 dict), ...]. zero-shot이면 비워 둔다. prompt: PROMPTS의 버전."""
    if prompt not in PROMPTS:
        raise ValueError(f"알 수 없는 프롬프트 버전: {prompt} (있는 버전: {sorted(PROMPTS)})")
    msgs = [{"role": "system", "content": PROMPTS[prompt]}]
    for ex_text, ex_label in fewshot:
        msgs.append({"role": "user", "content": format_user(ex_text)})
        msgs.append({"role": "assistant", "content": format_target(ex_label)})
    msgs.append({"role": "user", "content": format_user(doc_text)})
    return msgs
"""
[양세윤] + 강덕우 — 시스템 프롬프트, few-shot 조립, enable_thinking=False

학습 JSONL(pipeline/build_jsonl.py)·추론(eval/infer.py)·서빙(app/)이 모두 이 파일만 쓴다.
- 학습 데이터의 system/user 문구와 정답 직렬화(format_target)가 추론 때와 한 글자라도 다르면
  QLoRA 비교가 무의미해진다. build_jsonl.py도 반드시 build_messages()·format_target()을 쓸 것.
- train.jsonl을 만든 뒤에는 이 파일을 고치지 않는다(고치면 JSONL·어댑터를 다시 만들어야 함).

[v1 초안] SYSTEM_PROMPT 문구는 data/README.md 표기 규칙을 옮긴 것이다. 학습 전 강덕우 확인 필요.
"""
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


def format_user(doc_text):
    return f"다음 MSDS 1~3항에서 정보를 추출해 JSON으로만 답하라.\n\n<MSDS>\n{doc_text.strip()}\n</MSDS>"


def format_target(label):
    """정답 라벨 dict → assistant 응답 문자열. 학습 정답과 few-shot 예시가 모두 이 형식이다."""
    return json.dumps(label, ensure_ascii=False, separators=(",", ":"))


def build_messages(doc_text, fewshot=()):
    """fewshot: [(예시 문서 텍스트, 예시 정답 dict), ...]. zero-shot이면 비워 둔다."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for ex_text, ex_label in fewshot:
        msgs.append({"role": "user", "content": format_user(ex_text)})
        msgs.append({"role": "assistant", "content": format_target(ex_label)})
    msgs.append({"role": "user", "content": format_user(doc_text)})
    return msgs
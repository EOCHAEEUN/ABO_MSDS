"""
[강덕우] 성분·분류·H코드·함유량이 바뀐 변형 검출

원칙: 원본 텍스트에서 찾을 수 있던 정답 값은 변형 텍스트에서도 찾을 수 있어야 한다.
(원본에서도 못 찾는 값 — 셀 안 줄바꿈 등 — 은 비교 대상에서 뺀다. 변형 탓이 아니므로)
의도한 내용 변형(mutators.py)은 바뀐 라벨을 넘기고, 사라져야 할 값은 gone= 으로 넘긴다.

  problems = check(orig_text, new_text, new_label, gone=["1310-73-2"])
  빈 목록이면 통과.
"""
import re

H_CODE = re.compile(r"\bH\d{3}\b")


def _flat(s):
    return re.sub(r"\s+", "", s or "")


def label_values(label):
    """라벨에서 원문을 그대로 옮긴 값들 → [(필드 이름, 값)]"""
    out = []
    for key in ("product_name", "recommended_use", "use_restrictions"):
        v = (label.get(key) or {}).get("value")
        if v:
            out.append((key, v))
    for i, c in enumerate(label.get("ingredients", [])):
        for f in ("chemical_name", "cas_number", "ke_number"):
            if c.get(f):
                out.append((f"ingredients[{i}].{f}", c[f]))
        # 함유량은 숫자만 본다("80이상~90미만" ↔ 원문 "80 이상 ~ 90 % 미만")
        for n in re.findall(r"\d+(?:\.\d+)?", c.get("content") or ""):
            out.append((f"ingredients[{i}].content", n))
    for i, g in enumerate(label.get("ghs_classification", [])):
        out.append((f"ghs[{i}].hazard_class", g["hazard_class"]))
    for i, h in enumerate(label.get("hazard_statements", [])):
        if h.get("code"):
            for code in H_CODE.findall(h["code"]):
                out.append((f"hazard[{i}].code", code))
        out.append((f"hazard[{i}].text", h["text"]))
    return out


def check(orig_text, new_text, new_label, gone=()):
    fo, fn = _flat(orig_text), _flat(new_text)
    problems = []
    for where, v in label_values(new_label):
        fv = _flat(v)
        if fv and fv in fo and fv not in fn:
            problems.append(f"{where} 값이 변형 텍스트에서 사라짐: {v!r}")
    for v in gone:
        if _flat(v) in fn:
            problems.append(f"지워야 할 값이 남아 있음: {v!r}")
    # 라벨에 code가 하나도 없는데 텍스트에 H코드가 남아 있으면 모델이 배울 신호가 모순된다
    codes = {h.get("code") for h in new_label.get("hazard_statements", [])}
    if new_label.get("hazard_statements") and codes == {None} and H_CODE.search(new_text):
        problems.append("라벨은 H코드 없음인데 텍스트에 H코드가 남아 있음")
    return problems

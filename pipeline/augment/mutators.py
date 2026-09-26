"""
[강덕우] 내용 변형 — train의 약점 두 유형을 보강한다 (data/README.md "train의 약점").

텍스트와 라벨을 같은 규칙으로 함께 바꾼다. 라벨 규칙은 data/README.md 그대로:
  · 영업비밀 성분 → cas_number null, is_substitute_data true (2건뿐)
  · H코드 없는 문구 → code null, 문구만 (2건뿐)

각 변형: (text, label, rng) -> (new_text, new_label, gone) | None
  gone: 변형 텍스트에서 사라져야 하는 값(check_forbidden에 넘김). 적용할 수 없으면 None.
"""
import copy
import re

H_CODE = re.compile(r"\bH\d{3}\b")
SECRET_CAS = ["영업비밀", "영업비밀", "비공개", "자료없음(영업비밀)", "Trade Secret"]


def secret_ingredient(text, label, rng):
    """CAS가 텍스트에 한 번만 나오는 성분 하나를 골라 CAS 칸을 영업비밀로 가린다.
    붙어 있는 KE 번호도 같이 가린다. 성분명은 둔다(실제 문서에도 이름만 쓰고 CAS를 가린 경우가 많다)."""
    cands = [i for i, c in enumerate(label["ingredients"])
             if c.get("cas_number") and not c["is_substitute_data"] and text.count(c["cas_number"]) == 1
             and (not c.get("ke_number") or text.count(c["ke_number"]) <= 1)]
    if not cands:
        return None
    i = rng.choice(cands)
    c = label["ingredients"][i]
    word = rng.choice(SECRET_CAS)
    # "9003-55-8 / KE-13258" 처럼 붙은 KE 까지 한 덩어리로 가린다
    pat = re.escape(c["cas_number"])
    if c.get("ke_number"):
        pat += r"(?:\s*/?\s*" + re.escape(c["ke_number"]) + ")?"
    new_text = re.sub(pat, word, text, count=1)
    gone = [c["cas_number"]]
    if c.get("ke_number"):
        new_text = new_text.replace(c["ke_number"], "")
        gone.append(c["ke_number"])
    new = copy.deepcopy(label)
    new["ingredients"][i].update(cas_number=None, ke_number=None, is_substitute_data=True)
    return new_text, new, gone


def drop_h_codes(text, label, rng):
    """유해·위험문구 앞의 H코드를 모두 지우고 문구만 남긴다. 라벨 code는 전부 null."""
    hs = label.get("hazard_statements", [])
    if not hs or not any(h.get("code") for h in hs):
        return None
    # "H302+H332", "H302 + H332", "H302:" 까지 한 덩어리로 지운다
    new_text = re.sub(r"\bH\d{3}(?:[ \t]*\+[ \t]*H\d{3})*[ \t]*[:：\-]?[ \t]*", "", text)   # 줄바꿈은 남긴다
    if H_CODE.search(new_text):
        return None
    new = copy.deepcopy(label)
    for h in new["hazard_statements"]:
        h["code"] = None
    gone = sorted({c for h in hs if h.get("code") for c in H_CODE.findall(h["code"])})
    return new_text, new, gone


MUTATORS = {
    "secret": secret_ingredient,
    "nohcode": drop_h_codes,
}

"""
[강덕우] 내용 변형 — train에 적은 유형을 보강한다 (docs/plan.md 3.4 "보강 대상").

텍스트와 라벨을 같은 규칙으로 함께 바꾼다. 라벨 규칙은 docs/plan.md 2절 그대로:
  · 영업비밀 성분 → cas_number null, ke_number null, is_substitute_data true
  · H코드 없는 문구 → code null, 문구만
어떤 유형이 적은지는 train · val 라벨로만 판단한다(build_jsonl.py 보고서의 유형별 집계).
train에만 쓴다. val · test에는 쓰지 않는다.

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


def _ec_number(rng):
    """형식·체크디짓이 맞는 EC 번호(NNN-NNN-R). R = Σ(i × d_i) mod 11, 10이 나오면 다시 뽑는다."""
    while True:
        d = [rng.randint(2, 9)] + [rng.randint(0, 9) for _ in range(5)]
        r = sum((i + 1) * x for i, x in enumerate(d)) % 11
        if r < 10:
            return f"{''.join(map(str, d[:3]))}-{''.join(map(str, d[3:]))}-{r}"


def add_ec_column(text, label, rng):
    """성분표의 CAS 뒤에 EC 번호 칸을 끼워 넣는다. 라벨은 그대로(EC는 버리는 값, ke_number는 KE만).

    EC 칸 형식: "CAS EC 함유량" — CAS 바로 뒤(KE가 붙어 있으면 KE 뒤)에 온다.
    기본값은 끔(build_jsonl.py --ecnum). 켜는 조건: plan 2절 "EC · REACH 번호는 담지 않음" 규칙이 동결돼 있고,
    새 train 라벨 집계에서 EC 칸 문서가 부족할 때(docs/augmentation_guide.md 3절).
    """
    cands = [c for c in label["ingredients"] if c.get("cas_number") and text.count(c["cas_number"]) == 1]
    if not cands:
        return None
    new_text = text
    for c in cands:
        pat = re.escape(c["cas_number"])
        if c.get("ke_number"):
            pat += r"(?:\s*/?\s*" + re.escape(c["ke_number"]) + ")?"
        new_text = re.sub(pat, lambda m: f"{m.group(0)} {_ec_number(rng)}", new_text, count=1)
    # 표 머리에 CAS 칸 이름이 있으면 EC 칸 이름도 붙인다
    new_text = re.sub(r"(CAS\s*번호(?:\s*또는\s*식별번호)?)", r"\1 EC번호", new_text, count=1)
    return new_text, label, ()


MUTATORS = {
    "secret": secret_ingredient,
    "nohcode": drop_h_codes,
    "ecnum": add_ec_column,
}

"""
[강덕우] 텍스트 겉모양만 바꾸는 렌더러 6종 — 정답 라벨은 그대로 둔다.

generate_msds.py 원본이 저장소에 없어 같은 역할로 새로 썼다. 렌더러는 한 번에 하나만 적용한다
(난수 조합 없음). 값이 들어 있는 글자는 건드리지 않는다: 줄 앞 표지·항 제목·콜론 주변 공백·
항 사이 머리글·CAS 칸 이름만 바꾼다. 결과는 check_forbidden.check()로 다시 검사한다.
스타일은 train 문서에서 본 표기와 plan 3.4 증강표에 있는 것만 쓴다(test 문서 표기를 흉내 내지 않는다).

각 렌더러: (text, rng: random.Random) -> text
"""
import re

BULLETS = ["◦", "○", "-", "•", "·", "▶", "※", ""]
_BULLET_LINE = re.compile(r"^(\s*)([◦○•·▶※\-]|[ㅇo](?=\s))\s*")

# 1~3항 제목. 앞 번호 표기만 바꾸고 제목 글자는 그대로 둔다
_SECTION = re.compile(r"^\s*(?:제\s*)?([123])\s*(?:항)?\s*[.)]?\s*(?=(?:화학\s*제품|유해|구성\s*성분))")
SECTION_STYLES = ["{n}. ", "{n}) ", "제{n}항 ", "【{n}】 ", "{n}.", "SECTION {n}. "]

# 하위 항목 번호: "가. " "나) " "1) " "(1) "
_SUB_HANGUL = re.compile(r"^(\s*)([가나다라마바사아자차카타파하])\s*[.)]\s*")
_SUB_DIGIT = re.compile(r"^(\s*)\(?(\d{1,2})\)\s*")
HANGUL = "가나다라마바사아자차카타파하"
# "{d}. "는 넣지 않는다 — "3. 공급사 정보"가 3항 제목처럼 보인다
SUB_STYLES = ["{h}. ", "{h}) ", "({h}) ", "{d}) ", "({d}) "]

# "제품명 : 값" 의 콜론. 앞에 한글 라벨이 있을 때만 바꾼다(시각 "10:30" 같은 숫자 사이는 안 건드림)
_COLON = re.compile(r"(?<=[가-힣)])[ \t]*[:：][ \t]*")   # 줄바꿈은 먹지 않는다
COLON_STYLES = [" : ", ": ", ":", " ： ", " - "]

PAGE_HEADERS = [
    "물질안전보건자료(MSDS)", "Page {p} of {t}", "페이지 {p} / {t}", "- {p} -",
    "MSDS번호 : AA{num}", "개정일자 : 2024.0{m}.1{p}", "{p}/{t}",
]


def bullets(text, rng):
    """줄 앞 불릿 기호를 하나로 통일해서 바꾼다."""
    b = rng.choice(BULLETS)
    rep = (b + " ") if b else ""
    return "\n".join(_BULLET_LINE.sub(lambda m: m.group(1) + rep, ln) for ln in text.split("\n"))


def section_headers(text, rng):
    """'1. 화학제품과 …' → '제1항 화학제품과 …' 등."""
    style = rng.choice(SECTION_STYLES)
    return "\n".join(_SECTION.sub(lambda m: style.format(n=m.group(1)), ln) for ln in text.split("\n"))


def sub_numbering(text, rng):
    """하위 번호 체계를 바꾼다. 한글 순번(가나다)과 숫자 순번을 서로 바꿀 수 있다."""
    style = rng.choice(SUB_STYLES)

    def fmt(ind, idx):
        return ind + style.format(h=HANGUL[idx % len(HANGUL)], d=idx + 1)

    out = []
    for ln in text.split("\n"):
        m = _SUB_HANGUL.match(ln)
        if m and ln[m.end():m.end() + 1] not in ("", " "):
            ln = fmt(m.group(1), HANGUL.index(m.group(2))) + ln[m.end():]
        else:
            m = _SUB_DIGIT.match(ln)
            # 숫자 뒤에 곧바로 한글 라벨이 오는 줄만(함유량 "1) 30~40" 같은 오탐 방지)
            if m and re.match(r"[가-힣]", ln[m.end():m.end() + 1] or " ") and int(m.group(2)) <= 14:
                ln = fmt(m.group(1), int(m.group(2)) - 1) + ln[m.end():]
        out.append(ln)
    return "\n".join(out)


def colons(text, rng):
    """라벨 뒤 콜론 표기를 바꾼다. 괄호 안 콜론은 값의 일부라 두다("급성 독성(흡입: 가스)")."""
    style = rng.choice(COLON_STYLES)

    def inside_paren(s):
        depth = 0
        for ch in s:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth:   # "3) 급성 독성" 의 번호 괄호처럼 짝 없는 ")"는 무시
                depth -= 1
        return depth > 0

    def one_line(ln):
        return _COLON.sub(lambda m: m.group(0) if inside_paren(ln[:m.start()]) else style, ln)

    return "\n".join(one_line(ln) for ln in text.split("\n"))


def page_headers(text, rng):
    """항 제목 줄 앞에 PDF 머리글·쪽번호 같은 잡음 줄을 끼운다(실제 쪽 넘김 흉내)."""
    t = rng.randint(3, 12)
    lines, out, p = text.split("\n"), [], 1
    for ln in lines:
        if _SECTION.match(ln) and out:
            p += 1
            h = rng.choice(PAGE_HEADERS).format(p=p, t=t, num=rng.randint(10**9, 10**10 - 1), m=rng.randint(1, 9))
            out.append(h)
        out.append(ln)
    return "\n".join(out)


def cas_labels(text, rng):
    """CAS 칸 이름 표기를 바꾼다(plan 3.4 "라벨 표기"). 뒤에 오는 CAS 값과 "또는 식별번호" 같은 부기는 그대로."""
    style = rng.choice(CAS_LABEL_STYLES)
    return _CAS_LABEL.sub(style, text)


# "CAS번호" "CAS 번호" "CAS No." "CAS NO.:" "CAS Registry No." — 콜론은 뒤에 남긴다
_CAS_LABEL = re.compile(r"\bCAS[ \t]*(?:Registry[ \t]*)?(?:No\.?|NO\.?|번호|Number)", re.I)
CAS_LABEL_STYLES = ["CAS No.", "CAS 번호", "CAS NO.", "CAS번호", "CAS Registry No."]


RENDERERS = {
    "bullet": bullets,
    "section": section_headers,
    "subnum": sub_numbering,
    "colon": colons,
    "pagehdr": page_headers,
    "caslabel": cas_labels,
}

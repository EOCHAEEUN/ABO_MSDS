# 저장 위치: <프로젝트 루트>/scripts/compare_norm.py
"""라벨 대조(scripts/compare.py) 전용 정규화. 순수 함수만 — 파일 입출력·인자 파싱 없음.

채점기용 정규화(core/normalize.py)와 목적이 달라 따로 둔다.
  · core/normalize.py : 모델 출력 채점. 스키마 필드 단위, 상태값은 list_status로 따로 본다.
  · 이 파일            : 사람↔사람·사람↔모델 라벨 대조. 원문 값 문자열을 느슨하게 맞추고,
                         "자료없음"·"해당없음"·"-"(미판정)을 값으로 구분한다.

두 층을 구분한다.
  strict : 저장·표시용. 사람이 읽었을 때 원문에 가깝다.
  loose  : 비교 전용 키. 의미가 같으면 같은 문자열이 되도록 최대한 깎는다.
비교는 loose로 하고, 리포트에는 원본을 보여준다 — "무엇이 달랐는지"를 원문과 대조할 수 있게.
"""
import re
import unicodedata

# ── 값 없음 ─────────────────────────────────────────────────────────────
# 고용노동부고시 제11조제7항: 정보를 얻을 수 없으면 "자료 없음",
# 적용이 불가능하거나 대상이 되지 않으면 "해당 없음". 뜻이 다르므로 합치지 않는다.
NO_DATA = {"자료없음", "자료없음.", "데이터없음", "정보없음", "nodata", "nodataavailable"}
NOT_APPLICABLE = {"해당없음", "해당없음.", "해당사항없음", "na", "n/a", "notapplicable"}
UNDECIDED = "미판정"          # 원문이 "-"·빈칸이라 둘 중 어느 쪽인지 알 수 없음

# 구간 구분자. 물결표 변형과 하이픈·대시 계열을 모두 받는다.
RANGE_SEP = "[~∼～〜‐-―\\-]"

BULLET = re.compile(r"^[\s\-–—•○◦▷▶※*·]+")
LABEL = re.compile(
    r"^\s*(?:[가-힣]\s*[.)]\s*)?"
    r"(?:\d+\s*[.)]\s*)?"
    r"(?:제품\s*명|제품\s*설명|화학제품명|신\s*호\s*어|"
    r"유해[·.ㆍ]?\s*위험\s*문구|유해/위험\s*문구|"
    r"유해성\s*[·.ㆍ]?\s*위험성\s*분류|유해[·.ㆍ]?\s*위험성\s*분류)"
    r"\s*[:：]?\s*"
)
TRAIL_DOT = re.compile(r"[.。]\s*$")


def _nfkc(s):
    return unicodedata.normalize("NFKC", s or "")


def norm_strict(s):
    """저장용. 불릿·라벨을 떼고 공백만 고른다. 글자는 바꾸지 않는다."""
    s = _nfkc(s).replace(" ", " ")
    s = BULLET.sub("", s)
    s = LABEL.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def blank_kind(s):
    """값 없음 표기를 판정한다. 값이면 None을 돌려준다."""
    k = re.sub(r"\s+", "", norm_strict(s)).lower()
    if k in NO_DATA:
        return "자료없음"
    if k in NOT_APPLICABLE:
        return "해당없음"
    if k in {"", "-", "--", "–", "—"}:
        return UNDECIDED
    return None


def norm_loose(s):
    """일반 텍스트 비교 키. 공백·구분자·마침표를 지운다.

    '인화성 액체 구분 2' 와 '인화성 액체 : 구분2' 가 같은 키가 된다.
    """
    b = blank_kind(s)
    if b:
        return b
    s = norm_strict(s)
    s = TRAIL_DOT.sub("", s)
    s = re.sub(r"[‐-―]", "-", s)
    # 구분자로 쓰인 하이픈만 제거한다. 'H225 - 문구'는 떼고 'n-butyl'은 남긴다.
    s = re.sub(r"\s*-\s+|\s+-\s*", " ", s)
    s = re.sub(r"[\s:：;/·ㆍ,]+", "", s)
    return s.lower()


def norm_amount(s):
    """함유량 전용. '50 이상 ~ 60 % 미만', '99 - 100', '28∼38' → '50~60' 꼴."""
    b = blank_kind(s)
    if b:
        return b
    s = norm_strict(s)
    s = re.sub(r"이상|이하|초과|미만|퍼센트|%|％", " ", s)
    s = re.sub(r"\s*" + RANGE_SEP + r"\s*", "~", s)
    return re.sub(r"\s+", "", s).strip("~")


def norm_cas(s):
    """CAS 전용. 공백 제거. 식별번호가 붙어 있으면 CAS 쪽만 취한다."""
    b = blank_kind(s)
    if b:
        return b
    s = re.sub(r"\s+", "", norm_strict(s))
    m = re.search(r"\d{2,7}-\d{2}-\d", s)
    return m.group(0) if m else s.lower()


def norm_ke(s):
    """KE 전용. 괄호를 떼고 KE-xxxxx 만 취한다."""
    b = blank_kind(s)
    if b:
        return b
    s = re.sub(r"\s+", "", norm_strict(s)).upper()
    m = re.search(r"KE-?\d{3,6}", s)
    return m.group(0).replace("KE", "KE-").replace("KE--", "KE-") if m else s.lower()


def cas_checkdigit(cas):
    """CAS 체크디짓 검증. 형식이 아니면 None(판정 불가)."""
    m = re.fullmatch(r"(\d{2,7})-(\d{2})-(\d)", (cas or "").strip())
    if not m:
        return None
    digits = (m.group(1) + m.group(2))[::-1]
    total = sum(int(d) * (i + 1) for i, d in enumerate(digits))
    return total % 10 == int(m.group(3))

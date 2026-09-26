"""
[양세윤 v1] + 김건하 — 신호어·구분 N 정규화, content min/max 파싱, 별칭표 연동

채점(eval/score.py)·Rule Engine·서빙이 모두 이 파일 하나만 import한다.
정답과 모델 출력 양쪽에 똑같이 적용해야 하므로, 여기 말고 다른 곳에서 정규화하지 않는다.
"""
import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALIAS_CSV = ROOT / "eval" / "hazard_class_alias.csv"

# 별칭표에서 정규 분류명이 이 접두어로 시작하면 GHS 분류가 아님(예: 미국 OSHA Simple Asphyxiant)
NON_GHS_PREFIX = "(GHS 외"

_WS = re.compile(r"\s+")
_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—−"})


def squash(s):
    """공백·줄바꿈 전부 제거. None은 None."""
    if s is None:
        return None
    return _WS.sub("", str(s))


def _key(s):
    """비교용 키: NFKC + 공백 제거 + 소문자."""
    return squash(unicodedata.normalize("NFKC", s)).lower()


# ---------------------------------------------------------------- 제품명
_PARENS = re.compile(r"\([^()]*\)|\[[^\[\]]*\]|（[^（）]*）")
_NAME_PUNCT = re.compile(r"[,，、;·ㆍ]")


def norm_product_name(v):
    """제품명 비교 키. 정답·출력에는 원문(괄호 포함)을 그대로 두고, 비교할 때만 깎는다(2026-09-26 합의).

    괄호 부기("(2종)", "(경화제)", "(CHLORINE)")와 쉼표류, 공백을 뺀다.
    "레미픽스 에폭시(친환경, 주제)" == "레미픽스 에폭시", "HI EF425TV HI 425TVL" == "HI EF425TV, HI 425TVL"
    """
    if v is None:
        return None
    s = unicodedata.normalize("NFKC", str(v))
    prev = None
    while prev != s:  # 중첩 괄호는 안쪽부터 벗긴다
        prev, s = s, _PARENS.sub("", s)
    return squash(_NAME_PUNCT.sub("", s)).lower()


# ---------------------------------------------------------------- 신호어
_SIGNAL = {"위험": "위험", "경고": "경고", "danger": "위험", "warning": "경고"}


def norm_signal_word(v):
    if v is None:
        return None
    s = squash(v)
    return _SIGNAL.get(s.lower(), s)


# ---------------------------------------------------------------- CAS
def norm_cas(v):
    """공백 제거 + 여러 종류의 대시를 '-'로. 빈 문자열은 None."""
    if v is None:
        return None
    s = squash(unicodedata.normalize("NFKC", str(v)).translate(_DASHES))
    return s or None


# ---------------------------------------------------------------- 함유량
_NUM = re.compile(r"\d+(?:\.\d+)?")
_UPPER_ONLY = ("<", "≤", "미만", "이하")
_LOWER_ONLY = (">", "≥", "이상", "초과")


def parse_content(v):
    """함유량 문자열 → (min, max). 못 읽으면 None.

    - 범위 구분자(~ ∼ ～ - –)·부등호(< <= > >= ≥ ≤)·"이상/미만"은 모두 무시하고 숫자 두 개를 min/max로 본다.
      "80이상~90미만" == "80~90" == ">=80-<90" (경계 포함 여부는 비교하지 않음)
    - 숫자가 하나면: "<1"·"1미만" → (0, 1) / ">93"·"≥90" → (93, 100) / "15" → (15, 15)
    """
    if v is None:
        return None
    s = squash(unicodedata.normalize("NFKC", str(v)).replace("%", ""))
    nums = [float(x) for x in _NUM.findall(s)]
    if len(nums) == 2:
        lo, hi = sorted(nums)
        return (lo, hi)
    if len(nums) == 1:
        n = nums[0]
        if any(t in s for t in _UPPER_ONLY):
            return (0.0, n)
        if any(t in s for t in _LOWER_ONLY):
            return (n, 100.0)
        return (n, n)
    return None


def content_equal(a, b, tol=1e-6):
    """min/max가 같으면 같은 함유량. 둘 다 null이면 같음. 한쪽이라도 못 읽으면 공백 제거 문자열 비교."""
    if a is None or b is None:
        return a is None and b is None
    pa, pb = parse_content(a), parse_content(b)
    if pa is None or pb is None:
        return squash(str(a)) == squash(str(b))
    return abs(pa[0] - pb[0]) <= tol and abs(pa[1] - pb[1]) <= tol


# ---------------------------------------------------------------- GHS 구분
_KO_GAS = {"냉동액화가스", "액화가스", "압축가스", "용해가스"}
_EN_GAS = (  # 긴 것부터 검사(refrigerated liquefied ⊃ liquefied)
    ("refrigeratedliquefiedgas", "냉동액화가스"),
    ("liquefiedgas", "액화가스"),
    ("compressedgas", "압축가스"),
    ("dissolvedgas", "용해가스"),
)
_CAT_WORD = re.compile(r"구분|category|cat\.?", re.I)
_CAT_NUM = re.compile(r"(\d)([a-c])?", re.I)


def norm_category(v):
    """'구분 N' 형식으로. "구분2"·"Category 2"·"Cat. 2" → "구분 2", "구분1(1A/1B/1C)" → "구분 1",
    "Liquefied gas" → "액화가스". 해석이 안 되면 공백 제거한 원문을 돌려준다."""
    if v is None:
        return None
    s = unicodedata.normalize("NFKC", str(v))
    s = re.sub(r"\(.*?\)", "", s)  # 괄호 부기·나열형 제거
    q = squash(s)
    if not q or q in {"-", "—"}:
        return None
    if q in _KO_GAS:
        return q
    ql = q.lower()
    for en, ko in _EN_GAS:
        if en in ql:
            return ko
    if "류" in q or "형" in q:  # 폭발물 1.1류, 자기반응성 A형 등은 번호 규칙 밖
        return q
    m = _CAT_NUM.search(_CAT_WORD.sub("", q))
    if m:
        return f"구분 {m.group(1)}{(m.group(2) or '').upper()}"
    return q


# ---------------------------------------------------------------- GHS 분류명(별칭표)
@lru_cache(maxsize=1)
def _alias_table():
    table = {}
    with open(ALIAS_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # 헤더
        for row in reader:
            if not row or not row[0].strip():
                continue
            if row[0].startswith("["):  # "[category 특수값]" 절부터는 분류명 표가 아님
                break
            raw, canon = row[0], (row[1] if len(row) > 1 else "")
            if not canon.strip():
                continue
            table[_key(raw)] = canon.strip()
            table.setdefault(_key(canon), canon.strip())  # 정규명을 그대로 쓴 출력도 인식
    return table


def canon_hazard_class(raw):
    """원문 분류명 → (정규 분류명, 별칭표에 있었는지). 표에 없으면 원문을 그대로 돌려준다."""
    if raw is None:
        return None, False
    table = _alias_table()
    k = _key(raw)
    if k in table:
        return table[k], True
    return str(raw).strip(), False


def class_key(canon):
    """정규 분류명의 비교 키(공백·대소문자 무시)."""
    return _key(canon) if canon is not None else None


def is_non_ghs(canon):
    return bool(canon) and canon.startswith(NON_GHS_PREFIX)


# ---------------------------------------------------------------- 유해·위험 문구
def split_hcodes(code):
    """"H302+H332" → ["H302", "H332"]. 결합 문구는 개별 코드로 쪼개서 채점한다."""
    if not code:
        return []
    s = squash(unicodedata.normalize("NFKC", str(code))).upper()
    return [p for p in s.split("+") if p]


def norm_statement_text(t):
    """H코드 없는 문구 비교용: NFKC + 공백 제거 + 끝 마침표 제거(라벨링 규칙과 동일)."""
    if t is None:
        return None
    return squash(unicodedata.normalize("NFKC", str(t))).rstrip(".。")
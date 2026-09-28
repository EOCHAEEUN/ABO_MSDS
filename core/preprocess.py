"""
[양세윤 v1 → 강덕우 확정]
pdfplumber 추출 → 4항 제목 전 절단 → 2항 안에서만 P문구 블록 제거
- 국문·구서식·영문 4항 패턴, 국문·영문 P문구 패턴
- 제거 전후 2항의 H코드 개수가 다르면 제거 취소 후 FALLBACK
- NOT_FOUND 문서는 자동 투입 금지, _cut_log.csv에 기록

학습 JSONL·평가·서빙이 모두 이 파일 하나로 입력을 만든다. 패턴을 바꾸면 이미 만든 data/text/와
학습 데이터가 어긋나므로, 학습 시작 뒤에는 고치지 않는다.
패턴은 train·val 문서에서만 실측해 정했다(test 문서를 보고 패턴을 고치지 않는다).
굵은 글씨 겹침 복원(undouble)은 pipeline/extract_text.py가 preprocess() 전에 한다.
"""
import re

# ---------------------------------------------------------------- 항목 제목
# (이름, 정규식). 줄 단위로 검사한다. 글자가 겹쳐 뽑힌 제목("응응급급")도 잡도록 +를 쓴다.
SECTION2_PATTERNS = [
    ("KO_2", re.compile(r"^\s*2\s*[.:)\-–]?\s*유+\s*해+|^\s*2\s*[.:)\-–]?\s*위+\s*험+")),
    ("EN_2", re.compile(r"^\s*2\s*[.:)\-–]?\s*Hazards?\b", re.I)),
    ("EN_SECTION2", re.compile(r"^\s*SECTION\s*2\b", re.I)),
]
SECTION3_PATTERNS = [
    ("KO_3", re.compile(r"^\s*3\s*[.:)\-–]?\s*구+\s*성+")),
    ("EN_3", re.compile(r"^\s*3\s*[.:)\-–]?\s*Composition", re.I)),
    ("EN_SECTION3", re.compile(r"^\s*SECTION\s*3\b", re.I)),
]
SECTION4_PATTERNS = [
    ("KO_4", re.compile(r"^\s*4\s*[.:)\-–]?\s*응+\s*급+\s*[조처]+\s*치+")),   # 4. 응급조치 요령 / 4 . 응급조치요령 / 4: 응급처치
    ("KO_4_JE", re.compile(r"^\s*제\s*4\s*항")),
    ("EN_4", re.compile(r"^\s*4\s*[.:)\-–]?\s*first[\s\-]*aid", re.I)),
    ("EN_SECTION4", re.compile(r"^\s*SECTION\s*4\b", re.I)),
]

# ---------------------------------------------------------------- P문구 블록
# 시작: "예방조치 문구" 라벨 줄. 부모 제목("…문구를 포함한 경고 표지 항목")과
#       P문구 문장("모든 안전 예방조치 문구를 읽고…")은 시작이 아니다 → 줄 앞쪽에 라벨로 올 때만 인정.
P_START_PATTERNS = [
    ("KO_P", re.compile(
        r"^\s*(?:[○◦oO•●▶\-]\s*|\d+\)\s*|\d+(?:\.\d+)*\.?\s*)?예\s*방\s*조\s*치\s*문\s*구\s*(?:\(GHS\s*KR\))?\s*(?:[:：]|-|$|(?:예방|대응|저장|폐기)\b)")),
    ("EN_P", re.compile(
        r"^\s*(?:[•\-]\s*|\d+(?:\.\d+)*\.?\s*)?Precautionary\s+statements?\b(?!.*including)", re.I)),
]
# 끝: 2항의 다음 소항목(다. 기타 유해성 / Other hazards) 또는 3항 제목
P_END_PATTERNS = [
    ("KO_DA", re.compile(r"^\s*다\s*[.)]")),
    ("KO_OTHER", re.compile(r"^\s*(?:[○◦\-•]\s*)?기\s*타\s*유\s*해")),
    ("EN_OTHER", re.compile(r"^\s*(?:2\.3\.?|[Cc][.)])?\s*(?:Other\s+hazards|Hazards\s+not\s+otherwise\s+classified)", re.I)),
    ("EN_23", re.compile(r"^\s*2\.3\b")),
]
_H_RE = re.compile(r"(?<![A-Za-z])H\d{3}")
_P_RE = re.compile(r"(?<![A-Za-z])P\d{3}")
# pdfplumber가 자간 때문에 코드를 "H 412", "P 264"처럼 떼어 뽑는 경우가 있다 → 붙인다
_SPACED_CODE = re.compile(r"(?<![A-Za-z])([HP]) (\d{3})(?!\d)")


def join_spaced_codes(text):
    """"H 412" → "H412". 한 칸 띄어진 H·P 코드만 붙인다."""
    return _SPACED_CODE.sub(r"\1\2", text or "")


def find_first(patterns, lines, start=0):
    """patterns 중 하나에 처음 맞는 줄 → (줄 번호, 패턴 이름). 없으면 (None, None)."""
    for i in range(start, len(lines)):
        for name, rx in patterns:
            if rx.search(lines[i]):
                return i, name
    return None, None


def get_h_codes(text):
    """H코드 집합. "H302+H332"는 두 코드로, EUH401은 제외."""
    return set(_H_RE.findall(text or ""))


def cut_to_section3(text):
    """4항 제목 앞까지 자른다 → (자른 텍스트, 4항 패턴 이름). 못 찾으면 (None, None).
    목차 등에 먼저 나오는 4항 제목에 걸리지 않도록, 3항 제목이 있으면 그 뒤에서 찾는다."""
    lines = text.splitlines()
    i3, _ = find_first(SECTION3_PATTERNS, lines)
    i4, name = find_first(SECTION4_PATTERNS, lines, start=(i3 + 1) if i3 is not None else 0)
    if i4 is None:
        return None, None
    return "\n".join(lines[:i4]).rstrip() + "\n", name


def remove_p_block(text):
    """2항 안의 P문구 블록을 지운다 → (결과 텍스트, 정보).
    정보: 제거한 패턴 이름 / "NONE"(라벨 없음) / "ABORTED_H_LOSS: H…"(지우면 H코드가 사라져 취소)."""
    lines = text.splitlines(keepends=True)
    plain = [l.rstrip("\n") for l in lines]
    i2, _ = find_first(SECTION2_PATTERNS, plain)
    i3, _ = find_first(SECTION3_PATTERNS, plain, start=(i2 + 1) if i2 is not None else 0)
    lo = i2 if i2 is not None else 0
    hi = i3 if i3 is not None else len(plain)
    s, name = find_first(P_START_PATTERNS, plain[:hi], start=lo)
    if s is None:
        return text, "NONE"
    e, _ = find_first(P_END_PATTERNS, plain[:hi], start=s + 1)
    e = e if e is not None else hi
    removed = "".join(lines[s:e])
    lost = get_h_codes(removed)
    if lost:
        return text, "ABORTED_H_LOSS: " + ",".join(sorted(lost))
    return "".join(lines[:s] + lines[e:]), name


def preprocess(raw):
    """원문 텍스트 → dict(status, text, section4_pattern, p_block_pattern, h_code_before, h_code_after, note).
    status는 SUCCESS 또는 NOT_FOUND. NOT_FOUND면 text는 None(모델에 넣지 않음)."""
    raw = join_spaced_codes(raw)
    cut, s4 = cut_to_section3(raw)
    if cut is None:
        return dict(status="NOT_FOUND", text=None, section4_pattern=None, p_block_pattern=None,
                    h_code_before=len(get_h_codes(raw)), h_code_after=0,
                    note="4항 제목을 찾지 못함 — 원문 수동 확인 필요(자동 투입 금지)")
    before = len(get_h_codes(cut))
    out, info = remove_p_block(cut)
    after = len(get_h_codes(out))
    notes = []
    if info.startswith("ABORTED"):
        notes.append(f"P블록 제거 취소({info}) — P문구가 입력에 남음")
    elif info == "NONE" and _P_RE.search(cut):
        notes.append("P문구 라벨을 못 찾아 P문구가 입력에 남음")
    if before != after:  # remove_p_block이 막으므로 정상이라면 일어나지 않는다
        notes.append(f"H코드 수 변화 {before}→{after}")
    return dict(status="SUCCESS", text=out,
                section4_pattern=s4, p_block_pattern=None if info == "NONE" or info.startswith("ABORTED") else info,
                h_code_before=before, h_code_after=after, note="; ".join(notes))

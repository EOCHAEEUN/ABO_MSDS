"""
[양세윤 v1 → 강덕우 확정]
pdfplumber 추출 → 4항 제목 전 절단 → 2항 안에서만 P문구 블록 제거
- 국문·구서식·영문 4항 패턴, 국문·영문 P문구 패턴
- 제거 전후 2항의 H코드 개수가 다르면 제거 취소 후 FALLBACK
- NOT_FOUND 문서는 자동 투입 금지, _cut_log.csv에 기록
"""

# 저장 위치: <프로젝트 루트>/core/preprocess.py
"""MSDS 입력 전처리 — 순수 함수만 둔다.

원칙: 원문 내용을 바꾸지 않는다. 모델이 읽을 범위와 형식만 정리한다.
  - CAS/H코드/분류/함유량을 고치거나 보완하지 않는다.
  - 값 정규화("Warning" -> "경고" 등)는 normalize.py 담당이며 여기서 하지 않는다.

파일 입출력이 없으므로 PDF 없이 문자열만으로 테스트할 수 있다.
패턴 상수는 scripts/scan_patterns.py로 실문서 48건을 훑어 확정한 값으로 채운다.
"""
import re

# ---------------------------------------------------------------- 패턴 상수
# 항목 제목. 위에서 아래로 먼저 맞는 것을 쓴다.
SECTION2_PATTERNS = [
    r"^\s*2\s*[.\)]?\s*유해\s*[·ㆍ‧.]?\s*위험성",
    r"^\s*2\s*[.\)]?\s*유해성\s*[·ㆍ‧.]?\s*위험성",
    r"^\s*제?\s*2\s*항\s*유해",
    r"^\s*SECTION\s*2\b",
    r"^\s*2\s*[.\)\-–]?\s+Hazard",
]
SECTION3_PATTERNS = [
    r"^\s*3\s*[.\)]?\s*구성\s*성?분",
    r"^\s*제?\s*3\s*항\s*구성",
    r"^\s*SECTION\s*3\b",
    r"^\s*3\s*[.\)\-–]?\s+Composition",
]
SECTION4_PATTERNS = [
    r"^\s*4\s*[.\):]?\s*응급\s*[조처]치",
    r"^\s*제?\s*4\s*항\s*응급",
    r"^\s*SECTION\s*4\b",
    r"^\s*4\s*[.\)\-–]?\s+First\s*[-\s]?aid",
]

# P문구 블록 시작 — 반드시 "단독 라벨 줄"만 잡는다.
# "나. 예방조치 문구를 포함한 경고 표지 항목" 같은 부모 제목에 걸리면
# 신호어·유해위험문구까지 삭제 대상이 되므로 줄 끝($)을 요구한다.
P_BLOCK_START = [
    r"^\s*[○◦\-•▷*\s]*예방\s*조치\s*문구\s*[:：]?\s*$",
    r"^\s*[○◦\-•▷*\s]*예방\s*조치\s*문구\s*[:：]?\s*P\d{3}",
    r"^\s*[○◦\-•▷*\s]*Precautionary\s+statements?\s*[:：]?\s*$",
    # 구서식의 번호 라벨: "4) 예방조치문구" — 뒤에 글자가 더 붙으면($ 위반) 걸리지 않는다
    r"^\s*\d\s*[.\)]\s*예방\s*조치\s*문구\s*[:：]?\s*$",
]
# P문구 블록의 끝 = 다음 소제목. 2항 범위를 넘지 않는 선에서 탐색한다.
P_BLOCK_END = [
    r"^\s*[다라마]\s*[.\)]",
    r"기타\s*유해",
    r"^\s*NFPA",
    r"^\s*3\s*[.\)]",
    r"^\s*SECTION\s*3\b",
]
# 유해·위험 문구 라벨 — 삭제 후에도 반드시 살아 있어야 한다(구서식 안전장치).
HAZARD_LABEL_PATTERNS = [
    r"유해\s*[·ㆍ‧.]?\s*위험\s*문구",
    r"유해\s*/\s*위험\s*문구",
    r"Hazard\s+statements?",
]

H_CODE = re.compile(r"\bH\d{3}\b", re.IGNORECASE)


# ---------------------------------------------------------------- 기본 도구
def find_first(patterns, lines, start=0, end=None):
    """patterns 중 먼저 걸리는 (줄 번호, 사용 패턴). 없으면 (None, None)."""
    end = len(lines) if end is None else end
    for i in range(start, min(end, len(lines))):
        for pat in patterns:
            if re.search(pat, lines[i], re.IGNORECASE):
                return i, pat
    return None, None


def get_h_codes(text: str) -> set:
    """H코드 집합. 조합(H302+H312)도 개별 코드로 분해해 손실 추적에 쓴다.

    주의: 출력 스키마에서는 조합을 하나의 코드로 유지한다. 이 함수는
    전처리 안전장치 전용이다.
    """
    return {c.upper() for c in H_CODE.findall(text)}


def has_hazard_label(text: str) -> bool:
    """'유해·위험 문구' 라벨이 남아 있는가. H코드가 없는 구서식용 안전장치."""
    return find_first(HAZARD_LABEL_PATTERNS, text.splitlines())[0] is not None


# ---------------------------------------------------------------- 1) 범위 절단
def cut_to_section3(text: str):
    """4항 이후를 제거한다.

    반환: (잘린 텍스트, 사용 패턴). 4항 경계를 못 찾으면 (원문, None).
    호출부는 패턴이 None이면 NOT_FOUND로 처리하고 모델에 투입하지 않는다.
    """
    lines = text.splitlines()
    idx, pat = find_first(SECTION4_PATTERNS, lines)
    if idx is None:
        return text, None
    return "\n".join(lines[:idx]), pat


# ---------------------------------------------------------------- 2) P문구 제거
def remove_p_block(text: str):
    """2항 범위 안에서만 예방조치문구(P문구) 블록을 제거한다.

    반환: (텍스트, 결과 코드)
      - 제거 성공: (제거된 텍스트, 사용한 시작 패턴)
      - 제거 안 함: (원문, 사유 코드)
          NO_P_BLOCK                  2항 안에 P문구 블록 없음
          SECTION2_BOUNDARY_NOT_FOUND 2항/3항 경계를 못 찾음
          ABORTED_H_LOSS:H226,H336    삭제 시 H코드가 사라짐
          ABORTED_LABEL_LOSS          삭제 시 유해·위험 문구 라벨이 사라짐
    """
    lines = text.splitlines()
    s2, _ = find_first(SECTION2_PATTERNS, lines)
    if s2 is None:
        return text, "SECTION2_BOUNDARY_NOT_FOUND"
    s3, _ = find_first(SECTION3_PATTERNS, lines, start=s2 + 1)
    if s3 is None:
        s3 = len(lines)  # 4항 절단 후 문서 끝이 3항인 경우

    start, pat = find_first(P_BLOCK_START, lines, start=s2, end=s3)
    if start is None:
        return text, "NO_P_BLOCK"

    end, _ = find_first(P_BLOCK_END, lines, start=start + 1, end=s3)
    end = s3 if end is None else end

    cut = "\n".join(lines[:start] + lines[end:])

    lost = get_h_codes(text) - get_h_codes(cut)
    if lost:
        return text, "ABORTED_H_LOSS:" + ",".join(sorted(lost))
    if has_hazard_label(text) and not has_hazard_label(cut):
        return text, "ABORTED_LABEL_LOSS"
    return cut, pat


# ---------------------------------------------------------------- 3) 한 번에
def preprocess(text: str) -> dict:
    """절단 + P문구 제거를 한 번에 수행하고 판정에 필요한 값을 모두 돌려준다."""
    h_before = get_h_codes(text)
    cut, s4 = cut_to_section3(text)
    if s4 is None:
        return {
            "status": "NOT_FOUND", "text": None, "raw_text": text,
            "section4_pattern": None, "p_block_pattern": None,
            "h_code_before": len(h_before), "h_code_after": 0,
            "note": "4항 경계 미발견 — 수동 확인 필요",
        }

    final, p_info = remove_p_block(cut)
    note = ""
    if p_info in ("NO_P_BLOCK", "SECTION2_BOUNDARY_NOT_FOUND") or str(p_info).startswith("ABORTED"):
        note, p_info_out = p_info, None
    else:
        p_info_out = p_info

    return {
        "status": "SUCCESS", "text": final, "raw_text": text,
        "section4_pattern": s4, "p_block_pattern": p_info_out,
        "h_code_before": len(h_before), "h_code_after": len(get_h_codes(final)),
        "note": note,
    }
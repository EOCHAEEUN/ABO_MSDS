
"""전처리 테스트 5종 — 실제 수집 문서의 문장을 그대로 썼다.

실행: python -m pytest tests/test_preprocess.py -v
      (pytest 없으면) python tests/test_preprocess.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.preprocess import cut_to_section3, get_h_codes, preprocess, remove_p_block

# 01 현행 국문 (한국피셔과학 아세톤 국문판 형태)
DOC_01 = """안전보건자료
1. 화학제품과 회사에 관한 정보
제품 설명: Acetone
CAS 번호 67-64-1
2. 유해· 위험성
유해성ㆍ위험성 분류
물리적 위험성 인화성 액체 구분 2
건강 유해성 심한 눈 손상성/눈 자극성 구분 2
신호어 위험
유해/위험 문구
H225 - 고인화성 액체 및 증기
H319 - 눈에 심한 자극을 일으킴
예방조치문구
P210 - 열, 고온 표면, 스파크로부터 멀리할 것
P240 - 용기와 수용설비를 접지하시오
P280 - 보호장갑을 착용하시오
기타 유해성· 위험성
반복노출시 피부 건조를 일으킬 수 있음
3. 구성성분의 명칭 및 함유량
성분 일반명 CAS 번호 함유량(%)
아세톤 2-Propanone 67-64-1 99 - 100
4. 응급조치 요령
눈 접촉 즉시 다량의 물로 씻어내시오
5. 폭발· 화재시 대처방법
"""

# 02 국문 부모 제목 (노루페인트 베란다용 페인트) — 가장 중요한 케이스
DOC_02 = """물질안전보건자료(MSDS)
1. 화학제품과 회사에 관한 정보
 가. 제품명 : 순&수 베란다용 페인트 (소프트화이트)
2. 유해 위험성
 가. 유해 위험성 분류
 수생 환경유해성 만성 구분3
 나. 예방조치 문구를 포함한 경고 표지 항목
  ○ 그림문자
  ○ 신호어 : 경고
  ○ 유해 위험 문구 :
   H412 장기적 영향에 의해 수생생물에게 유해함
   H302 삼키면 유해함
  ○ 예방조치 문구
   - 예방
   P273 환경으로 배출하지 마시오.
   P201 사용 전 취급 설명서를 확보하시오.
   - 대응
   P301+P310 삼켰다면: 즉시 의료기관의 도움을 받으시오.
 다. 유해. 위험성 분류기준에 포함되지 않는 기타 유해 위험성
  NFPA지수 자료없음
3. 구성성분의 명칭 및 함유량
화학물질명 관용명 CAS번호 함유량(%)
물 Water 7732-18-5 36∼46
영업비밀 - - 10∼20
4. 응급조치 요령
 가. 눈에 들어갔을때 : 물로 15분 이상 헹구시오
"""

# 03 영문 SDS (Alfa Aesar 아세톤)
DOC_03 = """Safety Data Sheet
1 Identification
Product name: Acetone
CAS Number: 67-64-1
2 Hazard(s) identification
Classification of the substance or mixture
Flam. Liq. 2 H225 Highly flammable liquid and vapor.
Eye Irrit. 2 H319 Causes serious eye irritation.
Signal word Danger
Hazard statements
H225 Highly flammable liquid and vapor.
H319 Causes serious eye irritation.
Precautionary statements
P210 Keep away from heat/sparks/open flames.
P261 Avoid breathing dust/fume/gas/mist/vapours/spray.
P405 Store locked up.
3 Composition/information on ingredients
CAS# Description: 67-64-1 Acetone
4 First-aid measures
After inhalation Supply fresh air.
"""

# 04 구서식 — H코드가 원래 없다 (노루케미칼 에폭시 신나)
DOC_04 = """[물질안전보건자료(MSDS)] (이 자료는 산업안전보건법 제 41 조에 의거 작성된 것임)
1. 화학제품과 회사에 관한 정보
가.제품명 : 에폭시 신나(하절용) DR-100(S)
2. 유해성·위험성
가. 유해성·위험성 분류 : 인화성액체 2 ▷급성독성물질 경피 3 ▷발암성물질 1A
나. 예방조치 문구를 포함한 경고 표지 항목
2) 신호어 : 위험
3) 유해·위험문구 : 고인화성 액체 또는 증기 ▷피부와 접촉하면 유독함 ▷암을 일으킬 수 있음
4) 예방조치문구
 - 예방 : 열·스파크·화염·고열로부터 멀리하시오 - 금연
 - 대응 : 피부에 묻으면 다량의 비누 및 물로 씻어내시오.
다. 유해성·위험성 분류기준에 포함되지 않는 기타 유해성·위험성
물질명 NFPA 지수
3. 구성성분의 명칭 및 함유량
화학물질명 이 명 CAS 번호 함유량(%)
톨루엔 Toluene 108-88-3 9∼19
4. 응급조치요령
가.눈에 들어갔을때 : 15 분 이상 행구시오.
"""

# 05 4항 없음 — 자동 투입 금지
DOC_05 = """물질안전보건자료
1. 화학제품과 회사에 관한 정보
제품명 : 테스트 제품
2. 유해성·위험성
신호어 : 경고
3. 구성성분의 명칭 및 함유량
물 7732-18-5 100
"""


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    return cond


def test_01_current_korean():
    r = preprocess(DOC_01)
    assert r["status"] == "SUCCESS"
    assert "4. 응급조치 요령" not in r["text"], "4항이 남아 있다"
    assert "P210" not in r["text"] and "P280" not in r["text"], "P문구가 남아 있다"
    assert get_h_codes(r["text"]) == {"H225", "H319"}, "H코드 손실"
    assert "신호어 위험" in r["text"]
    assert r["h_code_before"] == r["h_code_after"] == 2


def test_02_parent_label_must_survive():
    """'예방조치 문구를 포함한 경고 표지 항목'을 P블록 시작으로 오인하면 안 된다."""
    r = preprocess(DOC_02)
    assert r["status"] == "SUCCESS"
    assert "나. 예방조치 문구를 포함한 경고 표지 항목" in r["text"], "부모 제목이 삭제됐다"
    assert "○ 신호어 : 경고" in r["text"], "신호어가 삭제됐다"
    assert get_h_codes(r["text"]) == {"H412", "H302"}, "H코드 손실"
    assert "P273" not in r["text"] and "P301" not in r["text"], "P문구가 남아 있다"
    assert r["p_block_pattern"] is not None, "P블록 제거가 수행되지 않았다"
    assert "4. 응급조치 요령" not in r["text"]


def test_03_english_sds():
    r = preprocess(DOC_03)
    assert r["status"] == "SUCCESS"
    assert "First-aid" not in r["text"], "4항이 남아 있다"
    assert "P210" not in r["text"] and "P405" not in r["text"], "P문구가 남아 있다"
    assert get_h_codes(r["text"]) == {"H225", "H319"}
    assert "Signal word Danger" in r["text"]


def test_04_old_format_no_h_code():
    """H코드가 0개여도 정상. 대신 유해·위험문구 줄이 살아 있어야 한다."""
    r = preprocess(DOC_04)
    assert r["status"] == "SUCCESS"
    assert r["h_code_before"] == 0 and r["h_code_after"] == 0
    assert "고인화성 액체 또는 증기" in r["text"], "문구가 삭제됐다"
    assert "2) 신호어 : 위험" in r["text"]
    assert "4. 응급조치요령" not in r["text"]


def test_05_no_section4():
    r = preprocess(DOC_05)
    assert r["status"] == "NOT_FOUND"
    assert r["text"] is None, "NOT_FOUND인데 모델 입력이 생성됐다"
    assert "수동 확인" in r["note"]


def test_06_h_loss_safeguard():
    """P블록 끝을 못 찾아 H코드까지 지워질 상황이면 제거를 포기한다."""
    broken = """2. 유해성·위험성
유해·위험 문구
예방조치문구
P210 열로부터 멀리하시오
H225 고인화성 액체 및 증기
3. 구성성분의 명칭 및 함유량
"""
    out, info = remove_p_block(broken)
    assert out == broken, "H코드가 사라지는데 삭제가 수행됐다"
    assert info.startswith("ABORTED_H_LOSS"), info
    assert "H225" in info


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__} — {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)
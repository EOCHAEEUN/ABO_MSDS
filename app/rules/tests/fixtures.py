"""
[김건하] 가짜 라벨·가짜 원문 fixture. 실제 문서가 아니라 검사 로직 검증용으로 만든 값이다.

CAS 두 개(64-17-5 에탄올, 67-56-1 메탄올)는 실제로 체크디지트가 맞는 값을 그대로 썼다
(가짜 물질명에 진짜 CAS를 붙인 것 — cas 검사가 형식·체크디지트만 보므로 문제없다).
"""
from __future__ import annotations

import copy

BASE_LABEL: dict = {
    "product_name": {"value": "테스트케미칼-100", "source_status": "기재"},
    "recommended_use": {"value": "테스트용 시약", "source_status": "기재"},
    "use_restrictions": {"value": None, "source_status": "자료없음"},
    "supplier": {
        "company_name": "가짜화학(주)",
        "address": "가짜시 가짜구 1",
        "emergency_phone": "02-000-0000",
    },
    "ingredients": [
        {
            "chemical_name": "테스트물질에이",
            "cas_number": "64-17-5",
            "ke_number": None,
            "content": "60~70",
            "is_substitute_data": False,
        },
        {
            "chemical_name": "테스트물질비",
            "cas_number": "67-56-1",
            "ke_number": None,
            "content": "30~40",
            "is_substitute_data": False,
        },
    ],
    "ghs_classification": [
        {"hazard_class": "인화성 액체", "category": "구분 2"},
    ],
    "signal_word": {"value": "위험", "source_status": "기재"},
    "hazard_statements": [
        {"code": "H225", "text": "고인화성 액체 및 증기"},
    ],
    "list_status": {
        "ingredients": "기재",
        "ghs_classification": "기재",
        "hazard_statements": "기재",
    },
}

BASE_SOURCE_TEXT = """
1. 화학제품과 회사에 관한 정보
가. 제품명 : 테스트케미칼-100
나. 권고 용도 : 테스트용 시약
다. 공급자 정보 : 가짜화학(주), 가짜시 가짜구 1, 02-000-0000
2. 유해성·위험성
가. 분류 : 인화성 액체 구분2
나. 신호어 : 위험
- H225 고인화성 액체 및 증기
3. 구성성분의 명칭 및 함유량
테스트물질에이 64-17-5 60~70
테스트물질비 67-56-1 30~40
"""


def clean_label() -> dict:
    return copy.deepcopy(BASE_LABEL)

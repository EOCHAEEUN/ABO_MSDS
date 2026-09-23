"""MSDS 1~3항 추출 결과 스키마 (v5 동결 스키마).

정답 라벨과 모델 출력에 같은 모델을 쓸 수 있다.
- 키 이름·자료형·상태 값을 검사한다.
- CAS 번호는 형식과 체크디지트까지 검사한다.
- 원문 대조(근거 매칭)와 review_status 판정은 여기서 하지 않는다(Rule Engine 몫).
"""
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# 고시 작성원칙: 정보를 얻을 수 없으면 "자료없음", 적용 불가·대상 아님이면 "해당없음"
Status = Literal["기재", "자료없음", "해당없음"]

CAS_RE = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")
# 국내 기존화학물질 번호(참고 필드, 채점 안 함)
KE_RE = re.compile(r"^KE-\d{5}$")
# H코드: H225, H302+H332 같은 조합, H360FD 같은 EU 확장 표기 허용
H_RE = re.compile(r"^H\d{3}[A-Za-z]{0,2}(\+H\d{3}[A-Za-z]{0,2})*$")
# 구분 N: 구분 1, 구분 1A, 구분 2B ...
CATEGORY_RE = re.compile(r"^구분 \d[A-C]?$")
# 구분 번호로 정규화할 수 없는 원문 값(고압가스 등). 필요하면 여기에 추가
CATEGORY_SPECIAL = {"액화가스", "압축가스", "냉동액화가스", "용해가스"}  # 고압가스 구분(영문도 한국어로 정규화)


def cas_checksum_ok(cas: str) -> bool:
    m = CAS_RE.match(cas)
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum((i + 1) * int(d) for i, d in enumerate(digits)) % 10 == int(m.group(3))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueField(_Strict):
    value: Optional[str]
    source_status: Status

    @model_validator(mode="after")
    def _value_matches_status(self):
        if self.source_status == "기재" and not self.value:
            raise ValueError("source_status가 기재인데 value가 비어 있음")
        if self.source_status != "기재" and self.value is not None:
            raise ValueError(f"source_status가 {self.source_status}이면 value는 null이어야 함")
        return self


class SignalWord(ValueField):
    @field_validator("value")
    @classmethod
    def _normalized(cls, v):
        if v is not None and v not in ("위험", "경고"):
            raise ValueError(f"신호어는 위험/경고로 정규화해야 함: {v!r}")
        return v


class Supplier(_Strict):
    company_name: Optional[str]
    address: Optional[str]
    emergency_phone: Optional[str]


class Ingredient(_Strict):
    chemical_name: str
    cas_number: Optional[str]
    ke_number: Optional[str]  # 참고 필드: 1~3항에 KE 번호가 있을 때만, 채점하지 않음
    content: Optional[str]
    is_substitute_data: bool

    @field_validator("cas_number")
    @classmethod
    def _cas(cls, v):
        if v is None:
            return v
        if not CAS_RE.match(v):
            raise ValueError(f"CAS 형식 오류: {v!r}")
        if not cas_checksum_ok(v):
            raise ValueError(f"CAS 체크디지트 오류: {v!r}")
        return v

    @field_validator("ke_number")
    @classmethod
    def _ke(cls, v):
        if v is not None and not KE_RE.match(v):
            raise ValueError(f"KE 번호 형식 오류: {v!r}")
        return v

    @model_validator(mode="after")
    def _substitute(self):
        if self.is_substitute_data and self.cas_number is not None:
            raise ValueError("영업비밀(대체자료) 성분은 cas_number가 null이어야 함")
        return self


class GHSItem(_Strict):
    hazard_class: str
    category: Optional[str]

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v is None or CATEGORY_RE.match(v) or v in CATEGORY_SPECIAL:
            return v
        raise ValueError(f"category는 '구분 N' 형식이어야 함: {v!r}")


class HazardStatement(_Strict):
    code: Optional[str]
    text: str

    @field_validator("code")
    @classmethod
    def _code(cls, v):
        if v is not None and not H_RE.match(v):
            raise ValueError(f"H코드 형식 오류: {v!r}")
        return v


class ListStatus(_Strict):
    ingredients: Status
    ghs_classification: Status
    hazard_statements: Status


class MSDSLabel(_Strict):
    product_name: ValueField
    recommended_use: ValueField
    use_restrictions: ValueField
    supplier: Supplier
    ingredients: List[Ingredient]
    ghs_classification: List[GHSItem]
    signal_word: SignalWord
    hazard_statements: List[HazardStatement]
    list_status: ListStatus

    @model_validator(mode="after")
    def _lists_match_status(self):
        for name in ("ingredients", "ghs_classification", "hazard_statements"):
            items = getattr(self, name)
            status = getattr(self.list_status, name)
            if status == "기재" and not items:
                raise ValueError(f"{name}: list_status가 기재인데 목록이 비어 있음")
            if status != "기재" and items:
                raise ValueError(f"{name}: list_status가 {status}이면 목록이 비어 있어야 함")
        return self

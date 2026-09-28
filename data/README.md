# MSDS 1~3항 정답 라벨 세트 v1 (data/)

팀 ABO · MSDS 구조화 추출 미니 프로젝트 · 2026-09-23

실문서 50건(국문 43 · 영문 7)의 1~3항을 사람이 직접 라벨링한 정답 데이터입니다. 모든 값은 PDF 원문과 대조했고, 텍스트 추출이 헷갈리는 표는 페이지 이미지로 다시 확인했습니다.

## 기준

- **스키마:** 기획서 v5 동결 스키마에 두 가지를 바꿨습니다. 상태값을 한국어(기재·자료없음·해당없음)로 바꿨고, 성분마다 `ke_number` 참고 필드를 추가했습니다.
- **라벨링 규칙:** 작업명세서의 라벨링 공통 규칙 10개를 따랐습니다(1~3항만 본다, 원문 표기 유지, P문구 제외, 코드 추정 금지 등).
- **상태값 근거:** 고시 작성원칙("관련 정보를 얻을 수 없으면 자료없음, 적용 불가·대상 아님이면 해당없음")을 따랐습니다.

## 폴더 구조 (저장소 기준)

```
data/
  labels/{doc_id}.json      재시작 정답 45건(train 35 + val 10)
  splits.csv                문서별 split 배정(train · val만, test는 저장소 밖)
  sources.csv               문서 목록: 원본 파일명, 언어, 서식, 제조사, split_group
  labeling_rules.md         라벨링 규칙
  text/                     전처리 결과 {doc_id}.txt, _cut_log.csv
  train.jsonl · val.jsonl   증강 학습셋(pipeline/build_jsonl.py), build_report.json
  README.md                 이 문서
  raw/                      원본 PDF (git 제외)
eval/
  fewshot.json              few-shot 예시 2건(train)
  hazard_class_alias.csv    분류명 원문 → 고시 기준 정규 분류명
archive/                    09-23 옛 라벨(labels_0923 · val_en_0923) — 재시작에서 쓰지 않음
docs/labeling_review_notes.md   판정 결과, 원문 모순 문서, PDF 추출 함정, 문서별 메모
src/schema.py                   Pydantic 스키마 (정답 라벨·모델 출력·FastAPI 공용)
scripts/validate_labels.py      폴더 단위 스키마 검사 (파싱률·스키마 준수율 출력)
scripts/check_splits.py         splits.csv 분할 규칙 검사
```

doc_id는 `KR|EN-제조사약칭-번호` 형식입니다.

## 라벨 예시 (KR-KUMHO-001, 일부)

```json
{
  "product_name": {"value": "SOL-6220E", "source_status": "기재"},
  "use_restrictions": {"value": null, "source_status": "자료없음"},
  "ingredients": [
    {"chemical_name": "스타이렌-부타디엔 고무", "cas_number": "9003-55-8", "ke_number": "KE-13258",
      "content": "78.5~81.5", "is_substitute_data": false}
  ],
  "ghs_classification": [{"hazard_class": "흡인 유해성", "category": "구분 1"}],
  "signal_word": {"value": "위험", "source_status": "기재"},
  "hazard_statements": [{"code": "H304", "text": "삼켜서 기도로 유입되면 치명적일 수 있음"}],
  "list_status": {"ingredients": "기재", "ghs_classification": "기재", "hazard_statements": "기재"}
}
```

## 표기 규칙

| 대상 | 규칙 |
|---|---|
| 상태값 | 원문에 값 있음 → `기재` / 원문 "자료없음" 또는 **원문에 아무것도 없음** → `자료없음` / 원문 "해당없음" → `해당없음`. `기재`가 아니면 value는 null, 리스트는 빈 배열 |
| content | 원문 범위 문자열에서 `%`와 공백만 제거. 구분자(`~` `∼` `–` `-`)와 부등호는 원문 그대로 (예: "80 이상 ~ 90 % 미만" → `80이상~90미만`, ">= 10 - < 15" → `>=10-<15`) |
| cas_number | CAS 번호만. 한 행 = 성분 1건이며, 한 칸에 CAS가 여러 개면 첫 번째 CAS. "9003-55-8 / KE-13258"처럼 붙은 KE 번호는 `ke_number`로 분리. CAS 칸이 비었거나 "Mixture·혼합물·—" 같은 값이면 null |
| ke_number | 1~3항에 적힌 KE 번호만 기록(15항 법규 정보의 KE는 제외). 없으면 null. **채점하지 않는 참고 필드** |
| is_substitute_data | 영업비밀·비공개가 명시된 성분만 true(이때 cas_number는 null). CAS가 없을 뿐 비공개 표시가 없으면 false |
| category | `구분 N`으로 정규화. 1A·1B·2A 등 확정 세부구분은 유지, "구분1(1A/1B/1C)" 같은 나열형과 "(호흡기 자극)" 같은 괄호 부기는 제거. 고압가스는 `액화가스` 등 가스 상태명 그대로(영문도 한국어로) |
| hazard_class | 원문 분류명 그대로. 영문도 원문 영어 그대로 두고 `hazard_class_alias.csv`로 정규화 |
| signal_word | 국문·영문 모두 `위험` / `경고`로 정규화 |
| hazard_statements | 라벨 요소(유해·위험 문구) 목록 기준. H코드가 없으면 code null, 문구만. 문구 끝 마침표와 줄바꿈 공백은 정리 |
| supplier | 참고 필드. 국내 수입자·공급자가 있으면 그쪽을 우선, 긴급전화가 여러 개면 24시간 번호 |

## 데이터 구성 · 검증

- 재시작 정답 45건(국문): train 35(현행 24 · 수입품 국문판 5 · 구서식 6) · val 10(현행 5 · 수입품 국문판 5)
- `python3 scripts/validate_labels.py data/labels` → 45건 스키마 통과
- 09-23 옛 세트(50건)의 구성 · 검증 기록은 옛 라벨과 함께 보관했습니다(git 이력). 재시작 수치로 쓰지 않습니다.

## 분할 (splits.csv)

재시작 분할입니다(2026-09-28, 경위는 `report/decisions.md`).

| split | 건수 | 위치 | 용도 |
|---|---|---|---|
| train | 35 (국문, 9개 그룹: 현행 24 · 수입품 국문판 5 · 구서식 6) | data/labels/ | QLoRA 학습 · 증강, few-shot 예시 |
| val | 10 (국문, 8개 그룹: 현행 5 · 수입품 국문판 5) | data/labels/ | r1 · r2 비교, 모델 고정 |
| test | 18 (국문) | 저장소 밖(PM 로컬) | 모델 고정 뒤 비교군마다 1회. splits.csv에 넣지 않음 |

`python3 scripts/check_splits.py`로 검사합니다. 분할 확정 직전에는 `--labels data/labels --final`로 정답 누락까지 봅니다.

- **제조사 단위 배정:** 같은 `split_group`과 같은 제조사는 train과 val 중 한쪽에만 둡니다.
- **val 서식:** 수입품 국문판을 섞었습니다. 구서식은 6건 모두 노루 계열이라 val에 넣으면 train에 구서식이 남지 않아 넣지 않았습니다.
- **ITW 2건:** 파일럿에서 조건 선택용 val로 쓴 문서라 test에서 빼고 val로 옮겼습니다. 정답을 새로 만든 뒤 `split-frozen`을 답니다.
- **test:** 새 문서 수집이 불가해 파일럿 노출 문서 18건을 씁니다. 재시작 train · val과 제조사(관계사 포함)가 겹치지 않아야 하며, 결론에 노출 이력을 밝힙니다.

## 채점기 구현 메모

- **content 비교:** 범위 구분자 `~ ∼ ～ - –`, 부등호 `< <= > >= ≥ ≤`, "이상·미만"을 모두 읽어 min/max로 비교해야 합니다.
- **code가 null인 문구:** H코드 F1에서 빼고 문구(공백 제거) 일치로 따로 채점합니다. 6개 문서가 해당됩니다.
- **분류명 비교:** `hazard_class_alias.csv`로 정규 분류명으로 바꾼 뒤 (정규 분류명, category) 쌍으로 비교합니다. 급성 독성 흡입의 물리형태(가스·증기·분진/미스트)는 정규형에서 합쳤습니다.
- **ke_number:** 채점하지 않습니다.
- **함유량 합계 검사:** 모든 문서에서 함유량 **하한** 합계는 100% 이하입니다(같은 물질 중복 없음). **상한** 합계는 범위 표기 특성상 27개 문서에서 100%를 넘으니, Rule Engine은 하한 합계만 검사해야 합니다.

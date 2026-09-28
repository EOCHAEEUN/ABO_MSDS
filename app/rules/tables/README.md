# Rule Engine 대응표  [김건하]

`app/rules/tables/loader.py`가 읽어서 `app/rules/checks/`의 `hcode`·`phrase_to_hcode`·`ghs_signal_hcode_consistency` 검사가 쓴다.

## h_code_phrases.csv

H코드 → 공식 유해·위험 문구. `data/gold_set/`·`data/labels/`·`eval/test/`·`eval/val_en/` 전체(93건, 2026-09-28 기준)에 실제로 등장한 (코드, 문구) 쌍을 모아 만들었다. 즉 고시 별표 2 전체를 옮긴 표가 아니라 **이 프로젝트 문서에 나온 범위**다.

- `phrase_ko`: 가장 흔한 표기(한국어 우선, 동률이면 빈도 최고). `phrase_to_hcode` 검사의 1차 비교 대상.
- `accepted_variants`: 같은 코드에 대해 실제 라벨에 쓰인 나머지 표기(공백·어미·영문 표기 차이, `|`로 구분). `phrase_to_hcode`는 이 중 하나만 맞아도 통과시킨다.
- 새 문서에서 표에 없는 코드나 새 표기가 나오면 이 표에 추가한다. 추가 스크립트: 저장소 루트에서 `data/gold_set`·`data/labels`·`eval/test`·`eval/val_en`의 모든 JSON을 훑어 `hazard_statements[].code`/`text`를 모으면 된다.

## classification_signal_word.csv

(분류명, 구분) → 기대 신호어·기대 H코드. `ghs_signal_hcode_consistency` 검사가 쓴다. `hazard_class_norm`은 `eval/hazard_class_alias.csv`의 "정규 분류명(고시 기준)" 값과 맞춰뒀다 — 검사 코드는 원문 `hazard_class`를 그 표로 먼저 정규화한 뒤 여기서 찾는다.

- `source=standard`: UN GHS·국내 고시가 국제적으로 공통으로 쓰는 값(신뢰도 높음, 문서 오염과 무관)
- `source=observed`: 이 값 하나만 있고 다른 분류가 섞이지 않은 문서에서 그대로 관측한 값(신뢰도 높음)
- 문서 레벨 `signal_word`는 그 문서의 여러 분류 중 가장 강한 것(위험 > 경고 > 해당없음)이라서, "위험"이 섞인 문서만 보고 이 표를 채우면 틀린다(다른 분류 때문일 수 있음). 그래서 여러 분류가 있는 문서의 관측값은 참고만 하고 `standard`로 채웠다. `note` 열에 오염 여부를 적어뒀다.
- **커버리지:** `eval/hazard_class_alias.csv`의 정규 분류명 21종 중 GHS가 아닌 1종(OSHA Simple Asphyxiant)을 뺀 20종을 다뤘다. 새 분류명이 나오면 이 표에 없으므로 `CLASSIFICATION_NOT_IN_TABLE`(info)만 남고 신호어·H코드 대조는 건너뛴다 — 표를 늘려야 한다.
- `expected_h_codes`가 `|`로 여러 개면 "그 중 하나 이상 있으면 통과"라는 뜻이다(예: 특정표적장기 독성(1회 노출) 구분3의 H335/H336).
- `signal_word` 칸이 비어 있으면 그 분류 단독으로는 신호어가 없다는 뜻(예: 만성 수생환경 구분3의 H412 — `EN-SIKA-001`이 실제 사례).

## 검증

`data/gold_set`(43건) + `data/labels`(28건) + `eval/test`(20건) + `eval/val_en`(2건) 전체 93건(중복 포함)을 원문 없이(`source_text=None`) `run_rules()`로 돌려본 결과, `INCONSISTENT`로 잡힌 문서는 전부 `docs/labeling_review_notes.md` B절에 이미 적힌 "원문 자체가 모순인 문서"이거나(KR-HANIL-002·KR-NOROO-001·KR-NOROO-004·KR-CHIPQUIK-001·EN-3M-001) 실제로 신호어가 통째로 빠진 문서였다(KR-DUKSAN-001 — 분류·H코드는 있는데 원문에 신호어가 없음). 오탐(false positive)은 없었다. 표를 더 채우면서 이 스윕을 다시 돌려보는 걸 권장한다.

## 알려진 한계

- 물리적 위험성 전 범주(폭발성·유기과산화물 등)와 건강·환경 유해성 일부(피부 자극 구분3, 눈 자극 구분2B 등 EU 확장 세부구분)는 이 프로젝트 데이터에 없어서 표에 없다.
- 고시 원문 별표를 그대로 스캔·전사한 것이 아니라 국제 표준 GHS 지식 + 프로젝트 관측값으로 구성했다. 결과가 의심스러운 판정이 나오면 이 표부터 의심하고 고시 원문과 대조해야 한다.

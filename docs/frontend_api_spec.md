# Rule Engine 출력 명세 (frontend_api_spec)  [김건하 작성 · 양세윤/어채은 검토]

`app/rules/engine.py`의 `run_rules()`가 반환하는 JSON 모양을 정의한다. `app/api_spec.md`의 `POST /compare`가 이 출력을 그대로(또는 감싸서) 응답 본문에 넣고, `web/`의 검토 화면이 이 모양을 그대로 읽는다고 가정한다.

**v1 (2026-09-28), 라벨 확정 전 임시판.** 아직 `data/gold_set`이 최종 확정되지 않아 `app/rules/tests/`는 fixture(가짜 라벨·가짜 원문)로만 검증했다. `app/rules/tables/`의 대응표도 프로젝트에 실제 등장한 범위로만 채웠으므로, 새 라벨이 들어오면 표 커버리지와 이 문서를 함께 갱신해야 한다.

## 함수 시그니처

```python
def run_rules(
    label: dict,                # 모델 출력 또는 정답 라벨 (src/schema.py MSDSLabel 모양의 dict)
    source_text: str | None,    # data/text/{doc_id}.txt 원문 전체. 없으면 원문 대조 계열 검사는 건너뜀
    doc_id: str | None = None,  # 있으면 결과에 그대로 echo (로그·화면 표시용)
) -> dict:
    ...
```

`label`은 반드시 pydantic으로 미리 파싱될 필요는 없다. 스키마 오류가 있는 원본 dict를 그대로 넣어도 `run_rules`가 죽지 않고 `schema` 검사 결과에 오류로 담는다.

## 최상위 출력 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `doc_id` | `str \| null` | 입력으로 받은 doc_id 그대로 |
| `review_status` | `"OK" \| "NEEDS_REVIEW" \| "INCONSISTENT" \| "SCHEMA_ERROR"` | 아래 "review_status 결정 규칙" 참고 |
| `schema_valid` | `bool` | `schema` 검사 통과 여부 (편의 필드, `findings`에서 다시 계산 가능) |
| `source_text_available` | `bool` | `source_text`가 주어졌는지. `false`면 `not_found`/`evidence` 검사는 실행되지 않고 `findings`에 `EVIDENCE_SKIPPED_NO_SOURCE` 정보성 항목 1건만 남긴다 |
| `checks_run` | `str[]` | 실제로 실행된 검사 이름 9개(또는 원문 없을 때 7개) |
| `findings` | `Finding[]` | 아래 "Finding 객체" 참고. 심각도 순 정렬(error → warning → info) |
| `evidence` | `Evidence[]` | 아래 "Evidence 객체" 참고. `label`의 원문성 값(제품명·CAS·함유량·문구 등) 각각에 대해 1건 |
| `summary` | `object` | `{"n_errors": int, "n_warnings": int, "n_info": int}` |

## Finding 객체

| 필드 | 타입 | 설명 |
|---|---|---|
| `check` | `str` | 9개 검사 이름 중 하나: `schema`\|`empty_value`\|`not_found`\|`evidence`\|`cas`\|`hcode`\|`phrase_to_hcode`\|`ghs_signal_hcode_consistency`\|`content_sum` |
| `severity` | `"error" \| "warning" \| "info"` | error=거의 확실히 잘못됨, warning=사람 확인 필요, info=참고(정오답 아님) |
| `code` | `str` | 사유 코드. 아래 "검사별 사유 코드" 표 참고 |
| `field` | `str \| null` | JSON 경로. `data/gold_set/labels modified.md`와 같은 표기: `$.ingredients[0].content` |
| `message` | `str` | 사람이 읽는 한국어 설명 |
| `detail` | `object \| null` | 검사별 부가 정보(예: 기대값·관측값). 화면에 강제로 보여줄 필요는 없음 |

## Evidence 객체

| 필드 | 타입 | 설명 |
|---|---|---|
| `field` | `str` | JSON 경로 |
| `value` | `str` | 검사 대상 값(예: CAS, 함유량 문자열, 문구) |
| `found` | `bool` | 원문에서 찾았는지 |
| `match_type` | `"exact" \| "normalized" \| "not_found"` | `normalized`는 공백·구분자 정규화 후 일치 |
| `snippet` | `str \| null` | 원문에서 찾은 주변 문맥(최대 80자). 못 찾으면 `null` |

## review_status 결정 규칙

우선순위대로 검사하고 먼저 맞는 것을 채택한다.

1. `schema` 검사에 `error`가 하나라도 있으면 → **`SCHEMA_ERROR`** (구조 자체가 깨져서 나머지 검사 결과를 신뢰할 수 없다는 뜻. 그래도 `checks_run`에 있는 검사는 최대한 실행해서 findings에 남긴다)
2. `ghs_signal_hcode_consistency` 또는 `phrase_to_hcode`에 `error`가 있으면 → **`INCONSISTENT`** (문서 내부 항목끼리 모순 — `docs/labeling_review_notes.md`의 B절 "원문 자체가 모순인 문서"가 이 상태로 잡혀야 함)
3. 그 외 `error` 또는 `warning`이 하나라도 있으면 → **`NEEDS_REVIEW`**
4. 아무 findings도 없으면 → **`OK`**

## 9개 검사와 사유 코드

| 검사(check) | 하는 일 | 사유 코드(code) |
|---|---|---|
| `schema` | `src/schema.py` 규칙(키·자료형·상태값·CAS 형식/체크디지트·목록-상태값 일치)을 필드 단위로 검사. 하나 틀렸다고 전체를 막지 않고 각각 finding으로 쌓는다 | `SCHEMA_FIELD_INVALID` |
| `empty_value` | `source_status`가 `기재`인데 값이 `"자료없음"·"해당없음"·"-"·"없음"·"N/A"·빈 문자열` 같은 사실상 빈 값인 경우를 잡는다(표기 규칙 위반 후보) | `EMPTY_VALUE_SUSPECT` |
| `not_found` | `source_text`가 있을 때, 원문성 값(제품명·공급자·CAS·함유량·H문구 등)이 원문에서 전혀 안 찾아지면 표시(환각 후보) | `VALUE_NOT_FOUND_IN_SOURCE` |
| `evidence` | `not_found`와 짝을 이뤄 찾은 값들의 근거 스니펫을 만들어 최상위 `evidence` 배열을 채운다. 원문이 없으면 정보성 1건만 남김 | `EVIDENCE_SKIPPED_NO_SOURCE` |
| `cas` | CAS 형식(`\d{2,7}-\d{2}-\d`)과 체크디지트 재검증(스키마 검사와 별개로 CAS 전용 배지를 화면에 띄우기 위해 분리) | `CAS_FORMAT_INVALID`, `CAS_CHECKSUM_INVALID` |
| `hcode` | H코드 형식과 `app/rules/tables/h_code_phrases.csv`에 실제 있는 코드인지 검사 | `HCODE_FORMAT_INVALID`, `HCODE_UNKNOWN_CODE` |
| `phrase_to_hcode` | `code`가 있는 유해·위험 문구는 `h_code_phrases.csv`의 해당 코드 문구(들)와 일치하는지 검사(공백·말줄임·문말 어미 차이는 정규화). `code`가 `null`인 문구는 원문 자체에 코드가 없는 정상 케이스이므로 검사하지 않는다 | `HCODE_PHRASE_MISMATCH` |
| `ghs_signal_hcode_consistency` | `app/rules/tables/classification_signal_word.csv`로 (분류명, 구분)마다 기대 신호어·기대 H코드를 찾아 문서의 실제 신호어·H코드 목록과 대조 | `SIGNAL_WORD_MISMATCH`, `HCODE_MISSING_FOR_CLASSIFICATION`, `CLASSIFICATION_NOT_IN_TABLE`(info) |
| `content_sum` | 성분 함유량 **하한** 합계가 100%를 넘는지만 검사(`data/README.md` 채점기 구현 메모: 상한 합계는 27개 문서에서 100% 초과가 정상이라 검사 대상이 아님) | `CONTENT_SUM_EXCEEDS_100`, `CONTENT_SUM_UNPARSEABLE` |

## 예시 1 — 정상 문서 (KR-KUMHO-001, `review_status: "OK"`)

```json
{
  "doc_id": "KR-KUMHO-001",
  "review_status": "OK",
  "schema_valid": true,
  "source_text_available": true,
  "checks_run": ["schema","empty_value","not_found","evidence","cas","hcode","phrase_to_hcode","ghs_signal_hcode_consistency","content_sum"],
  "findings": [],
  "evidence": [
    {"field": "$.product_name.value", "value": "SOL-6220E", "found": true, "match_type": "exact", "snippet": "가. 제품명\n- SOL-6220E"},
    {"field": "$.ingredients[0].cas_number", "value": "9003-55-8", "found": true, "match_type": "exact", "snippet": "9003-55-8 / KE-13258"}
  ],
  "summary": {"n_errors": 0, "n_warnings": 0, "n_info": 0}
}
```

## 예시 2 — 원문 자체가 모순인 문서 (KR-NOROO-001, `review_status: "INCONSISTENT"`)

분류는 인화성액체 구분3 한 줄뿐인데 H문구가 H226·H312·H332·H372·H373 5개다(`docs/labeling_review_notes.md` B절). 라벨은 원문을 그대로 옮겼으므로 라벨 자체가 "틀린" 것은 아니지만, Rule Engine은 검토자가 원본 PDF를 다시 봐야 한다는 신호를 줘야 한다. 아래는 실제 `data/gold_set/KR-NOROO-001.json`과 원문 PDF로 `run_rules()`를 돌린 실제 출력이다(`evidence`는 지면상 일부만 남김).

```json
{
  "doc_id": "KR-NOROO-001",
  "review_status": "INCONSISTENT",
  "schema_valid": true,
  "source_text_available": true,
  "checks_run": ["schema","empty_value","not_found","evidence","cas","hcode","phrase_to_hcode","ghs_signal_hcode_consistency","content_sum"],
  "findings": [
    {
      "check": "ghs_signal_hcode_consistency",
      "severity": "error",
      "code": "SIGNAL_WORD_MISMATCH",
      "field": "$.signal_word.value",
      "message": "분류로 미루어 신호어는 '경고'이어야 하는데 문서는 '위험'입니다.",
      "detail": {"expected": "경고", "actual": "위험"}
    },
    {
      "check": "ghs_signal_hcode_consistency",
      "severity": "error",
      "code": "HCODE_MISSING_FOR_CLASSIFICATION",
      "field": "$.hazard_statements",
      "message": "문구 코드 ['H312', 'H332', 'H372', 'H373']는 목록에 있는 분류로 설명되지 않습니다.",
      "detail": {
        "unexplained_codes": ["H312", "H332", "H372", "H373"],
        "listed_classifications": [{"hazard_class": "인화성액체", "category": "구분 3"}]
      }
    }
  ],
  "evidence": [
    {"field": "$.product_name.value", "value": "뉴-탄성씰(KS) (주제)", "found": true, "match_type": "exact", "snippet": "1. 화학제품과 회사에 관한 정보\n가.제품명 : 뉴-탄성씰(KS) (주제)"}
  ],
  "summary": {"n_errors": 2, "n_warnings": 0, "n_info": 0}
}
```

## 아직 안 된 것 / 알려진 한계

- `classification_signal_word.csv`는 데이터에 실제로 등장한 (분류명, 구분) 조합만 채웠다. 표에 없는 조합은 `CLASSIFICATION_NOT_IN_TABLE`(info)만 남기고 신호어/H코드는 비교하지 않는다.
- `h_code_phrases.csv`의 문구는 `data/gold_set`·`data/labels`·`eval/test`·`eval/val_en` 실제 라벨에서 관측된 표기를 그대로 모아 만들었다(고시 원문 별표 2 전체를 옮긴 것은 아님). 새 문서에서 새 표기가 나오면 표에 추가해야 한다.
- `app/main.py`(POST `/compare`)가 이 dict를 그대로 JSON 응답으로 쓸지, 감싸서 쓸지는 양세윤 확정 필요.

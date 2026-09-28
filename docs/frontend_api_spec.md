# 프런트엔드 API 연동 명세

프런트엔드 구현 기준: `feat/web`의 `web/src/workspace/api.js`, `useWorkspaceController.js`, `model.js` 및 `src/schema.py`. 이 문서는 **프런트가 백엔드에 요청하는 계약**이다. 현재 백엔드 `app/main.py`에는 이 API가 구현되어 있지 않다. 화면의 기본 예시 모드는 API를 호출하지 않으며, `workspace.html?mode=api#documents`에서만 아래 요청을 보낸다.

## 공통 규칙

- 모든 경로는 프런트와 **같은 origin의 루트 경로**다. 예: `http://localhost:8000/documents`. 현재 프런트에는 별도 API base URL과 인증 헤더 설정이 없다. FastAPI에서 정적 파일을 `/`에 mount한다면 API 라우트를 mount보다 먼저 등록한다.
- 성공 응답은 명시한 JSON(`Content-Type: application/json`) 또는 `POST /confirm`의 본문 없는 `204`다. 실패 시 JSON `{"detail":"사용자에게 보여 줄 한국어 오류 설명"}`을 돌려준다. 프런트는 HTTP 오류의 `detail` 문자열을 그대로 표시한다.
- 프런트 요청 제한 시간은 **120초**다. 추출이 이 안에 끝나지 않는다면 비동기 작업 ID/조회 API와 그에 맞는 프런트 변경을 별도로 합의해야 한다.
- 추출 필드의 이름·자료형·상태값은 `src/schema.py`의 `MSDSLabel`을 따른다. `extraction`은 모델 원본이며, 담당자 수정값은 `reviews`에 별도로 저장한다. 프런트의 입력 검사는 사용 편의용이므로 서버에서도 검증한다.
- 문서 목록, PDF, 비교 결과는 **허용된 작업 문서와 고정된 공개 가능 결과만** 제공한다. 봉인된 `test`·`test2` 원문, 정답, 상세 채점은 이 API에서 노출하거나 화면 요청으로 생성하지 않는다. `POST /compare`는 이미 생성된 val 집계의 조회이며 추론·채점을 실행하지 않는다.
- 현재 화면은 한 번에 전체 문서를 받아 브라우저에서 검색·필터·CSV 다운로드를 수행한다. 페이지네이션/서버 검색은 아직 계약에 없다.

## 엔드포인트

| 화면 동작 | 요청 | 성공 응답 | 구현 상태 |
|---|---|---|---|
| 문서 목록 로드·새로고침 | `GET /documents` | `200 {"documents": [Document, ...]}` | 백엔드 구현 필요 |
| PDF 업로드·추출 | `POST /extract` (`multipart/form-data`) | `200` 또는 `201 {"document": Document}` | 백엔드 구현 필요 |
| 5필드 검토 저장 | `POST /confirm` (`application/json`) | `200` JSON 또는 `204` | 백엔드 구현 필요 |
| val 실험 결과 조회 | `POST /compare` (`application/json`) | `200 CompareResult` | 백엔드 구현 필요 |
| 원본 PDF 보기 | `GET {Document.pdf_url}` | 브라우저에서 열 수 있는 `application/pdf` | 백엔드 구현 필요 |

### 1. `GET /documents`

요청 본문과 쿼리 파라미터는 없다. `documents`는 빈 배열일 수 있다. 각 원소는 아래의 **완전한 `Document`**다. 목록에서 선택한 문서를 같은 응답으로 검토·미리보기·다운로드하므로, 현재 프런트는 별도의 문서 상세 조회를 호출하지 않는다. `id`는 고유하고 안정적인 문자열로 내려준다.

```json
{"documents": []}
```

### 2. `POST /extract`

`multipart/form-data` 필드:

| 필드 | 자료형 | 값 |
|---|---|---|
| `file` | PDF 파일 1개 | 최대 30 MiB. 현재 프런트는 `.pdf` 확장자와 `%PDF-` 헤더를 먼저 확인함 |
| `model` | 문자열 | `base` 또는 `qlora` |

응답은 새 문서의 완전한 `Document`를 `document` 키에 담는다. 프런트는 반환된 문서를 목록 맨 앞에 추가하고 검토 화면으로 이동한다. `document.extraction`이 없으면 오류로 처리한다. 파일 크기·형식, PDF 판독 가능 여부, 모델 사용 가능 여부는 서버에서도 검사하고 실패 원인을 `detail`로 반환한다. 현재 화면은 동기 추출만 처리하며, 서버 응답이 오기 전까지 `추출 중`으로 표시한다.

응답 외형은 `{ "document": Document }`다. 이때 `Document`는 아래 예시처럼 `extraction` 전체를 포함한 JSON 객체다.

### 3. `POST /confirm`

담당자가 핵심 5필드(`product_name`, `ingredients`, `ghs_classification`, `signal_word`, `hazard_statements`)를 모두 확정한 후 호출한다. 요청의 `reviews`와 `confirmed_fields`는 해당 문서의 **현재 전체 검토 상태**다. 서버는 문서 ID를 조회하고 검증한 뒤 한 번에 저장한다. 모델 원본 `extraction`은 수정하지 않는다.

```json
{
  "document_id": "upload-001",
  "reviews": {
    "product_name": {
      "confirmed_value": {"value": "예시 제품", "source_status": "기재"},
      "confirmed_at": "2026-09-28T01:00:00.000Z"
    },
    "hazard_statements": {
      "confirmed_value": [{"code": "H226", "text": "인화성 액체 및 증기"}],
      "confirmed_at": "2026-09-28T01:01:00.000Z",
      "list_status": "기재",
      "resolved": true,
      "evidence": {"page": 1, "source_text": "H226 인화성 액체 및 증기"}
    }
  },
  "confirmed_fields": ["product_name", "ingredients", "ghs_classification", "signal_word", "hazard_statements"]
}
```

위 `reviews`는 구조 설명을 위해 일부 필드만 표시했다. 실제 확정 저장에서는 `confirmed_fields`의 **모든 필드에 대한 `reviews` 항목**을 보낸다. 스칼라 필드의 `confirmed_value`는 `{value, source_status}`, 목록 필드의 값은 해당 배열이며 목록 필드는 `list_status`(`기재`·`자료없음`·`해당없음`)도 갖는다. `resolved`와 `evidence`는 원문 확인이 필요한 유해·위험 문구에만 필요할 수 있다. `evidence.page`는 1부터 시작하며 `source_text`는 담당자가 확인한 원문이다. 근거가 없는 `resolved: true`를 서버가 자동으로 신뢰해서는 안 된다.

성공 시 `204 No Content`가 가장 단순하다. `200`을 사용한다면 JSON을 반환한다. 현재 프런트는 성공 응답 본문을 사용하지 않고 화면의 수정 시간을 로컬에서 갱신한다. 새로고침 때 저장된 `reviews`, `confirmed_fields`, `updated_at`이 `GET /documents`에 다시 나타나야 한다. 필드 누락·스키마 오류·근거 부족은 저장하지 않고 `422`와 `detail`을 반환한다.

### 4. `POST /compare`

```json
{"document_id": "upload-001", "split": "val", "subset": "all"}
```

- 현재 화면의 `split`은 **`val`만** 선택한다. `subset` 선택값은 `all`, `current_kr`, `legacy_kr`, `import_kr`다. 집계가 없는 subset은 `experiments: []`로 돌려주거나 명확한 `detail`과 함께 거부한다. 서로 다른 평가셋 결과를 합치지 않는다.
- 프런트는 선택 문서의 ID를 항상 전송하지만 화면에는 **분할·subset 단위 집계**를 표시한다. 서버가 문서별 비교를 제공하지 않는다면 `document_id`는 조회 문맥/권한 검사에만 사용하고 점수 필터로 사용하지 않는다.
- 성공 응답은 다음 구조다. `experiments` 순서는 화면의 비교 기준이므로 첫 항목을 기준 조건(예: `base_zs`)으로 고정한다. `id`는 배열 안에서 고유해야 한다.

```json
{
  "split": "val",
  "subset": "all",
  "executed_at": "2026-09-28 10:24",
  "experiments": [
    {
      "id": "base_zs",
      "name": "Base Zero-shot",
      "short": "Base ZS",
      "condition": "기본 프롬프트",
      "parsing": 75.0,
      "schema": 62.5,
      "cas": 98.0,
      "pair": 98.0,
      "hcode": 100.0,
      "seconds": 16.5,
      "tokens": 490
    }
  ]
}
```

예시 수치는 **형식 설명용**이다. `parsing`, `schema`, `cas`, `pair`, `hcode`는 0~100 단위의 숫자(비율/F1 × 100), `seconds`는 문서당 평균 초, `tokens`는 문서당 평균 **출력** 토큰이다. 이 일곱 값은 누락하거나 문자열/null로 보내지 않는다. 프런트는 카드·표·차트에서 사용한다. 실제 수치는 저장된 val 평가 결과에서 만든다. 선택 화면에서 모델을 클릭해도 서버 모델 설정은 바뀌지 않는다.

## `Document` 응답 객체

아래 JSON은 **화면 데이터 형태를 보여 주는 가상 문서**다. `extraction`의 키와 값 제약은 `src/schema.py`가 기준이며, 필드를 줄인 약식 객체를 반환하지 않는다.

```json
{
  "id": "upload-001",
  "number": 1,
  "file_name": "sample.pdf",
  "language": "한국어",
  "page_count": 1,
  "submission_number": null,
  "revision_date": null,
  "extracted_at": "2026.09.28 10:24",
  "updated_at": "2026.09.28 10:24",
  "owner": "미지정",
  "split": "업로드",
  "model_name": "QLoRA",
  "generation_seconds": 7.2,
  "output_tokens": 412,
  "pdf_url": "/files/upload-001.pdf",
  "source": null,
  "extraction": {
    "product_name": {"value": "예시 제품", "source_status": "기재"},
    "recommended_use": {"value": null, "source_status": "자료없음"},
    "use_restrictions": {"value": null, "source_status": "자료없음"},
    "supplier": {"company_name": "예시 회사", "address": null, "emergency_phone": null},
    "ingredients": [
      {"chemical_name": "예시 성분", "cas_number": "108-65-6", "ke_number": null, "content": "99", "is_substitute_data": false}
    ],
    "ghs_classification": [{"hazard_class": "인화성 액체", "category": "구분 3"}],
    "signal_word": {"value": "경고", "source_status": "기재"},
    "hazard_statements": [{"code": "H226", "text": "인화성 액체 및 증기"}],
    "list_status": {"ingredients": "기재", "ghs_classification": "기재", "hazard_statements": "기재"}
  },
  "reviews": {},
  "confirmed_fields": [],
  "rule_results": {
    "product_name": {"review_status": "OK", "reason_code": null, "page": 1, "section": "1항 가.", "source_text": "예시 제품"},
    "ingredients": {"review_status": "OK", "reason_code": null, "page": 1, "section": "3항", "source_text": "예시 성분 108-65-6 99%"},
    "ghs_classification": {"review_status": "OK", "reason_code": null, "page": 1, "section": "2항 가.", "source_text": "인화성 액체 : 구분 3"},
    "signal_word": {"review_status": "OK", "reason_code": null, "page": 1, "section": "2항 나.", "source_text": "경고"},
    "hazard_statements": {"review_status": "OK", "reason_code": null, "page": 1, "section": "2항 나.", "source_text": "H226 인화성 액체 및 증기"}
  }
}
```

| 필드 | 화면에서의 사용·제약 |
|---|---|
| `id`, `file_name` | 필수. `id`는 문서 선택·검토 저장·비교 요청에 사용 |
| `extraction` | 필수. `MSDSLabel` 전체 객체. JSON 탭의 모델 원본으로 보존 |
| `reviews`, `confirmed_fields` | 목록 로드 때 함께 반환. 없으면 프런트가 `{}`·`[]`로 보정하지만 저장 상태를 유지하려면 서버 값이 필요 |
| `rule_results` | 5개 핵심 필드의 근거·상태. 상태는 `OK`, `REVIEW_REQUIRED`, `SOURCE_CHECK_REQUIRED`. `reason_code`, 1부터 시작하는 `page`, `section`, `source_text` 제공. 근거가 없으면 `null`을 명시하고 서버에서 확정 가능 여부를 검증 |
| `pdf_url` | 실제 원문을 보여 줄 수 있는 같은 origin의 URL. 브라우저 `iframe`에서 접근 가능해야 하며 `application/pdf`로 반환. 서버가 제공하지 않으면 화면은 원문 미리보기를 표시하지 못함 |
| `source` | 가상 문서의 종이 모양 미리보기에만 쓰는 `MSDSLabel` 형태 객체. 실제 문서는 `null`과 `pdf_url`을 사용 |
| `language`, `split`, `owner`, `number` | 목록 필터·헤더·표시용. `language`은 현재 `한국어`/`영어`/`미확인` |
| 나머지 메타데이터 | `page_count`는 양의 정수 또는 `null`, `generation_seconds`·`output_tokens`는 숫자 또는 `null`. 미상인 날짜·제출번호는 `null` 허용 |

`ValueField`의 `source_status`는 `기재`·`자료없음`·`해당없음`이다. `기재`라면 `value`가 비어 있으면 안 되고, 나머지 두 상태라면 `value`는 `null`이다. 세 목록은 `list_status`가 `기재`일 때만 비어 있지 않아야 한다. CAS·KE·H코드·GHS 구분의 형식과 영업비밀 성분 규칙도 서버의 `MSDSLabel`로 확인한다. 프런트에서 편집하는 필드는 핵심 5개지만, `recommended_use`, `use_restrictions`, `supplier`도 원본 JSON에 포함해야 한다.

## 오류 처리와 연동 확인

권장 실패 사례: `400` 잘못된 split/subset/model, `404` 없는 문서/PDF, `413` 30 MiB 초과, `415` PDF가 아닌 파일, `422` 추출·검토값 검증 실패, `503` 추론 서비스 사용 불가. 상태 코드보다 중요한 계약은 **성공/실패를 정확히 구분하고, 실패 시 문자열 `detail`을 돌려주는 것**이다. PDF 추출에 실패했을 때 빈 `MSDSLabel`을 성공 결과로 꾸미지 않는다.

연동 확인 순서:

1. `GET /documents`가 빈 목록 또는 유효한 `Document` 배열을 반환하는지 확인한다.
2. `POST /extract`로 텍스트 PDF 1개를 보내 `document.extraction` 전체와 열리는 `pdf_url`을 확인한다.
3. 다섯 검토 필드를 저장한 뒤 `GET /documents`에서 수정값·확정 목록이 유지되는지 확인한다. 모델 원본 `extraction`은 그대로여야 한다.
4. `POST /compare`가 저장된 val 집계만 반환하는지, 없는 subset과 `test` 요청을 거부하는지 확인한다.

**연동 시 확정할 항목:** UI의 `model=base`가 `base_zs`와 `base_fs` 중 어느 추론 조건인지, 인증/담당자 식별 방식, PDF 접근 권한, 실제 val subset별 집계 제공 범위. 이 항목은 현재 프런트 코드만으로 결정할 수 없다.

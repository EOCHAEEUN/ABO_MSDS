# MSDS 1~3항 구조화 추출 — 작업 기준 요약

> **기준: 기획서 v8 (MSDS-PL-2609-08, 2026-09-23)**. 원본은 팀 드라이브에만 두고 이 저장소(공개)에는 올리지 않는다.
> 작업에 필요한 부분만 옮긴 요약본이다. 기획서가 바뀌면 같은 PR에서 이 파일도 고친다. 괄호 안 장 번호는 기획서 원본 기준.
> 함께 볼 파일: 라벨 표기 세부 `data/README.md` · 판정 기록 `docs/labeling_review_notes.md` · 분할 `data/splits.csv`

## 1. 과업 정의와 범위 (2장)

**한 줄 정의:** 실제 MSDS 1~3항의 핵심 5개 항목을 소형 LLM으로 구조화해 DB에 적재하고, QLoRA로 다양한 문서 표현에 대한 출력 안정성을 높인 뒤, 원문 근거와 함께 사람이 검토하도록 한다.

| 구분 | 내용 |
|---|---|
| 조건 | 본 수행 3일(09:30–17:30, 점심 12:30–13:30, 준비일 없음) · 4명 · RTX 4060 Laptop 8GB · WSL2 Ubuntu 24.04 · Python venv |
| 산출물 | QLoRA 어댑터 · API · SQLite DB · 검토 화면 · Real Test 비교표 |
| 1단계 (핵심) | PDF → 1~3항 5개 항목 고정 JSON → SQLite 적재 |
| 2단계 (입구만) | 스키마·빈 필드·형식·원문 근거 검사 → 검토 상태 표시. 분류 적정성 판단은 하지 않음 |
| 다국어 | 국문으로 학습·평가. 영문 SDS는 전이 성능 확인용으로 따로 평가(보고만) |

| 수행 | 제외 (사유) |
|---|---|
| 1~3항 → 핵심 5필드 + 참고 필드 JSON 추출 | 4~16항 추출 (확장 단계) |
| 추출 결과 SQLite 적재 | 스캔 PDF·OCR (전처리 부담) |
| 텍스트 PDF 처리 (pdfplumber) | rank 탐색·epoch 그리드 (학습 2회 상한) |
| Base · Few-shot · QLoRA 비교 | Ollama·GGUF 변환 (실패 시 복구 시간 없음) |
| FastAPI + transformers + peft 직접 서빙 | 혼합물 GHS 분류 계산·적정성 판정 |
| 검토 화면: 원문 대조·모델 전환·검토 상태 | 다국어 학습 · 15항 규제 정보 생성 (대조만 선택 구현, 10절) |

**설계 원칙**
- 모델은 기재된 값을 읽는다. 문서에 없는 H코드를 지식으로 채우거나 분류를 판단하지 않는다.
- 자동 등록이 아니라 검토 보조다. 모든 결과에 검토 상태와 원문 근거를 붙인다.
- 문서 밖 규칙은 코드가 처리한다. 문구 → H코드 대응, CAS 검증숫자, 물질명 대조, 규제 조회는 규칙·API로 한다.

## 2. 출력 스키마 — 동결 (3장)

착수 회의에서 동결하고 이후 **키 이름을 바꾸지 않는다**(라벨·학습·채점·API·UI·DB가 함께 깨진다). 검사기는 `src/schema.py` 하나를 정답 라벨과 모델 출력에 공통으로 쓴다.

```json
{
  "product_name": {"value": "순&수 베란다용 페인트 (소프트화이트)", "source_status": "기재"},
  "recommended_use": {"value": "콘크리트 내부도장용 상도", "source_status": "기재"},
  "use_restrictions": {"value": "권고 용도외 사용 제한", "source_status": "기재"},
  "supplier": {"company_name": "(주)노루페인트", "address": "경기도 안양시 만안구 박달로 351", "emergency_phone": "031-467-6114"},
  "ingredients": [
    {"chemical_name": "물", "cas_number": "7732-18-5", "ke_number": null, "content": "36∼46", "is_substitute_data": false},
    {"chemical_name": "영업비밀", "cas_number": null, "ke_number": null, "content": "10∼20", "is_substitute_data": true}
  ],
  "ghs_classification": [{"hazard_class": "수생 환경유해성(hazardous to the aquatic environment) 만성", "category": "구분 3"}],
  "signal_word": {"value": "경고", "source_status": "기재"},
  "hazard_statements": [{"code": "H412", "text": "장기적 영향에 의해 수생생물에게 유해함"}],
  "list_status": {"ingredients": "기재", "ghs_classification": "기재", "hazard_statements": "기재"}
}
```
`data/labels/KR-NOROO-004.json` 발췌(성분 7종 중 2종, 분류 2건 중 1건, H문구 3건 중 1건).

| 구분 | 필드 |
|---|---|
| 채점 대상 (핵심 5필드) | `product_name` · `ingredients` · `ghs_classification` · `signal_word` · `hazard_statements` |
| 참고 필드 (추출·DB 적재, 채점 안 함) | `recommended_use` · `use_restrictions` · `supplier` · `ingredients[].ke_number` |
| 모델이 만들지 않는 것 | `evidence`(page·section·source_text) · `review_status` → Rule Engine이 붙인다 |
| 출력·입력에서 모두 제외 | 예방조치문구(P문구). 입력 텍스트에서도 2항 P문구 블록을 잘라낸다(학습·평가·서빙 동일) |

**상태 값 — 원문 상태(모델)와 시스템 판정(Rule Engine)을 섞지 않는다**

| 필드 | 값 | 의미 | 생성 |
|---|---|---|---|
| `source_status` · `list_status` | 기재 | 원문에 값이 적혀 있음 | 모델 |
| 〃 | 자료없음 | 원문에 "자료없음"이라 적혀 있거나, 해당 항목·칸 자체가 없음 (고시 제11조⑦) | 모델 |
| 〃 | 해당없음 | 원문에 "해당없음"이라 적혀 있거나 "분류하지 않음·라벨 부착 규정 없음·None identified" 같은 비해당 서술 | 모델 |
| `review_status` | OK · REVIEW_REQUIRED · SOURCE_CHECK_REQUIRED | 확인 / 검토 필요 / 원문 확인 필요 | Rule Engine |
| 사유 코드 | NOT_FOUND · FORMAT_ERROR · INCONSISTENT | 원문에 있는데 모델이 비움 / 형식 오류 / 명백한 모순 | Rule Engine |

`기재`가 아니면 value는 null, 리스트는 빈 배열이다.

null은 "값 없음"을 나타내는 데이터 표기다. 고시의 자료없음·해당없음은 `source_status`·`list_status`에만 쓰고, `cas_number`·`code`·`ke_number`·`content`·`supplier`에는 상태 글자를 넣지 않는다. 비어 있는 이유는 옆 필드(`is_substitute_data`, `text`)로 알 수 있다.

**출력 규칙 (고용노동부고시 제2026-26호 + 정답 라벨링 결정)**

| 상황 | 출력 규칙 |
|---|---|
| 영업비밀 성분 | `is_substitute_data` true, `cas_number` null, 대체명칭·함유량은 기재된 그대로. "Trade Secret", "소유권(proprietary)"처럼 비공개가 명시된 경우도 같음 |
| CAS 없고 비공개 표시도 없음 | `cas_number` null, `is_substitute_data` false(빈칸·"Mixture"·"혼합물"·"—" 등). Rule Engine이 검토 필요로 표시 |
| CAS와 KE 번호 함께 기재 | `cas_number`에는 CAS만, `ke_number`에 KE. 1~3항의 KE만 담고 15항 법규 정보의 KE는 담지 않음 |
| 한 행에 CAS 여러 개 | 한 행 = 성분 1건. `cas_number`는 칸의 첫 번째 CAS |
| 대표 물질 + "세부조성" 행 | 대표 물질 1건만(세부조성을 넣으면 같은 물질을 두 번 셈) — 잠정 |
| 함유량 범위 | 원문 문자열에서 `%`와 공백만 제거. 구분자(`~ ∼ ～ – -`)·부등호·"이상/미만" 유지(">= 10 - < 15" → `>=10-<15`). 숫자 비교는 채점기·Rule Engine이 min/max로 파싱 |
| 조합 H코드 | `H302+H312`처럼 조합 그대로 코드 1개 |
| H코드 없이 문구만 | `code` null, `text`는 원문 그대로. 코드가 깨져 인쇄된 경우("H317" → "17")도 추정하지 않고 null |
| 신호어 변형 | 위 험, DANGER, 위험!, danger → `위험`. 경고도 같음 |
| 분류 표기 | `hazard_class`는 원문 분류명(영문도 원문 그대로), `category`는 `구분 N`. 확정 세부구분(1A·1B·2A) 유지, 나열형 "구분1(1A/1B/1C)"과 괄호 부기 "구분3(호흡기 자극)" 제거 |
| 고압가스 | `category`에 가스 상태명(압축가스·액화가스·냉동액화가스·용해가스). 영문 "Liquefied gas"도 `액화가스` |
| 한 줄에 분류 두 개 | "급성 독성-경피, 경구 : 구분4" → 경로별 2건으로 펼침 |
| 괄호를 떼면 같은 쌍이 되는 두 줄 | 1건으로 합침(효과 차이는 H335·H336에 남음) |
| 리스트가 빔 | 빈 배열 + `list_status`에 자료없음 / 해당없음 |
| 한계농도 미만이라 원문에 없는 성분 | 정답에 넣지 않음. "CAS 하나 빠짐 = 오류"로 보지 않는다 |

## 3. 데이터와 분할 (4장)

실문서 50건(국문 43 · 영문 7)이 본체이고, 합성은 문서 **표현**에만 적용한다(성분을 섞어 분류를 만들면 화학적으로 틀린 정답이 생긴다). 정답 초안 50건은 착수 전에 작성·검증을 마쳤고, 착수 후에는 검수만 한다.

| split | 건수 | 위치 | 구성 | 용도 |
|---|---|---|---|---|
| train | 24 | `data/labels/` | 국문. 현행 19 · 수입품 국문판 3 · 구서식 2 | 증강 8~10배 → 학습(약 190~240건). few-shot 예시 추출 |
| val | 4 | `data/labels/` | 국문, train과 제조사 겹침 없음 | 변형 5개씩 → 1·2차 비교, 사전 판정, 모델 고정 |
| test (Real Test) | 20 | `eval/test/` | 국문 15(현행 9 · 수입품 국문판 3 · 구서식 3) + 영문 5 | 모델 고정 후 모든 비교군 1회 평가. **봉인** |
| val_en | 2 | `eval/val_en/` | 영문 | 영문 정규화·매핑표 점검. 보고 수치로 쓰지 않음 |

**분할 원칙** (`python3 scripts/check_splits.py`로 검사)
- 분할은 증강 **전에**, 원본 문서 단위로 한다. 같은 제품의 변형이 train과 val에 나뉘면 답을 본 상태가 된다.
- 제조사 단위로 나눈다. 같은 제조사·제품군은 `split_group`으로 묶는다. 예외는 구서식 1건뿐: 구서식 5건이 모두 한 제조사 계열이라 train 2 / test 3으로 나누고, test 3건은 "제조사는 봤지만 제품은 처음"으로 따로 표기한다.
- 사전 검증(9/22)에 쓴 3건(KR-THERMO-001, KR-NOROO-004, KR-NOROO-005)은 이미 Base를 돌렸으므로 모두 train에 둔다.
- 언어가 달라도 같은 물질·같은 회사면 같은 쪽에 둔다. 국문판이 train에 있는 영문 문서는 test에 넣지 않는다(→ val_en).
- few-shot 예시 2개는 train에서만 뽑는다. 후보: KR-NOROO-004(스키마 예시, 영업비밀 포함), KR-KUMHO-002(해당없음 사례, 입력 짧음).

**Real Test 봉인**
- 3일차 09:30 전까지 Base를 포함한 어떤 모델도 test에 돌리지 않는다. 결과를 보고 구성을 바꾸지 않는다.
- test는 학습·few-shot·조건 선택 어디에도 쓰지 않는다. 증강도 적용하지 않는다.
- test 정답 100% 2차 검수는 2차 학습이 끝난 뒤(2일차 15:00)에 한다. 2일차 16:30–17:30 정답 확정 → `eval/seal.py --write` → tag `test-sealed`. 이후 수정 금지.
- 어기면 발표에서 밝힌다.

**표현 증강 — 내용은 그대로, 모양만 바꾼다** (train 8~10배, val 건당 5개, test 적용 안 함)

| 유형 | 예시 |
|---|---|
| 라벨 표기 | CAS No. / CAS 번호 / CAS NO.: / CAS Registry No. |
| 값 공백·구두점 | 67-64-1 / 67 - 64 - 1, 위험 / 위 험 / 위험! |
| 항목 헤더 · 번호 체계 | 2. 유해성·위험성 / 제2항 유해성 및 위험성 · 가. 나. / 1) 2) / ○ / ▷ |
| 레이아웃 | 표 / 서술형 / 키-값 나열 |
| PDF 추출 깨짐 | 표를 열 단위로 쏟음, 라벨과 값 분리, 머리글·바닥글·공급자 주소 끼어듦 |

- **금지:** 성분 추가·삭제, 분류·신호어·H코드 변경, 함유량 수치 변경. `generate_msds.py` 렌더러 5종만 재사용하고 난수 조합·신호어 계산 로직은 버린다.
- **보강 대상:** train의 영업비밀 성분(2건)과 H코드 없는 문서(2건)가 적다(test는 각 9건·4건). 이 두 유형의 표현 변형을 우선 늘린다.

**정답 검수:** train·val은 20%를 다른 사람이 교차검수, test는 100% 2차 검수. 애매한 판정과 원문 모순·PDF 추출 함정은 `docs/labeling_review_notes.md`에 문서별로 남긴다. 원본 PDF는 올리지 않고(`data/raw/`는 gitignore), 출처는 `data/sources.csv`에 기록한다.

## 4. 채점과 비교 (3·7장)

| 항목 | 정답 판정 |
|---|---|
| JSON · 스키마 | JSON 파싱률, 스키마 준수율(키·자료형·상태 값). `src/schema.py`로 검사 |
| product_name | value 공백 정규화 후 완전 일치 |
| signal_word | value·source_status 모두 일치 |
| ingredients | CAS F1 + (CAS, content) pair F1. content는 min/max 숫자로 비교. 영업비밀은 `is_substitute_data`와 content로 판정. `ke_number`는 채점 안 함 |
| ghs_classification | 별칭표 `eval/hazard_class_alias.csv`로 정규 분류명 변환 → 공백 제거 → (hazard_class, category) 쌍 F1. 급성 독성 흡입의 물리형태(가스·증기·분진/미스트)는 정규형에서 합침 |
| hazard_statements | H코드 F1. 코드 없이 문구만 있으면 문구 공백 제거 후 일치(H코드 F1과 따로) |
| 문서 단위 (보조) | 5필드 전부 일치한 문서 비율. 매우 엄격해 보조 지표로만 |

리스트 필드가 비어 있으면 `list_status`가 일치할 때 정답으로 본다.

| 비교군 | 출력 폴더 | 역할 |
|---|---|---|
| Base zero-shot | `outputs/base_zs/` | 출발선 |
| Base few-shot (k=2, train에서 추출) | `outputs/base_fs/` | 프롬프트 엔지니어링 대조군 |
| QLoRA 1차 · 2차 · 최종 | `outputs/qlora_r1/` · `qlora_r2/` · `qlora_final/` | 본 과업 결과물 |
| Rule-based baseline | — | 3일 일정 제외, 확장 단계 |

| 구분 | 지표 | 정의 |
|---|---|---|
| 형식 | JSON 파싱률 · 스키마 준수율 | 구문상 유효한 응답 비율 · 키·자료형·상태 값이 모두 맞는 비율 |
| 정확도 | 필드별 정확도 · 성분 F1 · pair F1 · 문서 단위 완전 일치(보조) | 위 채점 규칙 |
| 안정성 | 무근거 생성률 | 원문에 없는 CAS·H코드를 출력한 비율 |
| 효율 | 생성 시간 · 입력·출력 토큰 | 문서 1건당 평균 |

**분리 보고 — 합산하지 않는다:** Val 4건+변형(조건 선택용, 최종 수치 아님) / Real Test 국문 현행 9 / 구서식 3 / 수입품 국문판 3 / 영문 5 / val_en 2(보고 제외). 추출 실패율(제외 건수 ÷ 전체 투입 건수)도 모델 점수와 따로 보고하며, 실패 건을 분모에서 빼지 않는다.

**사전 판정 기준 (착수 회의 합의)**
- Base few-shot이 Validation 전 항목 90% 이상 → QLoRA의 주 결론을 입력 토큰 절감으로 전환. Real Test는 바꾸지 않는다.
- QLoRA가 정확도에서 Base few-shot과 동률 → 입력 토큰 절감을 주 결론으로. 생성 시간은 주장하지 않는다(사전 측정 7.6초 → 7.5초로 차이 없음).
- 2차 모델은 Validation에서 파싱률·핵심 필드가 모두 1차와 같거나 나을 때만 채택. 3차 학습은 없다.

## 5. 모델·학습·서빙 (5장)

| 구분 | 설정 | 비고 |
|---|---|---|
| 기반 모델 | Qwen/Qwen3-4B, `enable_thinking=False` | 대안 3B급 |
| 양자화 | NF4 4bit, double quantization, compute bf16 | |
| QLoRA | rank 16 / alpha 32 / dropout 0.05, q·k·v·o_proj | `pipeline/configs/r1.yaml` |
| 최대 길이 | 1536 기본, gradient checkpointing | P문구 절단 후 P50/P90/P95/MAX 확인. 초과 샘플은 길이 상향 → 불가 시 목록화(조용히 버리지 않음). 2~3항은 자르지 않음. 입력+정답 출력 길이를 함께 본다 |
| batch / accum / epoch | 1 / 8 / 2 (train 약 240건 → 약 60 step) | effective batch·총 step·학습 시간을 run 설정에 기록 |
| 2차 학습 | r1에서 조건 1개만 변경(epoch / 증강 배수 / 학습률 중 하나) | `pipeline/configs/r2.yaml` |
| 디코딩 | greedy, seed 고정, `max_new_tokens` = 정답 JSON 실측 최장 × 1.3 (초기 768) | 비교군 전부 동일. 정답 최장 3,231자(KR-CKP-001, 성분 13종), 평균 1,327자라 768토큰을 넘을 가능성이 높음 → 1일차 11:00 토크나이저 실측으로 확정 |
| 입력 전처리 | pdfplumber → 4항 제목 이전까지 절단 → 2항 P문구 블록 제거 | 학습·평가·서빙이 `core/`의 같은 추출기를 씀 |
| 서빙 | FastAPI + transformers + peft, 베이스·어댑터 동시 보유 | `/extract` `/compare` `/confirm` `/documents` |
| 기록 | SQLite 적재(필수) + JSONL 실행 로그 | 입력 해시·출력·소요 시간·토큰 수 |

학습 중 전용 GPU 메모리가 8GB에 붙고 공유 메모리 사용이 오르면 속도가 급락하므로, 그 시점에 최대 길이를 내린다.

**PDF 추출 폴백 — 실패를 조용히 넘기지 않는다**

| 상황 | 처리 |
|---|---|
| 4항 제목을 못 찾음 | 문서 전체를 입력으로 쓰고, 길이 초과 시 2·3항 헤더 기준으로 다시 자른다 |
| 항목 제목 형식이 다름 | 실문서에서 "4.", "4:", "4 –", "SECTION 4", "4 First-aid"를 확인. 절단 규칙이 모두 인식해야 함 |
| 추출 텍스트 200자 미만 | 스캔 PDF로 보고 제외 목록에 넣음(OCR은 범위 밖) |
| 표가 열 단위로 쏟아짐 · 굵은 글씨 이중 추출 · 텍스트 없는 이미지 쪽 | 정상 입력. 1~3항 값이 텍스트에 있으면 제외하지 않음 |
| 2항 또는 3항 헤더 자체가 없음 | 제외 목록에 넣고 사유 기록 |

제외·실패 건은 파일명과 사유를 `extract_failures.csv`에 남긴다(기획서 표기).

> **저장소 구현과 다른 점 (v9에서 정리):** 현재 코드(`pipeline/extract_text.py`)는 실패 기록을 `data/text/_cut_log.csv`(status ≠ SUCCESS 행)에 남기고 원문을 `data/text/review_required/`로 뺀다. 별도의 `extract_failures.csv`는 만들지 않는다. 또 4항 제목을 못 찾은 문서는 위 폴백과 달리 자동 투입하지 않는다.

## 6. DB 스키마 — 동결 (6장)

SQLite(온프레미스 전제, 파이썬 내장). 확장 단계에서 PostgreSQL로 옮길 수 있도록 표준 SQL만 쓴다. 1일차 착수 회의에서 출력 스키마와 함께 동결한다.

```sql
CREATE TABLE msds_documents (
  id INTEGER PRIMARY KEY,
  file_name TEXT NOT NULL,
  file_hash TEXT NOT NULL,                        -- 같은 파일 판별
  revision INTEGER NOT NULL DEFAULT 1,            -- 재업로드 시 누적
  product_name TEXT, product_name_status TEXT,    -- 상태: 기재 | 자료없음 | 해당없음
  recommended_use TEXT, use_restrictions TEXT,
  supplier_name TEXT, supplier_address TEXT, supplier_phone TEXT,
  signal_word TEXT, signal_word_status TEXT,      -- 상태: 기재 | 자료없음 | 해당없음
  model_name TEXT NOT NULL,                       -- base | qlora
  raw_json TEXT NOT NULL,                         -- 모델 원본 출력
  rule_json TEXT,                                 -- Rule Engine 판정 결과
  extracted_at TEXT NOT NULL,
  UNIQUE (file_hash, revision, model_name)
);
CREATE TABLE msds_ingredients (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES msds_documents(id),
  seq INTEGER NOT NULL,                           -- 원문 기재 순서
  chemical_name TEXT, cas_number TEXT,
  ke_number TEXT,                                 -- 국내 기존화학물질 번호 (참고)
  content TEXT,
  is_substitute_data INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE msds_classifications (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES msds_documents(id),
  hazard_class TEXT, category TEXT
);
CREATE TABLE msds_hazard_statements (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES msds_documents(id),
  code TEXT, text TEXT
);
CREATE TABLE msds_reviews (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES msds_documents(id),
  field_path TEXT NOT NULL,                       -- 예: ingredients[1].cas_number
  extracted_value TEXT,                           -- 모델이 낸 값
  confirmed_value TEXT,                           -- 사람이 확정한 값
  review_status TEXT, reason_code TEXT,
  confirmed_at TEXT
);
```

**설계 결정:** ① 개정은 덮어쓰지 않고 `revision`을 올려 쌓는다. ② 모델 출력과 사람 확정값을 `msds_reviews`에 분리 저장한다(사람이 몇 건 고쳤는지가 효과 지표). ③ `model_name`이 키에 들어가 같은 문서의 Base·QLoRA 결과를 나란히 저장한다.

| 엔드포인트 | 동작 |
|---|---|
| `POST /extract` | 추출 후 `msds_documents` + 하위 3개 테이블 적재, `document_id` 반환 |
| `POST /compare` | 같은 문서를 Base·QLoRA로 각각 추출해 비교 반환 |
| `POST /confirm` | 담당자 확정·수정값을 `msds_reviews`에 저장 |
| `GET /documents` | 적재 이력 목록(파일명·제품명·모델·검토 상태) |

## 7. Rule Engine과 검토 화면 (9장)

흐름: PDF 업로드 → 텍스트 추출(1~3항 절단) → LLM 추출(Base/QLoRA) → Rule Engine 검증 → 검토 화면(원문 대조) → 확정·수정 → DB 적재·JSON 다운로드

| 검사 | 규칙 | 실패 시 | 사유 |
|---|---|---|---|
| 스키마 | 키·자료형·source_status·list_status 값 | 검토 필요 | FORMAT_ERROR |
| 원문 근거 | 추출값이 원문에 존재하는가. 공백·하이픈 정규화 + 별칭(구분 2 ↔ Category 2, 위험 ↔ DANGER) | 원문 확인 필요 | — |
| CAS 형식 | 패턴 + 검증숫자 계산 | 검토 필요 | FORMAT_ERROR |
| CAS 없는 성분 | `cas_number` null이고 `is_substitute_data` false | 검토 필요 | — |
| H코드 형식 | H + 3자리, 조합은 + 연결 | 검토 필요 | FORMAT_ERROR |
| 문구 → H코드 대응 | code null인 문구를 고시 대응표와 대조 | 대응 실패 시 검토 필요 | — |
| GHS ↔ 신호어·H코드 일관성 | 공식 대응표 기준 명백한 위배만 | 검토 필요 | INCONSISTENT |
| 함유량 합계 | content를 min/max로 파싱해 **하한** 합 ≤ 100. 상한 합은 100을 넘는 것이 정상(정답 50건 중 27건) | 원문 확인 필요 | — |
| 누락 재판정 | 모델이 비웠는데 원문에 값이 있음 | 검토 필요 | NOT_FOUND |
| 빈값 | source_status·list_status가 자료없음 / 해당없음 | 확인(표시만) | — |

모든 검사를 통과한 항목은 OK. 분류가 맞는지는 판단하지 않는다. 정답에 원문 자체의 모순 7건이 원문대로 들어 있어 INCONSISTENT 시험용으로 쓸 수 있다(`docs/labeling_review_notes.md` B절).

| 화면 영역 | 필수 기능 | 완성 판정 | 하지 않는 것 |
|---|---|---|---|
| 업로드 | PDF 선택 + 샘플 문서 버튼 3개(현행·구서식·수입품) | 클릭 즉시 추출 시작, 진행 표시 | 드래그앤드롭, 다중 업로드 |
| 원문 패널 | 추출 텍스트 + 근거 하이라이트 | 결과 항목 클릭 시 원문 위치로 스크롤·강조 | PDF 원본 렌더링 |
| 결과 패널 | 5개 핵심 항목 + 참고 필드, 항목별 검토 상태 | 상태 3종 색 구분 + 사유 코드 표시 | 신뢰도 점수 |
| 모델 전환 | Base ↔ QLoRA 토글 | 같은 문서를 다시 추출해 차이 표시 | 3개 이상 동시 비교 |
| 확정 | 인라인 수정 + 확정 → `POST /confirm` | `msds_reviews`에 저장 | 코멘트, 승인 워크플로 |
| 이력 | `GET /documents` 목록 | 파일명·제품명·모델·검토 상태 표시 | 통계 대시보드, 검색·필터 |

화면 판정: 시연 시나리오 1회(업로드 → 결과 → 모델 전환 → 상태 확인 → 확정 → JSON 다운로드)가 끊김 없이 돌면 통과. 미적 완성도는 판정에 넣지 않는다. 샘플 문서는 test가 아닌 문서에서 고른다.

## 8. 3일 일정 (10장)

역할 — **데** 데이터·학습 실행(강덕우) / **규** 라벨링·Rule Engine(김건하) / **평** 환경·평가·서빙(양세윤) / **프** PM·Test 라벨·화면(어채은)

| 일차 | 시간 | 작업 |
|---|---|---|
| 1일차<br>검수·1차 학습 | 09:30–10:00 | 전원 착수 회의: 분할표·출력 스키마(ke_number 포함)·DB 스키마 동결, 잠정 판정 확정, 생성 길이 확정 방식, Real Test 봉인 공지 |
| | 10:00–14:30 | 데·규: Val 4건 검수 먼저(11:00) → Train 검수 · 평: 환경 점검·토큰 측정(max_new_tokens 확정) → Test 영문 5건 초안 확인 → 13:30 Base Val 추론 · 프: Test 국문 15건 초안 확인 |
| | 14:30–15:00 | 데·규: Train·Val 20% 교차검수 · 프: 불일치 판정 |
| | 15:00–16:30 | 데: `check_splits.py` → 증강 → 길이 분포 → JSONL · 규: CAS·H코드 형식 검사 · 평: Base Val 채점·사전 판정 · 프: 화면 골격 |
| | 16:30–17:30 | 데: 1차 학습(2 epoch, 약 60 step) · 규: 원문 근거 매칭(별칭표) · 프: 원문 패널 |
| 2일차<br>비교·2차 학습·연결 | 09:30–11:00 | 평: 1차 QLoRA Val 채점 · 데·규: Val 실패 유형 분석 · 프: 하이라이트 |
| | 11:00–11:30 | 전원: 2차 조건 결정(epoch / 증강 배수 / 학습률 중 하나만) |
| | 11:30–13:30 | 데: 2차 학습 · 규: GHS 일관성·NOT_FOUND 재판정 · 평: FastAPI + DB 적재 · 프: 실 API 연결 |
| | 13:30–15:00 | 평: 2차 Val 채점, 1차와 비교 · 규: Rule Engine → API 통합 · 프: 검토 상태 표시 |
| | 15:00–16:30 | 데·규: Real Test 정답 100% 2차 검수 · 평: 시간·토큰 측정, `POST /confirm` · 프: 모델 전환 UI |
| | 16:30–17:30 | 전원: 모델 고정 + Real Test 정답 확정·봉인 · 평: 실 모델 서빙 |
| 3일차<br>Real Test·발표 | 09:30–11:00 | 평: Real Test 20건 최초 평가(Base zero-shot / few-shot / QLoRA 각 1회) · 프: 샘플 버튼, 발표 목차 |
| | 11:00–12:30 | 평: 최종 비교표 · 데·규: 실패 사례 3~5건 선별 · 12:00 전원 시연 리허설 1차 |
| | 13:30–16:00 | 전원: 발표 자료 · 평·프: 안정화, **신규 기능 금지**(여유 시 `GET /documents` 이력 화면) |
| | 16:00–17:30 | 전원: 최종 리허설, 예상 질문 정리 |

## 9. 성과 판정과 위험 대응 (11장)

| 판정 항목 | 성공 | 실패 | 측정 |
|---|---|---|---|
| JSON 파싱률 | Real Test 95% 이상 | 90% 미만 | 3일차 Real Test 1회 |
| 스키마 준수율 | 95% 이상 | 90% 미만 | 3일차 Real Test 1회 |
| 핵심 5필드 | 모든 항목이 Base zero-shot 이상 + 1개 이상 개선 | 어느 한 항목이라도 Base보다 하락 | 4절 채점 규칙 |
| 입력 토큰 | Few-shot 대비 60% 이하 | 절감 없음 | 문서 1건당 평균 |
| 추출 실패율 | 10% 이하 + 사유 기록 | 기록 없이 누락 | `data/text/_cut_log.csv` |
| DB 적재 | 1건 업로드 시 4개 테이블 행 생성 + `POST /confirm` 저장 | 하나라도 미동작 | 2일차 이후 상시 |
| 검토 화면 | 시연 시나리오 1회 무중단 | 중단·수동 개입 필요 | 3일차 리허설 |

수치는 목표치이며 착수 회의에서 확정한다. Validation 90% 기준(4절)은 조건 선택용이지 성패 기준이 아니다.

- **필수:** ① QLoRA 어댑터 1개(손실 수렴, 파일 존재) ② Base·Few-shot 대비 개선 수치(Real Test 1회, 평가셋별 분리 비교표) ③ 동작하는 검토 화면 ④ DB 적재(4개 테이블 + `/confirm`)
- **선택:** ① Rule-based baseline(3일 제외) ② 실패 사례 3~5건 분석 ③ 영문 SDS 전이 결과 ④ 15항 규제 대조 시연(10절)

| 위험 | 판단 시점 | 대응 |
|---|---|---|
| 정답 검수 지연 | 1일차 12:30 | Val·Train 검수 60% 미만이면 Train은 20% 교차검수만. Real Test 100% 2차 검수는 줄이지 않음 |
| 정답 라벨 오류 | 1일차 15:00, 2일차 16:30 | 교차검수 불일치율 20% 초과 시 규칙 수정 후 해당 필드 전수 재확인 |
| 생성 길이 부족 | 1일차 11:00 | 정답 최장 문서 토큰 실측. 768로 잘리면 실측 최장 × 1.3으로 올리고 학습 최대 길이도 재검토 |
| Base 성능이 이미 높음 | 1일차 16:30 | 사전 판정 기준 적용 → 주 결론을 입력 토큰 절감으로 |
| VRAM 부족 | 1일차 11:30 | max length 1024로 내리고 초과 샘플 목록화. 미해결 시 3B급 교체 |
| 학습 손실 미수렴 | 1일차 17:30 | 학습률 1e-4로 내리고 야간 재실행 |
| 증강 과적합 | 2일차 오전 | 문서 단위 split 재확인. 원본과 변형 점수 격차로 판단 |
| PDF 추출 실패 다발 | 1일차 15:00 | 5절 폴백, 제외 건 기록. 실패율 10% 초과 시 발표에서 한계로 명시 |
| API·화면 연결 지연 | 2일차 14:00 | 노트북 시연으로 대체. 지표가 화면보다 우선 |
| DB 적재 지연 | 2일차 16:00 | 하위 테이블을 미루고 `msds_documents` + `raw_json` 적재부터 |
| 2차 학습 결과 악화 | 2일차 16:30 | Val에서 1차보다 못하면 1차로 확정. 3차 학습 없음 |
| Real Test 오염 | 상시 | 3일차 09:30 전 Test 추론·결과 열람 금지. 어기면 발표에서 밝힘 |

운영 원칙: 기능을 늘리는 결정은 하지 않는다. 여유 시간은 실패 사례 분석과 발표 준비에 쓴다.

## 10. 선택 과업·한계 (12·13장)

- **15항 국내 규제 대조(선택 4):** 모델이 생성하지 않는다. QLoRA가 뽑은 CAS로 KOSHA API 조회 → Rule Engine이 15항 기재값과 대조 → 불일치 시 REVIEW_REQUIRED + INCONSISTENT. 위험물안전관리법 지정수량 1종만. **착수 게이트:** 필수 1~4 충족, Real Test 비교표 완성, 리허설 1차 완료, 3일차 16:00 이전 — 하나라도 미충족이면 하지 않는다. 발표 비중 1분.
- **하지 않는 것:** 분류 적정성 판단, 무인 자동 등록, 서식이 일정한 문서에서 규칙 기반 대체 주장, 규제 대응 수준 정확도(Real Test 20건은 방향 확인 규모), 구서식 일반화 주장(구서식 5건이 한 제조사 계열).

## 11. 착수 회의 확정 사항 (1일차 09:30)

- [ ] 출력 스키마 동결 (cas_number, ke_number, is_substitute_data, source_status, list_status, 참고 필드, 상태값 기재·자료없음·해당없음)
- [ ] DB 스키마 동결 (테이블 5종, revision·model_name 키 규칙, msds_ingredients.ke_number)
- [ ] 분할표 확정: `data/splits.csv`(Train 24 / Val 4 / Real Test 20 / val_en 2)와 구서식 예외
- [ ] 잠정 라벨 판정 확정: `docs/labeling_review_notes.md` A절 잠정 표(A9~A17)
- [ ] Real Test 봉인 원칙과 사전 판정 기준(Validation 90%) 합의
- [ ] 9절 통합 판정표 목표 수치 확정
- [ ] `max_new_tokens` 초기값(768)과 11:00 실측 확정 방식 — 정답 최장 문서 KR-CKP-001 기준
- [x] real-03 정답 수정(H코드 추정값 제거) — KR-NOROO-005
- [ ] 출처 URL 31건 보완 (`data/sources.csv`)
- [ ] KOSHA Open API 인증키 발급 여부, 응답에 규제 항목 포함 여부
- [ ] 발표 자료의 기업명·제조사명 익명 처리 방식

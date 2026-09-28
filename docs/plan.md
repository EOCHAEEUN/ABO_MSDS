# MSDS 1~3항 구조화 추출 — 팀 작업 기준 (재시작판)

> **기준:** 과업 정의는 기획서 v8(MSDS-PL-2609-08, 2026-09-23)을 따릅니다. 기획서 원본은 팀 드라이브에만 두고 이 저장소(공개)에는 올리지 않습니다.
> **재시작 (2026-09-28):** 데이터 · 정답 · 평가 절차를 처음부터 다시 합니다(0절). 기획서의 3일 일정 대신 단계와 통과 조건(9절)으로 진행합니다.
> 이 문서를 고칠 때는 같은 PR에서 CLAUDE.md도 맞춥니다. 함께 볼 파일: 라벨 표기 세부 `data/README.md` · 결정 기록 `report/decisions.md`

## 0. 왜 다시 시작하나

- **파일럿:** PM이 혼자 파일럿을 먼저 진행했습니다(`feat/web` 브랜치, 09-23~28). 전 과정을 한 번 돌렸습니다. 학습(r1 · r2 · 재학습 C1 · 제조사 교차검증), 평가 도구, 검토 화면이 있습니다.
- **파일럿의 test는 독립 평가로 쓸 수 없게 됐습니다.**
  - 개발 판단(증강 설계)에 test 텍스트를 참고했습니다.
  - 추출 검증 중에 test 정답을 열었습니다.
  - 추가 test(test2)의 정답이 개발 AI 세션에 첨부됐습니다.
  - 정답에서 나온 집계값이 공개 저장소에 push됐습니다.
- **재시작에서 바꾸는 것:**
  1. **test는 저장소 밖에 두고 개발에 쓰지 않습니다.** 원래는 새 문서로 만들 계획이었으나, 수집이 불가해 파일럿 노출 문서 18건을 씁니다(3.1 · 3.3절, 2026-09-28 결정).
  2. **정답은 처음부터 다시 만듭니다.** main의 기존 라벨(09-23)은 초안이나 참고로 쓰지 않습니다.
  3. **파일럿 결과는 근거로 쓰지 않습니다.** 파일럿에서 얻은 과정상의 교훈만 가져옵니다(12절).
- **파일럿 코드(`feat/web`):** main에 병합하지 않습니다. 필요한 파일은 PR로 하나씩 가져오고 리뷰를 받습니다. 코드를 다시 쓰는 것은 test 유출이 아닙니다. test가 새 문서이기 때문입니다.

## 1. 과업 정의와 범위

**한 줄 정의:** 실제 MSDS 1~3항의 핵심 5개 항목을 소형 LLM으로 구조화해 DB에 적재합니다. QLoRA로 다양한 문서 표현에 대한 출력 안정성을 높이고, 원문 근거와 함께 사람이 검토하도록 합니다.

| 구분 | 내용 |
|---|---|
| 조건 | 개발 4명 + test 담당(개발 비참여), 노트북 GPU 8GB, WSL2 Ubuntu 24.04, Python venv. 기간은 PM이 확정 |
| 산출물 | QLoRA 어댑터 · API · SQLite DB · 검토 화면 · test 비교표 |
| 1단계 (핵심) | PDF → 1~3항 5개 항목 고정 JSON → SQLite 적재 |
| 2단계 (입구만) | 스키마 · 빈 필드 · 형식 · 원문 근거 검사 → 검토 상태 표시. 분류 적정성은 판단하지 않음 |
| 다국어 | 국문으로 학습 · 평가. 영문 SDS는 선택 과제(보고만) |

| 수행 | 제외 (사유) |
|---|---|
| 1~3항 → 핵심 5필드 + 참고 필드 JSON 추출 | 4~16항 추출 (확장 단계) |
| 추출 결과 SQLite 적재 | 스캔 PDF · OCR (전처리 부담) |
| 텍스트 PDF 처리 (pdfplumber) | rank 탐색 · epoch 그리드 (학습 2회 상한) |
| Base · Few-shot · QLoRA 비교 | Ollama · GGUF 변환 |
| FastAPI + transformers + peft 직접 서빙 | 혼합물 GHS 분류 계산 · 적정성 판정 |
| 검토 화면: 원문 대조 · 모델 전환 · 검토 상태 | 다국어 학습 · 15항 규제 정보 생성 |

**설계 원칙**
- 모델은 기재된 값을 읽습니다. 문서에 없는 H코드를 지식으로 채우거나 분류를 판단하지 않습니다.
- 자동 등록이 아니라 검토 보조입니다. 모든 결과에 검토 상태와 원문 근거를 붙입니다.
- 문서 밖 규칙은 코드가 처리합니다. 문구 → H코드 대응, CAS 검증숫자, 물질명 대조는 규칙으로 합니다.

## 2. 출력 스키마 — 동결

**키 이름을 바꾸지 않습니다.** 바꾸면 라벨 · 학습 · 채점 · API · UI · DB가 함께 깨집니다. 검사기는 `src/schema.py` 하나를 정답 라벨과 모델 출력에 공통으로 씁니다.

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
형식 예시입니다(일부 항목만).

| 구분 | 필드 |
|---|---|
| 채점 대상 (핵심 5필드) | `product_name` · `ingredients` · `ghs_classification` · `signal_word` · `hazard_statements` |
| 참고 필드 (추출 · DB 적재, 채점 안 함) | `recommended_use` · `use_restrictions` · `supplier` · `ingredients[].ke_number` |
| 모델이 만들지 않는 것 | `evidence`(page · section · source_text) · `review_status` → Rule Engine이 붙임 |
| 출력 · 입력에서 모두 제외 | 예방조치문구(P문구). 입력 텍스트에서도 2항 P문구 블록을 잘라냄(학습 · 평가 · 서빙 동일) |

**상태 값 — 원문 상태(모델)와 시스템 판정(Rule Engine)을 섞지 않습니다**

| 필드 | 값 | 의미 | 생성 |
|---|---|---|---|
| `source_status` · `list_status` | 기재 | 원문에 값이 적혀 있음 | 모델 |
| 〃 | 자료없음 | 원문에 "자료없음"이라 적혀 있거나, 해당 항목 · 칸 자체가 없음 (고시 제11조⑦) | 모델 |
| 〃 | 해당없음 | 원문에 "해당없음"이라 적혀 있거나 "분류하지 않음 · 라벨 부착 규정 없음 · None identified" 같은 비해당 서술 | 모델 |
| `review_status` | OK · REVIEW_REQUIRED · SOURCE_CHECK_REQUIRED | 확인 / 검토 필요 / 원문 확인 필요 | Rule Engine |
| 사유 코드 | NOT_FOUND · FORMAT_ERROR · INCONSISTENT | 원문에 있는데 모델이 비움 / 형식 오류 / 명백한 모순 | Rule Engine |

- `기재`가 아니면 value는 null, 리스트는 빈 배열입니다.
- null은 "값 없음"을 나타내는 데이터 표기입니다. 자료없음 · 해당없음은 `source_status` · `list_status`에만 씁니다. `cas_number` · `code` · `ke_number` · `content` · `supplier`에는 상태 글자를 넣지 않습니다.

**출력 규칙 (고용노동부고시 제2026-26호 + 라벨링 결정)**

라벨 규칙 동결(4절) 전에 파일럿 라벨링 결과로 보완할 수 있습니다. 동결 뒤에 바꾸면 이미 만든 모든 정답(test 포함)에 다시 적용합니다.

| 상황 | 출력 규칙 |
|---|---|
| 영업비밀 성분 | `is_substitute_data` true, `cas_number` null, 대체명칭 · 함유량은 기재된 그대로. "Trade Secret", "소유권(proprietary)"처럼 비공개가 명시된 경우도 같음 |
| CAS 없고 비공개 표시도 없음 | `cas_number` null, `is_substitute_data` false(빈칸 · "Mixture" · "혼합물" · "—" 등). Rule Engine이 검토 필요로 표시 |
| CAS와 KE 번호 함께 기재 | `cas_number`에는 CAS만, `ke_number`에 KE. 1~3항의 KE만 담고 15항 법규 정보의 KE는 담지 않음. EC · REACH 번호는 담지 않음 |
| 한 행에 CAS 여러 개 | 한 행 = 성분 1건. `cas_number`는 칸의 첫 번째 CAS |
| 대표 물질 + "세부조성" 행 | 대표 물질 1건만(세부조성을 넣으면 같은 물질을 두 번 셈) — 잠정 |
| 함유량 범위 | 원문 문자열에서 `%`와 공백만 제거. 구분자(`~ ∼ ～ – -`) · 부등호 · "이상/미만" 유지(">= 10 - < 15" → `>=10-<15`). 숫자 비교는 채점기 · Rule Engine이 min/max로 파싱 |
| 조합 H코드 | `H302+H312`처럼 조합 그대로 코드 1개 |
| H코드 없이 문구만 | `code` null, `text`는 원문 그대로. 코드가 깨져 인쇄된 경우("H317" → "17")도 추정하지 않고 null |
| 신호어 변형 | 위 험, DANGER, 위험!, danger → `위험`. 경고도 같음 |
| 분류 표기 | `hazard_class`는 원문 분류명(영문도 원문 그대로), `category`는 `구분 N`. 확정 세부구분(1A · 1B · 2A) 유지, 나열형 "구분1(1A/1B/1C)"과 괄호 부기 "구분3(호흡기 자극)" 제거 |
| 고압가스 | `category`에 가스 상태명(압축가스 · 액화가스 · 냉동액화가스 · 용해가스). 영문 "Liquefied gas"도 `액화가스` |
| 한 줄에 분류 두 개 | "급성 독성-경피, 경구 : 구분4" → 경로별 2건으로 펼침 |
| 괄호를 떼면 같은 쌍이 되는 두 줄 | 1건으로 합침 |
| 리스트가 빔 | 빈 배열 + `list_status`에 자료없음 / 해당없음 |
| 한계농도 미만이라 원문에 없는 성분 | 정답에 넣지 않음 |

## 3. 데이터

### 3.1 문서의 두 종류

| 종류 | 무엇 | 쓸 수 있는 곳 |
|---|---|---|
| **노출 문서** | 파일럿에서 본 87건(제조사 44곳, 국문 64 · 영문 22 · 기타 1). 목록은 파일럿 `data/sources.csv` | train · val · 영문 점검용 |
| **test (예외)** | 노출 문서 중 18건. 재시작 train · val과 제조사가 겹치지 않아야 함. 파일럿에서 test · test2 등으로 쓰였음 | test만. 결론에 노출 이력을 밝힘 |

- 노출 문서의 원본 PDF는 이미 있습니다(`data/raw/`, git 제외, 팀 드라이브로 공유).
- 파일럿의 test · test2 문서도 재시작에서는 노출 문서입니다. 정답을 새로 만들어 train · val에 쓸 수 있습니다.
- **test 예외 (2026-09-28):** 새 문서 수집이 불가해 노출 문서 18건을 test로 씁니다. 파일럿에서 조건 선택용 val로 쓴 ITW 2건은 test에서 빼고 재시작 val로 옮겼습니다. 경위는 `report/decisions.md`.

### 3.2 분할

| split | 위치 | 구성 | 용도 |
|---|---|---|---|
| train | `data/labels/` | 노출 문서 중 국문 35건(9개 그룹) | 증강 → 학습. few-shot 예시 |
| val | `data/labels/` | 노출 문서 중 국문 10건(8개 그룹, 현행 5 · 수입품 국문판 5). train과 제조사 불겹침. 구서식은 전부 노루 계열이라 val에 넣지 않음 | 조건 선택(r1 · r2 비교, 모델 고정) |
| test | 저장소 밖(PM 로컬) | 노출 문서 중 국문 18건. train · val과 제조사(관계사 포함)가 겹치지 않아야 함. splits.csv에 넣지 않음 | 모델 고정 뒤 비교군마다 1회. **봉인** |
| val_en | `eval/val_en/` | 노출 문서 중 영문 (선택) | 영문 정규화 점검. 보고 수치로 쓰지 않음 |

**분할 원칙** (`python3 scripts/check_splits.py`로 검사)
- 분할은 증강 **전에**, 원본 문서 단위로 합니다.
- 같은 제조사 · 제품군은 `split_group`으로 묶어 한쪽에만 둡니다. 언어가 달라도 같은 물질 · 같은 회사면 같은 쪽에 둡니다.
- few-shot 예시 2개는 train에서만 고르고, 고른 뒤에는 바꾸지 않습니다.
- 분할을 확정하면 tag `split-frozen`을 답니다. 결과를 보고 바꾸지 않습니다.

### 3.3 test 구성 · 보관

- **구성 (2026-09-28 결정):**
  - 새 문서 수집이 불가해 노출 문서 18건을 씁니다. 재시작 train · val 제조사와 겹치지 않고, 텍스트 PDF이며 1~3항이 있어야 합니다.
  - 파일럿에서 조건 선택에 쓴 문서(ITW)는 뺐습니다.
  - 정답은 파일럿 정답을 열지 않고 원문에서 새로 만듭니다.
  - 보고할 때 파일럿 노출 정도(파일럿 test / test2 / 그 밖)로 나눠 적을 수 있도록, 문서별 구분을 저장소 밖 목록에 둡니다.
- **보관:**
  - test 문서 · 텍스트 · 정답은 저장소 밖(현재 PM 로컬)에 둡니다. 개발 세션(사람 · AI)에 파일 · 목록을 넣지 않습니다.
  - 공개 저장소에는 봉인 해시 목록(`report/test_manifest.csv`)만 커밋합니다.
- **개발 쪽에 알려 주는 것:** 건수, 서식별 건수, 봉인 해시만 알려 줍니다. 파일명 · 제조사 · 값은 평가가 끝날 때까지 알려 주지 않습니다.
- **평가 실행:**
  - 모델 고정(9절 단계 7) 뒤에 test 담당이 텍스트를 넘기고, 평가 담당이 비교군마다 1회 생성 · 채점합니다.
  - 평가가 끝나기 전에는 개발 쪽이 문서별 출력 · 채점 상세를 보지 않습니다. 평가가 끝난 뒤에는 실패 분석에 씁니다.
  - test 출력 · 채점 상세 · 별칭표 밖 분류명 목록은 저장소 밖(`--out-root`)에만 생깁니다. 비교군마다 최초 채점 결과는 따로 보존하고 덮어쓰지 않습니다.

### 3.4 표현 증강 — 내용은 그대로, 모양만 바꾼다 (train만, val은 변형 점검용, test 적용 안 함)

| 유형 | 예시 |
|---|---|
| 라벨 표기 | CAS No. / CAS 번호 / CAS NO.: / CAS Registry No. |
| 값 공백 · 구두점 | 67-64-1 / 67 - 64 - 1, 위험 / 위 험 / 위험! |
| 항목 헤더 · 번호 체계 | 2. 유해성·위험성 / 제2항 유해성 및 위험성 · 가. 나. / 1) 2) / ○ / ▷ |
| 레이아웃 | 표 / 서술형 / 키-값 나열 |
| PDF 추출 깨짐 | 표를 열 단위로 쏟음, 라벨과 값 분리, 머리글 · 바닥글 · 공급자 주소 끼어듦 |

- **금지:** 성분 추가 · 삭제, 분류 · 신호어 · H코드 변경, 함유량 수치 변경. 증강 뒤에는 `pipeline/augment/check_forbidden.py`로 검사합니다.
- **보강 대상:** train에 적은 유형(영업비밀 성분, H코드 없는 문서, 수입품 서식)의 표현 변형을 우선 늘립니다. 어떤 유형이 적은지는 train · val로만 판단합니다.

## 4. 라벨링

| 단계 | 할 일 | 담당 | 통과 조건 |
|---|---|---|---|
| 1. 규칙 파일럿 | train 문서 5건을 두 사람이 따로 라벨링 → 불일치를 보고 2절 규칙 · `data/README.md` 보완 | 데 · 규 | 불일치 판정을 `docs/labeling_review_notes.md`에 기록 |
| 2. 규칙 동결 | 2절 출력 규칙과 `data/README.md` 표기 규칙 확정 | PM | tag `label-rules-frozen` |
| 3. train · val | 라벨링 + 20% 교차검수 | 데 · 규 (+ 여유 인원) | `validate_labels.py` 통과, 교차검수 불일치율 20% 이하(넘으면 규칙 수정 후 그 필드 전수 재확인) |
| 4. test | 라벨링 + 100% 2차 검수, 저장소 밖 | test 담당 + 2차 검수자(둘 다 개발 비참여) | 스키마 검사 통과 → 봉인(해시 커밋) → tag `test-sealed` |

- **정답은 사람이 확정합니다.** LLM 초안을 쓰면 원문과 모두 대조한 뒤 확정합니다. test 초안은 test 담당의 세션에서만 만듭니다.
- 판정이 애매한 경우, 원문 모순, PDF 추출 함정은 `docs/labeling_review_notes.md`에 문서별로 남깁니다. test 문서 메모는 이 파일에 쓰지 않고 test 담당이 따로 보관합니다.
  - main의 기존 `labeling_review_notes.md`는 이전 라벨 기준 기록입니다. 재시작에서는 새로 씁니다.
- 원문 모순 사례(train · val)는 Rule Engine의 INCONSISTENT 검사 시험에 씁니다.

## 5. 채점과 비교 (착수 회의에서 확정)

| 항목 | 정답 판정 |
|---|---|
| JSON · 스키마 | JSON 파싱률, 스키마 준수율(키 · 자료형 · 상태 값). `src/schema.py`로 검사 |
| product_name | value 공백 정규화 후 완전 일치. 정답은 원문 괄호 포함, **비교할 때만** 괄호 부기 · 쉼표 제거 |
| signal_word | value · source_status 모두 일치 |
| ingredients | CAS F1 + (CAS, content) pair F1. content는 min/max 숫자로 비교. CAS 없는 성분 · 영업비밀은 (`is_substitute_data`, content)로 매칭(`nocas` F1). `ke_number`는 채점 안 함 |
| ghs_classification | 별칭표 `eval/hazard_class_alias.csv`로 정규 분류명 변환 → 공백 제거 → (hazard_class, category) 쌍 F1 |
| hazard_statements | H코드 F1. 코드 없이 문구만 있으면 문구 공백 제거 후 일치(H코드 F1과 따로) |
| 다른 칸 오입력 | KE 칸에 KE가 아닌 값(EC 등), 함유량 칸에 CAS — 건수로 셈 |
| 무근거 생성 | 원문에 없는 CAS · H코드 · 분류를 출력한 문서 수 |
| **문서 완전 정답 (주지표 후보)** | 핵심 5필드가 모두 맞고, CAS 없는 성분까지 맞고, 다른 칸 오입력이 없는 문서 비율 |

- 리스트 필드가 비어 있으면 `list_status`가 일치할 때 정답으로 봅니다.
- 채점기를 고치면 `test/`의 회귀 테스트를 같이 고치고 통과시킵니다.
- **별칭표:** test 문서에 별칭표에 없는 분류명이 나오면 test 담당이 행을 추가합니다. 추가한 행은 문서 ID를 빼고 근거와 함께 전달하고, 실험 고정 전에 모든 비교군에 똑같이 적용합니다.

| 비교군 | 출력 폴더 | 역할 |
|---|---|---|
| Base zero-shot | `outputs/base_zs/` | 출발선 |
| Base few-shot (k=2, train에서 추출) | `outputs/base_fs/` | 프롬프트 엔지니어링 대조군 |
| QLoRA 1차 · 2차 · 최종 | `outputs/qlora_r1/` · `qlora_r2/` · `qlora_final/` | 본 과업 결과물. r1 · r2는 val에서 비교하고, test에는 `qlora_final`(r1과 r2 중 고른 것)만 돌림 |

- **효율:** 문서 1건당 평균 생성 시간 · 입력 · 출력 토큰
- **짝 비교:** 같은 문서에서 두 조건의 승 · 패 · 무, 제조사 그룹 단위 부트스트랩 95% 신뢰구간. 문서 수와 그룹 수를 함께 적습니다.
- **분리 보고:** val(조건 선택용, 최종 수치 아님)과 test를 섞지 않습니다. test 안에서도 서식별로 따로 보고하고 합산하지 않습니다. 추출 실패율(실패 건수 ÷ 전체 투입 건수)도 따로 보고하고, 실패 건을 분모에서 빼지 않습니다.

## 6. 모델 · 학습 · 서빙

| 구분 | 설정 | 비고 |
|---|---|---|
| 기반 모델 | Qwen/Qwen3-4B, `enable_thinking=False` | 대안 3B급 |
| 양자화 | NF4 4bit, double quantization, compute bf16 | |
| QLoRA | rank 16 / alpha 32 / dropout 0.05, q · k · v · o_proj | `pipeline/configs/r1.yaml` |
| 최대 길이 | **4096에서 시작**, gradient checkpointing | 파일럿에서 1536이면 정답 JSON 끝이 잘렸음. 새 라벨로 P50/P90/P95/MAX를 다시 재고 입력 + 정답 길이를 함께 봄. 초과 샘플은 목록화(조용히 버리지 않음) |
| batch / accum / epoch | 1 / 8 / 2 | effective batch · 총 step · 학습 시간을 run 설정에 기록 |
| 2차 학습 | r1에서 조건 1개만 변경(epoch / 증강 배수 / 학습률 중 하나) | `pipeline/configs/r2.yaml`. 증강 배수를 바꾸면 step 수도 함께 바뀜 — 보고에 밝힘 |
| 학습 상한 | **2회** (r1 · r2) | 추가 학습은 PM 결정 + 사유 기록 |
| 디코딩 | greedy, seed 고정, `max_new_tokens` = train · val 정답 JSON 최장 토큰 × 1.3 | 비교군 전부 동일. 새 라벨로 실측해 실험 고정 전에 정함. **실험 고정 전 임시 기본값(2026-09-28): 2048**(`eval/infer.py`의 `DEFAULT_MAX_NEW_TOKENS`, test에는 미적용). 옛 라벨 기준 최장 975토큰 × 1.3 ≈ 1,268인데도 임시값 1024에서 fixture 문서가 잘려 2048로 올림. 학습 `max_length`(4096, 입력+정답 합계용)를 그대로 쓰지 않은 이유는 EOS 없이 도는 실패 사례가 그 값까지 다 채워 진단 단계 생성 시간을 크게 늘릴 수 있어서임 |
| 입력 전처리 | pdfplumber → 4항 제목 이전까지 절단 → 2항 P문구 블록 제거 | 학습 · 평가 · 서빙이 `core/`의 같은 추출기를 씀 |
| 서빙 | FastAPI + transformers + peft, 베이스 · 어댑터 동시 보유 | `/extract` `/compare` `/confirm` `/documents` |
| 기록 | SQLite 적재(필수) + JSONL 실행 로그 | 입력 해시 · 출력 · 소요 시간 · 토큰 수 |

**PDF 추출 실패 — 조용히 넘기지 않습니다**

| 상황 | 처리 |
|---|---|
| 4항 제목을 못 찾음 | `data/text/review_required/`로 빼고 사유를 `_cut_log.csv`에 기록. 수동 확인 |
| 항목 제목 형식이 다름 | "4.", "4:", "4 –", "SECTION 4", "4 First-aid"를 모두 인식해야 함 |
| 추출 텍스트 200자 미만 | 스캔 PDF로 보고 제외 목록에 넣음(OCR은 범위 밖) |
| 표가 열 단위로 쏟아짐 · 굵은 글씨 이중 추출 · 텍스트 없는 이미지 쪽 | 정상 입력. 1~3항 값이 텍스트에 있으면 제외하지 않음 |
| 2항 또는 3항 헤더 자체가 없음 | 제외 목록에 넣고 사유 기록 |

## 7. DB 스키마 — 동결

SQLite(온프레미스 전제, 파이썬 내장)를 씁니다. 나중에 PostgreSQL로 옮길 수 있도록 표준 SQL만 씁니다.

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

**설계 결정:**
1. 개정은 덮어쓰지 않고 `revision`을 올려 쌓습니다.
2. 모델 출력과 사람 확정값을 `msds_reviews`에 나눠 저장합니다. 사람이 몇 건 고쳤는지가 효과 지표입니다.
3. `model_name`이 키에 들어가, 같은 문서의 Base · QLoRA 결과를 나란히 저장합니다.

DB 파일(`*.db`)은 커밋하지 않습니다.

| 엔드포인트 | 동작 |
|---|---|
| `POST /extract` | 추출 후 `msds_documents` + 하위 3개 테이블 적재, `document_id` 반환 |
| `POST /compare` | 같은 문서를 Base · QLoRA로 각각 추출해 비교 반환 |
| `POST /confirm` | 담당자 확정 · 수정값을 `msds_reviews`에 저장 |
| `GET /documents` | 적재 이력 목록(파일명 · 제품명 · 모델 · 검토 상태) |

## 8. Rule Engine과 검토 화면

흐름: PDF 업로드 → 텍스트 추출(1~3항 절단) → LLM 추출(Base/QLoRA) → Rule Engine 검증 → 검토 화면(원문 대조) → 확정 · 수정 → DB 적재 · JSON 다운로드

| 검사 | 규칙 | 실패 시 | 사유 |
|---|---|---|---|
| 스키마 | 키 · 자료형 · source_status · list_status 값 | 검토 필요 | FORMAT_ERROR |
| 원문 근거 | 추출값이 원문에 존재하는가. 공백 · 하이픈 정규화 + 별칭(구분 2 ↔ Category 2, 위험 ↔ DANGER) | 원문 확인 필요 | — |
| CAS 형식 | 패턴 + 검증숫자 계산 | 검토 필요 | FORMAT_ERROR |
| CAS 없는 성분 | `cas_number` null이고 `is_substitute_data` false | 검토 필요 | — |
| H코드 형식 | H + 3자리, 조합은 + 연결 | 검토 필요 | FORMAT_ERROR |
| 문구 → H코드 대응 | code null인 문구를 고시 대응표와 대조 | 대응 실패 시 검토 필요 | — |
| GHS ↔ 신호어 · H코드 일관성 | 공식 대응표 기준 명백한 위배만 | 검토 필요 | INCONSISTENT |
| 함유량 합계 | content를 min/max로 파싱해 **하한** 합 ≤ 100. 상한 합은 100을 넘는 것이 정상 | 원문 확인 필요 | — |
| 누락 재판정 | 모델이 비웠는데 원문에 값이 있음 | 검토 필요 | NOT_FOUND |
| 빈값 | source_status · list_status가 자료없음 / 해당없음 | 확인(표시만) | — |

- 모든 검사를 통과한 항목은 OK입니다. 분류가 맞는지는 판단하지 않습니다.
- 대응표(문구 → H코드, GHS ↔ 신호어 · H코드)는 고시 원문에서 만듭니다. 정답 라벨이나 모델 출력에서 거꾸로 만들지 않습니다.

| 화면 영역 | 필수 기능 | 완성 판정 | 하지 않는 것 |
|---|---|---|---|
| 업로드 | PDF 선택 + 샘플 문서 버튼 3개(현행 · 구서식 · 수입품) | 클릭 즉시 추출 시작, 진행 표시 | 드래그앤드롭, 다중 업로드 |
| 원문 패널 | 추출 텍스트 + 근거 하이라이트 | 결과 항목 클릭 시 원문 위치로 스크롤 · 강조 | PDF 원본 렌더링 |
| 결과 패널 | 5개 핵심 항목 + 참고 필드, 항목별 검토 상태 | 상태 3종 색 구분 + 사유 코드 표시 | 신뢰도 점수 |
| 모델 전환 | Base ↔ QLoRA 토글 | 같은 문서를 다시 추출해 차이 표시 | 3개 이상 동시 비교 |
| 확정 | 인라인 수정 + 확정 → `POST /confirm` | `msds_reviews`에 저장 | 코멘트, 승인 워크플로 |
| 이력 | `GET /documents` 목록 | 파일명 · 제품명 · 모델 · 검토 상태 표시 | 통계 대시보드, 검색 · 필터 |

- **화면 판정:** 시연 시나리오 1회(업로드 → 결과 → 모델 전환 → 상태 확인 → 확정 → JSON 다운로드)가 끊김 없이 돌면 통과입니다. 미적 완성도는 판정에 넣지 않습니다.
- 샘플 문서는 train · val 문서에서 고릅니다.

## 9. 단계와 통과 조건

날짜는 PM이 기간을 정한 뒤 채웁니다. 트랙 A(제품: API · DB · Rule Engine · 화면)는 5단계부터 병렬로 진행합니다.

| # | 단계 | 담당 | 통과 조건 | 날짜 |
|---|---|---|---|---|
| 0 | 착수 회의 | 전원 | 13절 확정. test 담당 지정. 이 문서와 CLAUDE.md를 main에 병합 | |
| 1 | test 구성 | PM | 3.3절. 18건 확정(2026-09-28). 개발 쪽에는 건수 · 서식별 건수만 공개 | |
| 2 | 라벨 규칙 파일럿 · 동결 | 데 · 규 → PM | tag `label-rules-frozen` | |
| 3 | train · val 라벨링 · 분할 확정 | 데 · 규 | `validate_labels.py` · `check_splits.py` 통과, tag `split-frozen` | |
| 4 | test 라벨링 · 봉인 | test 담당 + 2차 검수자 | 봉인 해시 커밋, tag `test-sealed` | |
| 5 | 전처리 · 프롬프트 · 채점기 | 평 · 데 · 규 | train · val 텍스트 추출 실패 기록, 채점기 회귀 테스트 통과 | |
| 6 | Base 진단 · 학습 r1 → r2 | 데 · 평 | val 채점 · 짝 비교. r2 채택 기준: val에서 파싱률 · 핵심 필드가 모두 r1과 같거나 나을 때만 | |
| 7 | 모델 · 실험 고정 | PM | `qlora_final`, `max_new_tokens`, 채점기 · 별칭표 해시, 결론 문구(10절)를 고정해 커밋 | |
| 8 | test 평가 1회 | 평 + test 담당 | 비교군 3개(base_zs · base_fs · qlora_final) 각 1회. 생성 중 같은 GPU에서 다른 작업 금지 | |
| 9 | 보고 | 전원 | `report/final_table.md` · `failures.md`(실패 사례 3~5건), 서식별 분리 보고 | |

**늦어질 때**
- API · 화면 연결이 늦으면 노트북 시연으로 대체합니다. 지표가 화면보다 우선입니다.
- DB가 늦으면 `msds_documents` + `raw_json` 적재부터 합니다.
- test는 18건이라 방향 확인 규모입니다. 문서 수 · 그룹 수와 함께 보고합니다.

## 10. 성과 판정 · 결론 문구 (결과 보기 전에 고정)

| 판정 항목 | 성공 | 실패 | 측정 |
|---|---|---|---|
| JSON 파싱률 | test 95% 이상 | 90% 미만 | test 1회 |
| 스키마 준수율 | 95% 이상 | 90% 미만 | test 1회 |
| 핵심 5필드 | 모든 항목이 Base zero-shot 이상 + 1개 이상 개선 | 어느 한 항목이라도 Base보다 하락 | 5절 채점 규칙 |
| 입력 토큰 | Few-shot 대비 60% 이하 | 절감 없음 | 문서 1건당 평균 |
| 추출 실패율 | 10% 이하 + 사유 기록 | 기록 없이 누락 | `data/text/_cut_log.csv` |
| DB 적재 | 1건 업로드 시 4개 테이블 행 생성 + `POST /confirm` 저장 | 하나라도 미동작 | 상시 |
| 검토 화면 | 시연 시나리오 1회 무중단 | 중단 · 수동 개입 필요 | 리허설 |

수치는 목표치이며 착수 회의에서 확정합니다.

**결론 문구 (qlora_final 대 base_fs, 주지표 짝 비교)**

| test 결과 | 결론 |
|---|---|
| 신뢰구간 하한 > 0, 악화 필드 없음 | "재시작 학습에 쓰지 않은 제조사 18건에서 학습의 이점이 확인됐다(파일럿 노출 이력 있음)" (문서 수 · 그룹 수 · 신뢰구간 함께) |
| 신뢰구간이 0을 포함 | "few-shot과의 정확도 차이를 확인하지 못했다" — **동등하다는 뜻이 아니다.** 입력 토큰 비율을 함께 보고 |
| 신뢰구간 상한 < 0 | "few-shot보다 정확도가 낮다" + 떨어진 필드, 입력 토큰 절감과의 교환 관계 |

- **악화 불허 필드:** 파싱률 · 스키마 · 제품명 · CAS F1 · pair F1이 base_fs보다 떨어지면 우위 결론을 내지 않습니다.
- 그룹 수가 적으면 신뢰구간 추정 자체가 불안정하므로, 문서 수와 그룹 수를 함께 적습니다.

## 11. 역할

| 약칭 | 사람 | 맡는 일 |
|---|---|---|
| 데 | 강덕우 | train · val 라벨링, 증강 · JSONL, 학습 실행 |
| 규 | 김건하 | train · val 라벨링, Rule Engine |
| 평 | 양세윤 | 환경, 전처리 · 채점기, 평가 실행, 서빙(API · DB) |
| 프 | 어채은 | PM(결정 · 봉인 승인 · 기록), 검토 화면, 발표 |
| test 담당 | 미정(개발 비참여) | test 수집 · 라벨링 · 보관, 별칭표 추가 행 |
| 2차 검수자 | 미정(개발 비참여) | test 정답 100% 2차 검수 |

- 기획서의 역할 배정을 따른 제안입니다. PM이 착수 회의에서 확정합니다.
- PM은 개발 결정(조건 선택 · 모델 고정)을 맡으므로 test 수집 · 라벨링 · 검수는 맡지 않습니다. 개발 4명 모두 같습니다.

## 12. 파일럿에서 가져오는 교훈 (결과 수치는 가져오지 않음)

| 파일럿에서 생긴 일 | 재시작에서 할 일 |
|---|---|
| val을 현행 서식만으로 만들었더니 Base few-shot이 거의 만점이라 조건 비교가 안 됐음 | val에 수입품 국문판 · 구서식을 섞음(3.2) |
| 최대 길이 1536에서 정답 JSON 끝이 잘림 | 4096에서 시작하고 새 라벨로 다시 잼(6절) |
| 추론 기본 `max_new_tokens`가 규칙(정답 최장 × 1.3)보다 작았음 | 실측값을 실험 고정 전에 정함 |
| 기존 지표로는 EC 번호를 KE 칸에 넣는 오류 · CAS 없는 성분 오류가 문서 정답에 안 드러났음 | 다른 칸 오입력 · `nocas`를 처음부터 채점(5절) |
| 채점 지표를 추가하다 기존 판정을 덮어쓴 버그가 있었음 | 채점기 수정마다 회귀 테스트 |
| 2차 학습에서 증강 배수와 step 수가 함께 바뀌어 원인을 분리할 수 없었음 | 바꾼 조건과 그에 따른 step 변화를 함께 기록 |
| 같은 데이터 · 설정 · seed로 두 번 학습했을 때 val 8건 중 2건의 결과가 달랐음 | 작은 val에서 1~2건 차이로 조건을 고를 때는 짝 비교 신뢰구간과 함께 봄 |
| test 텍스트를 증강 판단에 참고했고, test 정답을 열었음 | test를 저장소 밖에 두고 개발 비참여자가 관리(3.3) |
| test2 정답이 개발 AI 세션에 첨부됐음 | 개발 세션에는 test 파일을 첨부하지 않음 |
| 정답에서 나온 집계값을 `sources.csv`에 적어 공개 저장소에 push했음 | test 행에는 정답 파생값을 적지 않고, 평가 전에는 test 목록 자체를 올리지 않음 |
| 한 폴더를 AI 세션 둘이 같이 쓰다 수정이 겹쳤음 | 한 폴더에 한 세션, 각자 clone |

## 13. 착수 회의 확정 사항

- [ ] 기간(마감 · 발표일)과 9절 날짜
- [ ] test 담당 · 2차 검수자 지정(개발 비참여)
- [ ] test 규모 · 서식 비율(제안: 국문 30건 이상, 제조사 15곳 이상)
- [ ] train · val 후보 문서와 건수(노출 문서 중 국문)
- [ ] 출력 스키마 · DB 스키마 동결 재확인
- [ ] 주지표와 5절 채점 규칙, 10절 목표 수치 · 결론 문구
- [ ] 파일럿 코드 중 가져올 파일 목록(파일 단위 PR)
- [x] main의 기존 라벨 처리(2026-09-28): `data/labels/` → `archive/labels_0923/`, `eval/val_en/` → `archive/val_en_0923/`, `eval/test/` 삭제(지금 test 문서의 옛 정답). 재시작 정답은 `data/labels/`. `docs/labeling_review_notes.md` 정리는 남음
- [ ] `.github/workflows/validate.yml`(PR #1) 병합 여부 — 병합하면 test를 저장소에서 검사하지 않도록 고침
- [ ] 공개 저장소에 남은 파일럿 이력(`feat/web`, PR #2) 처리

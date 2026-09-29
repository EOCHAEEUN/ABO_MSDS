# MSDS Lab 프런트엔드

랜딩페이지와 **문서 검토·문서 목록·실험 비교 화면을 모두 React JSX + CSS**로 구현합니다. 랜딩 화면은 `src/LandingPage.jsx`, 작업공간은 `src/workspace/`의 화면별 JSX에서 수정합니다. 각 화면은 CSS를 직접 import하며, 검토 상태·모달·검색·그래프를 React 상태와 이벤트로 처리합니다. `index.html`과 `workspace.html`에는 React를 연결하는 루트와 메타데이터만 둡니다.

## 실행

Node.js 20.19+ 또는 22.12+가 필요합니다. 저장소 루트에서 실행합니다.

```bash
npm --prefix web ci
npm --prefix web run dev
```

http://localhost:5173 에서 확인합니다. JSX·CSS 수정 사항은 개발 서버에 바로 반영됩니다. 소스 폴더를 `python -m http.server`로 직접 제공하거나 HTML 파일을 더블클릭하면 JSX가 변환되지 않습니다.

## 배포 빌드

```bash
npm --prefix web run build
npm --prefix web run preview
```

http://localhost:4173 에서 빌드 결과를 확인합니다. 산출물은 `web/dist/`에 생성됩니다. `index.html`과 `workspace.html`을 모두 빌드하므로 작업공간 링크도 유지됩니다.

FastAPI에서 제공할 때도 먼저 빌드합니다.

```bash
npm --prefix web run build
source venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

FastAPI는 `web/dist/`만 공개합니다. 다른 정적 서버를 사용한다면 해당 디렉터리를 웹 루트로 지정하세요.

- `/`: 작업공간과 같은 파스텔 배경·로고·카피바라, 반투명 내비게이션과 카드, 문서·추출 결과 비주얼, 프로젝트 소개, 실험 결과를 담은 랜딩페이지
- `/workspace.html#review`: 원문 미리보기, 추출 텍스트, 필드별 검토, 원문 근거, JSON
- `/workspace.html#documents`: 검색·필터, 선택 문서 미리보기, 검토 진행, CSV 다운로드, PDF 업로드
- `/workspace.html#compare`: 실험 비교표, 지표 카드, 막대그래프·추이, 실험 선택

## 예시 모드와 저장

검토 작업공간의 기본은 **예시 모드**입니다. `src/workspace/data.js`의 문서 8건과 비교 수치는 사용자 제공 화면 기반의 UI 전용 예시이며 실제 추론·평가 결과가 아닙니다. 브라우저에서 train/val 라벨, 봉인된 test, 학습 결과를 읽지 않습니다. 랜딩페이지의 실험 표·차트는 재시작 뒤 평가 전이라 비워 두었습니다(파일럿 수치는 쓰지 않음). val 채점 뒤 `report/scores.csv` 값으로 채우며, 지표는 GHS F1·문서 정답률·스키마 준수율입니다. 점수 갱신 시 `src/LandingPage.jsx`의 표·차트·접근성 레이블을 함께 갱신해야 합니다. 일부 문서는 목록 정보만 제공하므로 나머지 필드는 자료없음으로 표시합니다. P문구는 추출 JSON에 포함하지 않습니다.

첫 문서에서 원문에 없는 `H335`를 삭제하거나 근거를 입력하고, 핵심 5필드 확정 후 **확정하고 저장**을 누르면 해당 문서의 검토값이 브라우저 `localStorage`에 저장됩니다. 모델 원본 `extraction`과 담당자 수정값 `reviews`를 분리합니다. JSON 다운로드는 수정 반영값을, JSON 탭의 모델 원본 다운로드는 최초 모델 값을 내보냅니다. 참고 필드와 동결 스키마 키를 유지합니다.

원문 재현은 첨부 화면의 1쪽에 한정하며 나머지 페이지는 미제공으로 표시합니다. PDF 업로드는 최대 30MB, 한 번에 1개입니다. 예시 모드에서는 실제 PDF를 브라우저 내장 뷰어로 표시하고 추출 대기로 남깁니다. PDF는 외부로 전송하지 않으며 새로고침하면 로컬 미리보기가 제거됩니다. 모델 추론·OCR·인증·DB 저장은 프런트엔드에 포함하지 않습니다.

## 저장된 val 실험 결과 모드 (기본)

예시 모드(`?mode=api`가 아닐 때)는 `web/public/results/`의 결과 파일이 있으면 가상 예시 대신 **저장된 val 실험 결과**를 보여 줍니다. 파일이 없으면 예시 데이터로 돌아갑니다.

- `documents.json`: val 문서 × 조건(qlora_r1 · base_fs · base_zs)별 모델 출력, Rule Engine 검토 상태(핵심 5필드), 원문 근거. 파싱에 실패한 출력은 목록에서 빼고 `skipped`에 사유를 남기며, 화면을 열 때 알림으로 표시합니다.
- `compare.json`: `report/scores.csv`의 val 집계. 명세의 7개 값에 GHS F1(`ghs`) · 문서 완전 정답(`exact`)을 더했습니다.
- 다시 만들기(val 추론 · 채점 뒤, 저장소 루트): `python3 -m app.web_results`
- 문서 목록의 "모델" 열과 Split 필터(`val · QLoRA r1` 등)로 조건을 구분합니다. 원본 PDF가 연결되지 않은 결과는 "추출 텍스트" 탭을 자동으로 표시합니다. 저장된 `source_text` 전체와 선택한 필드의 근거를 함께 보여 주며, 쪽 번호가 없으면 항 위치를 표시합니다. `pdf_url`이 제공되면 원본 PDF를 볼 수 있습니다.
- Rule Engine의 `OK`는 "규칙 검사 통과"로 표시하며 정답 또는 원문 완전 일치로 표시하지 않습니다. 근거가 없는 항목은 일괄 확정에서 제외하고, 담당자 확정 상태와 자동 검사 상태를 구분합니다.
- 검토 · 확정값은 브라우저 `localStorage`에만 저장합니다(결과 파일이 바뀌면 초기화). DB 저장은 API 모드에서 합니다.
- val은 조건 선택용 결과이며 최종 보고 수치(test)가 아닙니다.

## 실제 API 연결 계약

`http://localhost:8000/workspace.html?mode=api#documents`로 API 모드를 선택합니다. 현재 `app/main.py`는 빌드된 프런트엔드 서빙만 구현되어 있습니다. API 모드는 백엔드와 같은 origin으로 제공할 때 사용합니다. 아래 API는 **백엔드에서 구현해야 하는 프런트엔드 연동 계약**입니다. API가 없거나 실패하면 오류를 표시하며 예시 데이터로 대체하지 않습니다.

| 호출 | 요청 | 응답 |
|---|---|---|
| `GET /documents` | 없음 | `{ "documents": [Document, ...] }` |
| `POST /extract` | `multipart/form-data`: `file` PDF, `model` (`base`/`qlora`) | `{ "document": Document }` |
| `POST /confirm` | `{ "document_id": id, "reviews": {...}, "confirmed_fields": [...] }` | 성공 시 JSON 또는 204 |
| `POST /compare` | `{ "document_id": id, "split": "val", "subset": "all" }` | 아래 비교 응답 |

모든 경로는 같은 origin의 루트입니다. 백엔드 라우터는 `app/main.py`의 정적 파일 mount **앞에** 등록하세요. 기존 서버의 응답 구조가 다르면 `src/workspace/api.js`에서 변환합니다. 백엔드는 `src/schema.py`로 검증하며 프런트 입력 검사는 사용 편의용입니다.

`Document`는 다음 구조입니다. `src/workspace/data.js`의 `demoDocuments()`가 완전한 예시입니다.

```js
{
  id: "document-1",
  file_name: "sample.pdf",
  language: "한국어",
  page_count: 16,
  submission_number: "...",
  revision_date: "2025.08.12",
  extracted_at: "2025.08.12 10:24",
  updated_at: "2025.08.12 14:37",
  owner: "검토 담당자",
  split: "val",
  model_name: "qlora",
  generation_seconds: 7.2,
  output_tokens: 412,
  extraction: { /* src/schema.py의 MSDSLabel JSON, 모델 원본 */ },
  source: null, // 예시 HTML 재현용. 실 문서는 pdf_url과 rule_results 사용
  pdf_url: "/files/document-1.pdf",
  confirmed_fields: ["product_name", "ingredients"],
  reviews: {
    product_name: {
      confirmed_value: { value: "제품명", source_status: "기재" },
      confirmed_at: "2026-09-26T00:00:00.000Z"
    }
    // 리스트 필드 수정에는 list_status: "기재" 등도 포함
    // 근거를 지정하여 유지한 경우 evidence: { page, source_text } 포함
  },
  rule_results: {
    product_name: {
      review_status: "OK", // OK | REVIEW_REQUIRED | SOURCE_CHECK_REQUIRED
      reason_code: null,
      page: 1,
      section: "1항 가.",
      source_text: "제품명"
    }
    // 나머지 4개 필드도 동일 구조
  }
}
```

브라우저 PDF 뷰어는 페이지·확대 및 선택을 자체 제공하며 텍스트 위치 자동 강조는 지원하지 않습니다. 화면 재현용 HTML과 추출 텍스트 모드에서 필드별 강조를 제공합니다. 실제 PDF 좌표 강조가 필요하면 별도 PDF 렌더러를 연동하세요.

비교 응답에는 `experiments`, `executed_at`, `split`, `subset`을 포함합니다. 각 experiment에는 `id`, `name`, `short`, `condition`, `parsing`, `schema`, `cas`, `pair`, `hcode`, `seconds`, `tokens`가 필요합니다. 비율/F1은 0~100 단위, 시간은 초입니다. 카드 증감은 첫 실험 기준 퍼센트포인트, 생성 시간 증감은 상대 변화율입니다. 서로 다른 평가셋의 수치를 합산하지 않습니다. UI는 봉인된 Test 평가를 요청하지 않습니다.

## 파일 구성

- `src/LandingPage.jsx` · `src/landing-page.css`: 랜딩페이지
- `src/main.jsx`: 랜딩페이지 React 진입점
- `src/workspace-main.jsx`: 작업공간 React 진입점
- `src/workspace/Workspace.jsx`: 작업공간 화면 분기·공통 레이아웃
- `src/workspace/ReviewPage.jsx`: 필드 검토, 원문 근거, JSON, 확정·저장
- `src/workspace/DocumentsPage.jsx`: 문서 목록·검색·필터·미리보기·요약
- `src/workspace/ComparePage.jsx`: 실험 표·카드·막대그래프·추이
- `src/workspace/PreviewPanel.jsx`: 원문 재현·PDF·추출 텍스트
- `src/workspace/WorkspaceDialogs.jsx`: 필드 편집·근거 지정·업로드·비교 설정 모달
- `src/workspace/ui.jsx` · `icons.jsx`: 공통 JSX 컴포넌트와 SVG 아이콘
- `src/workspace/WorkspaceContext.jsx` · `useWorkspaceController.js`: React 상태와 화면 동작
- `src/workspace/model.js`: 검토값 합성·입력 검증·다운로드 유틸리티
- `src/workspace/api.js`: API 호출, 예시 저장, PDF 로컬 미리보기
- `src/workspace/data.js`: UI 전용 예시 데이터, 필드·지표 정의
- `src/workspace/workspace.css`: 작업공간 공통 스타일·반응형 레이아웃
- `src/workspace/review-refresh.css`: 첨부 화면 기반 사이드바·검토 화면 스타일
- `index.html` · `workspace.html`: 메타데이터와 React 루트만 포함하는 실행 진입점
- `vite.config.js`: React 플러그인과 두 진입점 빌드 설정
- `package.json` · `package-lock.json`: 실행 명령과 고정 의존성
- `dist/`: 배포용 빌드 결과, Git 제외

랜딩페이지 상단 메뉴는 소개·검토 예시·실험 결과 섹션으로 이동합니다. 검토 버튼과 미리보기는 검토 작업공간에, 실험 비교 링크는 비교 작업공간에 연결됩니다. 작업공간에는 문서 검토·문서 목록·실험 비교를 오가는 좌측 사이드바가 있으며, 로고를 누르면 랜딩페이지로 돌아갑니다. 문서 검토 화면은 카드형 필드 검토와 위험문구별 원문 대조를 제공하고, 일치 항목 일괄 확정은 Rule Engine이 `OK`로 판정한 미확정 필드에만 적용됩니다. 키보드 포커스, 표 헤더, 입력 레이블, 모달, 상태 알림, 모바일 레이아웃을 제공합니다. CSV는 UTF-8 BOM을 포함해 Excel에서 열 수 있으며 수식으로 해석될 수 있는 셀은 이스케이프합니다.

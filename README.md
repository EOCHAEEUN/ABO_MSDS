# ABO_MSDS

실제 MSDS 1~3항의 핵심 5개 항목을 고정 JSON으로 추출하는 Qwen3-4B QLoRA 모델과, 원문 근거·검토 상태를 붙이는 Rule Engine, 검토 화면을 3일 안에 구현한다. 기준 문서는 기획서 v5(MSDS-PL-2609-05)와 개인별 작업명세서다.

## 현재 상태
- **정답 라벨 세트 v1 편입·분할 완료 (2026-09-23)** — 50건(국문 43 · 영문 7). Train 24 · Val 4는 `data/labels/`, Test 20은 `eval/test/`, 영문 점검용 2는 `eval/val_en/`에 있다.
- 검사: `python scripts/validate_labels.py data/labels`(+`eval/test`, `eval/val_en`) 50건 통과, `python scripts/check_splits.py` 규칙 위반 없음. 상세는 `data/README.md`와 `docs/labeling_review_notes.md`.
- 다음 할 일: tag `split-frozen` → `eval/seal.py --write`로 `eval/test/` 봉인 → tag `test-sealed`.
- 기획서 v5는 48건(영문 5) 기준이지만 실제 세트는 50건(영문 7)이다. 영문 2건은 test 대신 `val_en`으로 뺐다(사유는 `data/README.md` 분할 절).

## 실행 순서
1. `pipeline/extract_text.py` — 원본 PDF → `data/text/`
2. 라벨링 → `data/labels/`, `eval/test/`
3. `pipeline/build_jsonl.py` — 증강·JSONL
4. `pipeline/train_qlora.py --config pipeline/configs/r1.yaml`
5. `eval/infer.py` → `eval/score.py` (Validation으로만 조건 선택)
6. `eval/seal.py --write` → tag `test-sealed`
7. Real Test 최초 평가 (Base zero-shot / few-shot / QLoRA 최종, 각 1회)
8. `app/main.py` 서빙, `web/` 검토 화면

## 원칙
- 전처리·스키마·프롬프트는 `core/` 한 곳에서만 고친다. 수정 시 책임자 리뷰 필수.
- split의 유일한 기준은 `data/splits.csv`다.
- Real Test는 모델 고정 전까지 어떤 추론에도 쓰지 않는다.
- 3일판은 기능을 늘리지 않는다. 여유 시간은 실패 분석과 발표에 쓴다.

## 파일트리와 담당
```
ABO_MSDS/
├── README.md                  # [어채은] 과업 한 줄 정의, 실행 순서, 폴더별 담당자
├── requirements.txt           # [양세윤] transformers·peft·bitsandbytes·pdfplumber·fastapi 버전 고정
├── .gitignore                 # [어채은] raw PDF·어댑터 가중치·.env 제외
├── .gitattributes             # [어채은] *.json text eol=lf — 줄바꿈 차이로 해시가 바뀌는 것 방지
├── .env.example               # [어채은] KOSHA_API_KEY= (실제 키는 .env, 커밋 금지)
│
├── core/                      # [공통] 학습·평가·서빙이 모두 import하는 단 하나의 구현, 수정 시 책임자 리뷰 필수
│   ├── preprocess.py          # [양세윤 v1 → 강덕우 확정] 추출 → 4항 전 절단 → 2항 안에서만 P문구 블록 제거
│   ├── schema.py              # [양세윤] + 김건하 — 동결 스키마 정의 + 스키마 준수 검사
│   ├── prompt.py              # [양세윤] + 강덕우 — 시스템 프롬프트, few-shot 조립, enable_thinking=False
│   └── normalize.py           # [양세윤 v1] + 김건하 — 신호어·구분 N 정규화, content min/max 파싱, 별칭표 연동
│
├── data/                      # [강덕우·김건하]
│   ├── README.md              # [어채은] doc_id 규칙, split 기준, 봉인·태그 규칙, Gold 수정 절차
│   ├── raw/                   # [강덕우] 원본 PDF (gitignore)
│   ├── text/                  # [양세윤 v1 → 강덕우 확정] preprocess 결과 {doc_id}.txt
│   │   └── _cut_log.csv       # doc_id, status, section4_pattern, p_block_pattern, cut_page, token_count, note
│   ├── sources.csv            # [강덕우] doc_id, 원본 파일명, 언어, 서식, 제조사, split_group, 건수 요약
│   ├── splits.csv             # [강덕우] split의 유일한 기준, 확정 후 tag split-frozen
│   ├── labels/                # [강덕우 14건 · 김건하 14건] Train 24 + Val 4 정답 {doc_id}.json
│   ├── train.jsonl            # [강덕우] Train 증강 8~10배
│   └── val.jsonl              # [강덕우] Val 원본 + 건당 변형 5개
│
├── pipeline/                  # [강덕우] 데이터 → 학습
│   ├── extract_text.py        # raw/ → text/ 일괄 변환, _cut_log.csv 기록
│   ├── augment/
│   │   ├── renderers.py       # generate_msds.py 렌더러 5종만 이식 (난수 조합 로직 제외)
│   │   └── check_forbidden.py # 성분·분류·H코드·함유량이 바뀐 변형 검출
│   ├── build_jsonl.py
│   ├── length_stats.py        # P50/P90/P95/MAX → report/length_stats.md
│   ├── train_qlora.py         # + 양세윤(스크립트 지원)
│   └── configs/
│       ├── r1.yaml            # rank 16 / alpha 32 / lr 2e-4 / 2 epoch / accum 8
│       └── r2.yaml            # r1에서 조건 1개만 변경
│
├── eval/                      # [양세윤·어채은]
│   ├── infer.py               # [양세윤] 조건 × split 추론, test는 명시 플래그 필요
│   ├── score.py               # [양세윤] 파싱률·스키마·필드별·CAS F1·pair F1·H코드 F1
│   ├── seal.py                # [양세윤 작성 · 어채은 실행] --write / --verify
│   ├── fewshot.json           # [양세윤] few-shot 예시 2건 doc_id 고정 (Train에서만)
│   ├── test/                  # [어채은 국문 15 · 양세윤 영문 5] Real Test 정답 20건, 봉인 후 수정 금지
│   ├── val_en/                # 영문 파이프라인 점검용 2건, 성능 보고에 쓰지 않음
│   └── hazard_class_alias.csv # 분류명 원문 → 고시 정규 분류명, normalize.py가 참조
│
├── outputs/                   # [양세윤] 모델 출력 {조건}/{val|test}/{doc_id}.json
├── runs/                      # [강덕우] {날짜}_{r1|r2}/ — config.json·loss 로그만 커밋
│
├── app/                       # [양세윤·김건하]
│   ├── main.py                # [양세윤] FastAPI POST /extract, /compare
│   ├── model.py               # [양세윤] 베이스 + 어댑터 동시 로드, 모델 전환
│   ├── api_spec.md            # [양세윤] 입출력 명세
│   └── rules/                 # [김건하] engine.py, checks/ 9개, tables/, tests/
│
├── web/                       # [어채은] 3일판 단일 검토 화면, mock/은 김건하 제공
│
├── docs/                      # [어채은] labeling_review_notes.md — 판정 결과·원문 모순 문서·PDF 추출 함정
├── src/                       # schema.py — Pydantic 스키마 (정답 라벨·모델 출력·FastAPI 공용)
├── scripts/                   # validate_labels.py(스키마 검사), check_splits.py(분할 규칙 검사)
│
└── report/                    # decisions[어채은] env_check[양세윤] length_stats[강덕우] scores[양세윤]
                               # label_audit/[어채은·강덕우·김건하] test_manifest[어채은]
                               # failures[강덕우+김건하] final_table[양세윤] slides[어채은 편집]
```

## Git 태그
- `split-frozen` — splits.csv 확정 직후
- `test-sealed` — Test 정답 확정 후 `eval/seal.py --write` 직후

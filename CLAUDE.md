# ABO_MSDS

MSDS 1~3항 → 핵심 5필드 고정 JSON 추출(Qwen3-4B QLoRA) + Rule Engine 검토 상태 + SQLite 적재 + 검토 화면. 3일 팀 과업.
상세: @docs/plan.md · 팀 규칙: @docs/TEAM_GUIDE.md · 라벨 표기 세부: data/README.md · 판정 기록: docs/labeling_review_notes.md

## 절대 규칙
- **Real Test 봉인:** eval/test/(20건)는 3일차 09:30 전까지 어떤 모델에도 넣지 않는다(Base 포함). test 추론, few-shot·프롬프트 예시, 화면 샘플, 조건 선택 근거로 쓰지 않는다.
- Test 정답 검수나 길이 측정을 명시적으로 요청받은 경우가 아니면 eval/test/*.json과 labeling_review_notes.md의 test 문서 메모를 열지 않는다. 열었더라도 그 값을 코드·정규식·프롬프트에 반영하지 않는다.
- **데이터 용도는 data/splits.csv가 유일한 기준:** 학습(증강·JSONL)과 few-shot은 split=train 문서만, 조건 선택(1·2차 비교·모델 고정)은 split=val 문서만 쓴다. data/labels/에는 train과 val이 섞여 있다. eval/val_en/은 영문 점검용이라 학습·보고 수치에 쓰지 않는다. splits.csv는 임의로 바꾸지 않는다.
- **정답은 사람이 확정한다.** 요청받지 않은 정답 값 수정은 하지 않는다. 정답을 고칠 때는 JSON 수정 → `python3 scripts/validate_labels.py data/labels`(test면 eval/test) → docs/labeling_review_notes.md에 이유 한 줄 → 커밋 메시지 `fix(label): KR-XXX-001 …` 순서를 지킨다. test-sealed 태그 이후 eval/test/는 수정 금지.
- **스키마 동결:** 출력 JSON 키 이름과 상태값(기재·자료없음·해당없음), DB 테이블·열 이름을 바꾸지 않는다. 출력 스키마는 src/schema.py가 단일 기준이며 core/schema.py 등에 별도 정의를 만들지 않는다.
- **커밋 금지:** data/raw/·*.pdf(저작권), runs/의 가중치·체크포인트(*.safetensors, *.bin, *.gguf, checkpoint-*/; config.json·loss 로그만 커밋), .env, 기획서 원본·수요조사 자료(공개 저장소).
- **Git:** main에 직접 커밋·push하지 않는다. 개인 브랜치에서 작업하고 PR로 병합한다. `git branch -M main`·`git push --force` 금지.

## 설계 원칙 (코드 작성 시)
- 모델은 원문에 적힌 값만 읽는다. 프롬프트·후처리에서 H코드·분류·CAS를 지식으로 채우거나 추정하지 않는다.
- 모델 출력은 스키마 JSON뿐이다. evidence·review_status는 Rule Engine(app/rules/)이 붙인다.
- P문구는 출력에서 빼고 입력에서도 2항 P문구 블록을 잘라낸다. 전처리·프롬프트는 학습·평가·서빙이 core/ 하나를 공유하며, core/ 수정은 담당자 리뷰 필수.
- 추출 실패는 조용히 버리지 않는다. 사유를 기록하고 실패 건을 평가 분모에서 빼지 않는다.
- 3일판은 기능을 늘리지 않는다.

## 환경
- WSL2 Ubuntu 24.04, RTX 4060 Laptop 8GB. venv 활성화 후 저장소 루트에서 `python3`로 실행
- 검사: `python3 scripts/validate_labels.py data/labels` (eval/test, eval/val_en, outputs/<조건>/val도 가능) / `python3 scripts/check_splits.py`

## 규약
- doc_id: `KR|EN-제조사약칭-번호`, 정답·출력 파일명은 `{doc_id}.json`
- 모델 출력: `outputs/{base_zs,base_fs,qlora_r1,qlora_r2,qlora_final}/{val|test|val_en}/{doc_id}.json`. 이 파일에는 모델이 낸 JSON만 둔다(파싱 실패도 모델 출력 그대로 저장해 실패로 집계). 시간·토큰·원문 로그는 `.jsonl`, 채점 상세는 `*.json`이 아닌 이름으로 둔다(검사기가 폴더의 `*.json`을 모두 검사함)
- 전처리: `data/text/{doc_id}.txt`, 실패 기록은 `data/text/_cut_log.csv` + `data/text/review_required/` (실패 로그 파일을 따로 만들지 않는다)
- 점수: `report/scores.csv` (condition, split, subset, metric, value). 평가셋별 행을 나누고 합산하지 않는다
- 학습: `pipeline/configs/r1.yaml` 기준, r2는 조건 1개만 변경. 기록은 `runs/{날짜}_{r1|r2}/`
- 결정 기록: report/decisions.md
- 커밋 prefix: `feat:` / `fix:` / `fix(label):` / `docs:` / `chore:`
- Git 태그: `split-frozen`(분할 확정) → `test-sealed`(`eval/seal.py --write` 직후)

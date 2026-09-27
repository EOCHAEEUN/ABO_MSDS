# C안 개발 인계 (2026-09-27)

새 개발 세션과 팀을 위한 인계 메모입니다. **이 메모에는 test2의 값·분류·오류 설명을 넣지 않습니다.** 문서 ID, 배정, 적격성, 노출 이력, 처리 상태만 적습니다.

앞선 개발 세션에 test2 정답 정보가 유입됐습니다(`report/decisions.md` "test2 정답 정보의 개발 세션 유입"). 그래서 이후 작업은 새 세션에서 합니다.

## 새 세션이 지킬 것
- 다음 자료는 열지 않습니다. 판정이 필요하면 검수 담당에게서 결과만 받습니다.
  - test2 문서와 보류 문서의 정답 파일
  - zip의 `eval/test2/`와 `eval/test2_hold/`
  - 검토 메모의 test2 문서별 내용
  - 새 별칭표의 "라벨에 나온 문서" 열 가운데 test2 항목
  - `data/sources.csv`의 test2 행 집계 열(`n_ingredients` · `signal_word` 등). doc_id와 메타데이터 열(lang · form · manufacturer · split_group)만 본다. 저장소 사본에서는 비웠고(09-27), 이 파일의 `git diff` · `git log -p` · `git show defa79b`는 열지 않는다(삭제된 줄에 값이 있다)
- 대화에 test2 파일을 첨부하지 말아 달라고 사용자에게 요청합니다. 첨부되면 작업을 멈추고 decisions.md에 기록합니다.
- CLAUDE.md의 test2 규칙과 `eval/gate.py`의 게이트를 따릅니다. 학습은 사용자 승인 후에만 합니다.

## 저장소 현재 상태 (확인됨)
| split | 건수 | 비고 |
|---|---:|---|
| train | 24 | 신규 2건(KR-NOROO-007, KR-DUKSAN-001)은 정답·텍스트가 아직 저장소에 없음(라벨 패키지에도 없음) |
| val | 8 | 두 번째 수집분 KR-GSC-003 · 004 추가(정답 반영). 기존 조건의 val 출력은 6건 기준이라 새 val로 다시 돌려야 함 |
| test | 20 | 기존 Real Test. 노출 이력이 있어 보조 평가로만 씀 |
| test2 | 14 | `pending` 8(KR-KZ-001·002·003, KR-DAIKIN-001·002·003, KR-NEOGEN-001, KR-KNAUF-001) · `exposed` 6(KR-SEBANG-001·002, KR-ASIACEM-001, KR-CLOVER-001, KR-NEOGEN-002, KR-KNAUF-002). 정답은 저장소 밖(`eval/test2/` 0건). 주 분석 대상 확정 0건 |
| val_en | 13 | 두 번째 수집분 4건 추가(EN-CQV · WURTH · LOTTE · AKCHEM-001, 정답 반영) |
| excluded | 8 | EN-3M-002, PT-ROBERLO-001, KR-HENKEL-001, EN-SOIL-001 · 002, KR-HENKEL-002, EN-SEBANG-001, KR-AEKYUNG-001(스캔 PDF) |

- 도구 상태:
  - `eval/experiment.json`: 고정 전이고, `max_new_tokens`와 `qlora_final` 어댑터가 비어 있습니다. `--freeze`는 test2 역할 목록에 `pending`이 남아 있으면 거부합니다. 고정 때 분석 대상 목록(doc_id · 역할 · 언어 · 서식 · 그룹)을 기록하고, 그 뒤 바뀌면 출력 생성 · 채점을 거부합니다.
  - `eval/test2_roles.csv`: test2 문서마다 역할(main · oldform · exposed · pending) 한 줄. 중복 doc_id는 거부됩니다. 채점 · 짝 비교 · 분할 검사 · 배정 제안이 이 목록을 씁니다.
  - 봉인: test2 1단계·2단계 모두 아직입니다(1단계는 건수를 채운 뒤).
  - 테스트: `test/`의 7개 파일(61건)과 `tests/test_normalize.py`(32건)가 모두 통과한다. 각 파일은 `python test/파일명.py`로 실행한다.
- 커밋: `26a2172` · `666751e`는 `feat/web`. 역할 목록 작업 `02e0857`과 두 번째 수집분 반영은 `feat/eval-test2-roles`(PR #2 → `feat/web`, 병합 전)에 있다. 브랜치는 더 나누지 않는다(결정권자).
- 파일 위치: 라벨 패키지 `gold_v3_추가분.zip`은 저장소 밖 `~/abo_msds/labeling/`에 있다. test2 · 보류 정답과 별칭표 v3가 들어 있으니 개발 세션은 열지 않는다. `.gitignore`는 `*.zip`과 대소문자 무관 `.pdf`를 막는다.

## 두 번째 수집분 17건 — 반영함 (09-27, `report/decisions.md` "두 번째 수집분 반영")
다시 배정하지 않고(결정 ③) 라벨링 쪽 추가행을 기준으로 중복 · 적격성 · 그룹 충돌 · 노출만 바로잡아 `splits.csv` · `sources.csv`에 17행씩 덧붙였다. note는 새로 썼다(라벨링 쪽 test2 · 보류 행 note는 열지 않음).

| 문서 | 라벨링 쪽 패키지 | 반영한 배정 |
|---|---|---|
| KR-SEBANG-001 · 002, KR-ASIACEM-001, KR-CLOVER-001(구서식) | test2 | test2, 역할 `exposed` |
| KR-NEOGEN-002, KR-KNAUF-002 | excluded(부적격 판정 아님 — 결정권자 확인) | test2, 역할 `exposed` |
| KR-GSC-003 · 004 | val | val (정답 반영) |
| EN-CQV-001, EN-WURTH-001, EN-LOTTE-001, EN-AKCHEM-001 | val_en | val_en (정답 반영) |
| EN-SOIL-001 · 002 | val_en | **excluded**(기존 test 제조사의 영문판, 기존 test 평가 전 개발 노출 방지 — 결정권자 결정) |
| KR-HENKEL-002 | excluded | excluded(노출 제조사) |
| EN-SEBANG-001 | excluded | excluded(test2 제조사의 영문판) |
| KR-AEKYUNG-001 | excluded(스캔 PDF) | excluded(범위 밖) |

- test2 그룹 7행(위 test2 6건 + EN-SEBANG-001)은 `sources.csv` 집계 열을 비워 넣었다.
- 중복 2건은 해시로 확인했다: Würth PDF 사본, `KCC – EP1160(H)-B` = 기존 EN-KCC-001 원본.
- **아직 안 한 것:**
  - 원본 PDF 17개를 `data/raw/`에 두기. 받은 PDF zip은 삭제됐으니 라벨링 쪽에서 다시 받아야 합니다. `sources.csv`의 `source_file` 이름 그대로 넣어야 봉인 · 추출이 찾습니다(중복 2개 제외).
  - test2 · 보류 정답은 1단계 봉인 뒤 라벨링 쪽이 복사합니다.
  - 별칭표 v3와 검토 메모 v3 추가분은 개발용 부분을 분리한 뒤 받습니다.

## 09-27 결정 (외부 검토 권고 ①~④ 채택, `report/decisions.md`)
- ① `data/sources.csv`의 test2 집계 열을 비웠다. `check_splits.py`가 다시 채워지면 오류를 낸다.
- ② 정답이 유입된 6건(위 표)은 독립 주평가에 넣지 않고 test2에 역할 `exposed`로 보존한다. 버리거나 train으로 보내지 않는다. 기존 test2 8건은 역할 `pending`이다. 영향 점검 전에는 완전한 미노출 자료로 보지 않는다. 다만 저장소에 값이 있었다는 사실만으로 모델에 쓰였다고 단정하지도 않는다.
- ③ 17건은 다시 배정하지 않는다. 균형 배정 규칙(`docs/plan_c.md` 4절 5항)은 승인됐고 다음 수집분부터 적용한다.
- ④ 주 분석 대상은 `eval/test2_roles.csv`의 `main`이다. 채점 · 짝 비교가 같은 목록을 쓰고, 목록의 모든 문서를 분모에 둔다.
- KR-DUKSAN-001은 "내용을 알았으니 train"의 선례가 아니다. train 배정에는 학습에 쓸 이유와 라벨 적격성이 있어야 한다.

## 할 일 (순서대로)
1. **별칭표 점검** (검수 담당)
   - v2·v3에서 추가된 매핑 중 test2 문서를 계기로 생긴 행을 골라, "이 원문 표현을 이 정규 분류명으로 바꿔도 의미가 같은가"를 출처와 함께 확인합니다.
   - 같은 규칙을 모든 비교군에 적용합니다.
   - "test2를 계기로 추가됨" 이력은 남깁니다.
   - 개발 쪽에는 판정과, 문서 ID 열을 분리한 사본만 전달합니다. 그 뒤 `eval/hazard_class_alias.csv`를 교체합니다(채점 파일이므로 실험 고정 전에 끝내야 함).
2. **test2 영향 점검** (검수 담당)
   - `pending` 8건마다 `eval/test2_roles.csv` note의 경로가 모델 · 전처리 · 프롬프트 · 조건 선택에 영향을 줬는지 봅니다.
   - 그 결과로 `main` 또는 `exposed`를 정합니다. 개발 쪽에는 역할과 한 줄 사유만 전달합니다.
   - 실험 고정 전에 `pending`이 0건이어야 합니다(`--freeze`와 `check_splits.py --final`이 막음).
   - `main`이 영향받은 그룹(노출 · 점검 대기 문서가 있는 split_group)에 있으면 `check_splits.py`가 경고합니다. 분리를 권고합니다.
3. **zip 반영** → **CSV 행 · 역할 · val · val_en 정답은 반영함(09-27).** 남은 것:
   - 원본 PDF 17개를 `data/raw/`에 `source_file` 이름으로 두기(중복 2개 제외)
   - 검토 메모의 개발용 부분(라벨링 쪽이 test2 부분을 분리해 전달)
   - **`eval/test2/` 정답은 복사하지 않습니다.** 순서는 test2 목록 확정(건수 충족) → `eval/seal.py --split test2 --write-docs`(결정권자가 실행) → 라벨링 쪽이 정답 복사입니다. 1단계 봉인은 `eval/test2/`에 정답이 있으면 거부됩니다.
4. **신규 배정 규칙** → **승인됨(09-27), 다음 수집분부터 적용.** `docs/plan_c.md` 4절 5항, `scripts/propose_splits.py`(제안표만 만들고 splits.csv는 고치지 않음). test2 목표는 `main`과 `pending`만 셉니다. 영향받은 그룹을 따르는 신규 문서는 주평가로 세지 않습니다. **원하는 구성이 나올 때까지 시드를 바꾸지 않습니다.**
5. **목표 표현** → **결정 · 반영 완료.** 주 분석 대상(역할 `main`, 국문 현행 · 수입품 국문판)으로 최소 30 · 목표 40, 그 안에서 3:1. 채점(`score.py`)과 짝 비교(`paired.py`)도 역할별로 나눕니다. 문서 수와 제조사 그룹 수를 함께 보고하며, 30건을 채웠다고 우위가 입증되는 것은 아닙니다.
6. **스캔 PDF 집계:** "수집 문서 중 범위 밖 제외"와 텍스트 PDF의 "추출 실패율"을 구분해서 셉니다.
7. **그다음**
   - train·val 텍스트 추출(`--split train,val`). 새 val 8건(KR-GSC-003 · 004 포함)으로 비교군 val 출력을 다시 만든다
   - 새 정답으로 생성 길이 재측정 → `experiment.json`
   - C1 데이터 생성 → C1 학습(승인 후)
   - val 비교 → `qlora_final` 확정
   - test2 역할 확정(`pending` 0건) → test2 2단계 봉인 → 실험 고정·커밋 → 최종 평가
8. **수집 우선순위:**
   - 이번 17건 중 train으로 간 문서가 0건입니다. train은 23~28건, val은 7건 더 필요합니다(지금 train 24 · val 8).
   - test2 주 분석 대상은 확정 0건입니다. 건수와 3:1 비율(±1)을 함께 맞춰야 합니다. 30건이면 현행 21~23 · 수입품 7~9, 40건이면 현행 29~31 · 수입품 9~11입니다(`check_splits.py`가 쓰는 반올림 기준).
     - `pending` 8건(현행 3 · 수입품 5)이 모두 `main`이 되는 경우: 최소 22건을 더 모으되 수입품은 2~4건만 더합니다. 예를 들어 현행 20 + 수입품 2 → 23 : 7입니다. 현행만 22건을 더하면 25 : 5가 되어 비율을 벗어납니다.
     - 8건이 모두 `main`이 되지 않는 경우: 새 문서로 현행 21~23 · 수입품 7~9를 모읍니다.
   - 새 문서는 기존 어느 분할에도 없고 영향받은 그룹(SEBANG · ASIACEM · CLOVER · NEOGEN · KNAUF, 점검 결과에 따라 KZ · DAIKIN)도 아닌 제조사의 국문 현행 문서가 우선입니다. 4번 규칙으로 배정합니다.

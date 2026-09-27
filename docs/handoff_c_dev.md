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
| train | 24 | 신규 2건(KR-NOROO-007, KR-DUKSAN-001)은 정답·텍스트가 아직 저장소에 없음 |
| val | 6 | |
| test | 20 | 기존 Real Test. 노출 이력이 있어 보조 평가로만 씀 |
| test2 | 8 | 현행 3(KR-KZ-001·002·003), 수입품 5(KR-DAIKIN-001·002·003, KR-NEOGEN-001, KR-KNAUF-001). 정답은 저장소 밖(`eval/test2/` 0건). **8건 모두 역할 `pending`(영향 점검 대기)** — 주 분석 대상 확정 0건 |
| val_en | 9 | |
| excluded | 3 | EN-3M-002, PT-ROBERLO-001, KR-HENKEL-001 |

- 도구 상태:
  - `eval/experiment.json`: 고정 전이고, `max_new_tokens`와 `qlora_final` 어댑터가 비어 있습니다. `--freeze`는 test2 역할 목록에 `pending`이 남아 있으면 거부합니다. 고정 때 분석 대상 목록(doc_id · 역할 · 언어 · 서식 · 그룹)을 기록하고, 그 뒤 바뀌면 출력 생성 · 채점을 거부합니다.
  - `eval/test2_roles.csv`: test2 문서마다 역할(main · oldform · exposed · pending) 한 줄. 중복 doc_id는 거부됩니다. 채점 · 짝 비교 · 분할 검사 · 배정 제안이 이 목록을 씁니다.
  - 봉인: test2 1단계·2단계 모두 아직입니다.
  - 테스트: `test/`의 7개 파일(61건)과 `tests/test_normalize.py`(32건)가 모두 통과한다. 각 파일은 `python test/파일명.py`로 실행한다.
- 커밋: `26a2172`(sources.csv 집계 열 숨김) · `666751e`(목표 기준 · 배정 규칙 초안 · 이 메모)는 `feat/web`에 push됨. 그 뒤의 역할 목록 작업(평가 코드)은 별도 브랜치(`feat/eval-test2-roles`)로 나누기를 권고받음.

## 두 번째 수집분 17건 (라벨링 쪽 보고. 저장소 미반영·미검증)
**다시 배정하지 않는다(09-27 결정 ③).** 라벨링 전에 기록된 제안 배정을 기준으로 중복 · 적격성 · 그룹 충돌 · 노출만 바로잡는다. 아래 "반영할 배정"이 그 결과다.

| 문서 | 라벨링 쪽 제안 | 반영할 배정 | 이 세션 유입 |
|---|---|---|---|
| KR-SEBANG-001, KR-SEBANG-002 | test2 (현행) | **test2, 역할 `exposed`**(노출 보조평가) | 정답 유입 |
| KR-ASIACEM-001 | test2 (현행) | **test2, 역할 `exposed`** | 정답 유입 |
| KR-CLOVER-001 | test2 (구서식, 따로 보고) | **test2, 역할 `exposed`**. 노루 외 첫 구서식 | 정답 유입 |
| KR-GSC-003, KR-GSC-004 | val (GSC 그룹을 따름) | val | 정답 첨부됨(val) |
| EN-CQV-001, EN-SOIL-001, EN-SOIL-002, EN-WURTH-001, EN-LOTTE-001, EN-AKCHEM-001 | val_en | val_en. **EN-SOIL-001 · 002는 결정권자 확인 필요.** 기존 test 제조사(SOIL)의 영문판이라 val_en에 두면 test 제조사 서식이 개발에 노출된다. 검토 권고: 기존 test 평가가 끝나기 전에는 val_en에 넣지 않고 사유를 적어 `excluded`로 보존 | 정답 첨부됨(val_en) |
| KR-NEOGEN-002, KR-KNAUF-002 | 보류 | **test2, 역할 `exposed`**. 라벨 담당이 중복 · 개정판 · 적격성을 확인한 뒤 반영(부적격이면 excluded) | 정답 유입 |
| KR-HENKEL-002 | 보류 | **excluded 권고**(HENKEL은 노출 제조사, KR-HENKEL-001과 같은 사유) | 정답 유입 |
| EN-SEBANG-001 | 보류 | **excluded 권고**(test2 제조사의 영문판이라 val_en에 두면 개발 중 서식이 노출됨) | 정답 유입 |
| 애경산업 1건 (ID 미확인) | 제외 | 스캔 PDF라 범위 밖. "범위 밖 제외"로 따로 셈 | — |

라벨링 쪽은 zip 안 PDF 19개 중 중복 2개를 뺐다고 보고했습니다. 하나는 EN-KCC-001과 같은 파일이고, 하나는 Würth 파일이 두 번 들어간 것입니다. 이 내용은 zip과 대조해 확인해야 합니다.

라벨링 쪽 현황표는 KR-HENKEL-001이 test2에 있고 구서식 목표가 남아 있던 **옛 상태를 기준으로** 작성됐습니다. 반영할 때는 옛 `splits_alt`가 아니라 **현재 `data/splits.csv`에 행을 추가**합니다.

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
3. **zip 반영** (범위를 줄여서, 위 표의 "반영할 배정"대로)
   - 반영 대상: `data/labels` · `eval/val_en` 정답, 대조를 마친 sources · splits 행, 검토 메모의 개발용 부분.
   - test2로 가는 6건은 `splits.csv`에 test2 행, `eval/test2_roles.csv`에 역할 `exposed`와 note(유입 경로 · 날짜)를 함께 넣습니다. `sources.csv`의 test2 행은 집계 열을 비운 채로 넣습니다.
   - **`eval/test2/`와 보류분은 복사하지 않습니다.** 순서는 test2 목록 확정 → `eval/seal.py --split test2 --write-docs` → 정답 복사입니다. 1단계 봉인은 `eval/test2/`에 정답이 있으면 거부됩니다.
   - 중복 2건과 17건 배정을 zip과 대조한 뒤 `python scripts/check_splits.py`로 검사합니다.
4. **신규 배정 규칙** → **승인됨(09-27), 다음 수집분부터 적용.** `docs/plan_c.md` 4절 5항, `scripts/propose_splits.py`(제안표만 만들고 splits.csv는 고치지 않음). test2 목표는 `main`과 `pending`만 셉니다. 영향받은 그룹을 따르는 신규 문서는 주평가로 세지 않습니다. **원하는 구성이 나올 때까지 시드를 바꾸지 않습니다.**
5. **목표 표현** → **결정 · 반영 완료.** 주 분석 대상(역할 `main`, 국문 현행 · 수입품 국문판)으로 최소 30 · 목표 40, 그 안에서 3:1. 채점(`score.py`)과 짝 비교(`paired.py`)도 역할별로 나눕니다. 문서 수와 제조사 그룹 수를 함께 보고하며, 30건을 채웠다고 우위가 입증되는 것은 아닙니다.
6. **스캔 PDF 집계:** "수집 문서 중 범위 밖 제외"와 텍스트 PDF의 "추출 실패율"을 구분해서 셉니다.
7. **그다음**
   - train·val 텍스트 추출(`--split train,val`)
   - 새 정답으로 생성 길이 재측정 → `experiment.json`
   - C1 데이터 생성 → C1 학습(승인 후)
   - val 비교 → `qlora_final` 확정
   - test2 역할 확정(`pending` 0건) → test2 2단계 봉인 → 실험 고정·커밋 → 최종 평가
8. **수집 우선순위:**
   - 이번 17건 중 train으로 가는 문서가 0건입니다. train은 23~28건, val은 7건 더 필요합니다.
   - test2 주 분석 대상은 확정 0건입니다. 건수와 3:1 비율(±1)을 함께 맞춰야 합니다. 30건이면 현행 21~23 · 수입품 7~9, 40건이면 현행 29~31 · 수입품 9~11입니다(`check_splits.py`가 쓰는 반올림 기준).
     - `pending` 8건(현행 3 · 수입품 5)이 모두 `main`이 되는 경우: 최소 22건을 더 모으되 수입품은 2~4건만 더합니다. 예를 들어 현행 20 + 수입품 2 → 23 : 7입니다. 현행만 22건을 더하면 25 : 5가 되어 비율을 벗어납니다.
     - 8건이 모두 `main`이 되지 않는 경우: 새 문서로 현행 21~23 · 수입품 7~9를 모읍니다.
   - 새 문서는 기존 어느 분할에도 없고 영향받은 그룹(SEBANG · ASIACEM · CLOVER · NEOGEN · KNAUF, 점검 결과에 따라 KZ · DAIKIN)도 아닌 제조사의 국문 현행 문서가 우선입니다. 4번 규칙으로 배정합니다.

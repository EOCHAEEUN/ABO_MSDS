# data/ 규칙  [어채은]

## doc_id
- 국문 `KR-{제조사약칭}-{3자리}`, 영문 `EN-{제조사약칭}-{3자리}` (예: `KR-NOROO-001`)
- 정답 JSON 파일명 = `{doc_id}.json`

## 분할
- `splits.csv`가 split의 유일한 기준이다. 폴더로 train/val을 나누지 않는다.
- 증강 전에 원본 문서 단위로 나눈다. 제조사는 겹치지 않게 배정한다 (노루 구서식 예외만 허용: Train 2 / Test 3).
- Val 4건과 few-shot 예시 2건(Train)은 착수 회의에서 먼저 정한다.

## 경로
| 대상 | 경로 |
|---|---|
| 원본 PDF | `data/raw/` (커밋 금지) |
| 전처리 텍스트 | `data/text/{doc_id}.txt`, 절단 기록 `data/text/_cut_log.csv` |
| Train·Val 정답 | `data/labels/{doc_id}.json` |
| Test 정답 | `eval/test/{doc_id}.json` |

## 태그
- `split-frozen`: splits.csv 확정 직후. 이후 Test 구성 변경 금지
- `test-sealed`: Test 정답 확정 후 `eval/seal.py --write` 실행 직후. 이후 `eval/test/` 수정 금지

## Gold 수정 절차
- 애매한 필드는 메모를 남기고 넘어간다. 판정은 어채은.
- 봉인 이후 수정이 불가피하면 `report/decisions.md`에 사유를 남기고 발표에서 밝힌다.

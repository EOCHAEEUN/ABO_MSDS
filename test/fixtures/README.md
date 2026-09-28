# 코드 테스트용 fixture

증강 코드(`pipeline/augment/`, `pipeline/build_jsonl.py`)의 회귀 테스트 입력입니다. **학습 · 평가 데이터가 아닙니다.**

- `labels/`: 09-23 옛 라벨(재시작 전) 7건. PM 승인(2026-09-28)으로 코드 테스트에만 씁니다.
- `text/`: 같은 문서의 1~3항 절단 텍스트(파일럿 전처리 결과).
- `splits.csv`: fixture 전용 분할표. `data/splits.csv`와 무관합니다.

규칙
- 이 폴더의 파일을 `data/labels/` · `data/text/` · 학습 JSONL로 옮기지 않습니다.
- 새 라벨이 확정되면(`label-rules-frozen` · `split-frozen` 뒤) 새 라벨이나 더미로 바꿉니다.
- 같은 문서를 새로 라벨링할 때는 이 폴더의 옛 라벨을 열어 두지 않습니다.
- 더미는 필요한 유형(영업비밀 · EC 칸 · H코드 없음 등)이 옛 라벨에 없을 때만 추가합니다. 현재 7건에 모두 있습니다.

| doc_id | 담긴 유형 |
|---|---|
| KR-NOROO-004 | 영업비밀 성분 |
| KR-NOROO-005 | H코드 없는 문구(구서식) |
| KR-KUMHO-002 | KE 번호, 해당없음 |
| KR-GSC-001 | EC 번호 칸, 영업비밀 |
| KR-OCI-005 | 고압가스, `CAS No.` 표기, H문구 다수 |
| KR-HENKEL-001 · KR-HANIL-001 | val 경로 시험(렌더러만) |

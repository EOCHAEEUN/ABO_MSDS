# D3 결정 (2026-09-30, r1 결과를 보기 전)
- r1 양자화 보정: data/train.jsonl에서 seed 42로 64개, chat template(thinking 끔) 입력+정답, 1,024토큰에서 자름
- 이유: 8GB GPU와 시간 제약(G5 1.7B 128x512: GPU 피크 12.71GB, 65분). 총 보정 토큰을 G5 수준(약 6.5만)으로 맞춤. 품질 선택이 아니라 자원 문제
- 멈춤 규칙(속도 기준): 처음 2층의 층당 시간 x 36 > 7시간이면 중단 후 32개 x 1,024로 재실행
- 병합: nf4dq, 임시 스크립트 runs/deploy_r1/merge_nf4dq_tmp.py
- 판정은 이 결과로 한다. pileval은 계획서대로 미달 시 대안 1회
- [수정, 결과 보기 전] 64x1,024는 8GB GPU에서 OOM(eager 어텐션 8GiB, sdpa에서도 MLP 단계 OOM) → 32개 x 512토큰, attn=sdpa로 변경. WSL memory 24→16GB

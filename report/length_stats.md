# 입력+출력 토큰 분포  [강덕우]

`python pipeline/length_stats.py` · 토크나이저 Qwen/Qwen3-4B · train·val 28건(test·test2·val_en 제외) · 프롬프트는 시스템 프롬프트와 chat template 포함

| 항목 | P50 | P90 | P95 | MAX | 최장 문서 |
|---|---:|---:|---:|---:|---|
| 프롬프트(zero-shot · QLoRA) | 1841 | 2772 | 2790 | 2949 | KR-OCI-005 |
| 정답 JSON | 473 | 738 | 832 | 976 | KR-NOROO-005 |
| 프롬프트 + 정답 (학습 1건) | 2311 | 3245 | 3687 | 3766 | KR-NOROO-005 |
| few-shot 프롬프트(base_fs) | 4202 | 5133 | 5151 | 5310 | KR-OCI-005 |

## 권장값

- `max_new_tokens` = 정답 MAX 976 × 1.3 = **1269** (plan.md 5장 규칙). `eval/infer.py` 기본값과 비교해 작으면 올린다.
- 학습 `max_length` ≥ 프롬프트 + 정답 MAX 3766 (10% 여유 → 4352). 현재 설정 4096 → 충분. 증강 뒤 길이는 `train_qlora.py`가 초과 샘플을 따로 알린다.

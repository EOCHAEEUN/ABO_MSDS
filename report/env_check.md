# 환경 점검  [양세윤]

점검일 2026-09-28 · 브랜치 `feat/eval-env` · 버전 고정은 `requirements.txt`

## 장비 · OS

| 항목 | 값 |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB |
| 드라이버 | Windows 610.78 (WSL nvidia-smi 610.55), CUDA UMD 13.3 |
| OS | Ubuntu 24.04.4 LTS on WSL2 (커널 6.18.33.2-microsoft-standard-WSL2) |
| RAM · 디스크 | 15 GiB · 여유 845 GB |
| Python | 3.12.3, 저장소 루트의 `.venv` |

## 패키지 (requirements.txt와 같음)

torch 2.14.0+cu130 (CUDA 13.0, `torch.cuda.is_available()` True) · transformers 5.17.0 · peft 0.21.0 ·
bitsandbytes 0.50.2 · accelerate 1.15.0 · tokenizers 0.23.2 · pdfplumber 0.11.10 · pydantic 2.13.5 · fastapi 0.141.1 · uvicorn 0.53.0

## 모델

- `Qwen/Qwen3-4B`, HF 스냅샷 `1cfa9a7208912126459214e8b04321603b3df60c` (7.6 GB, `~/.cache/huggingface/hub`)
- 실험 고정(단계 7) 때 이 리비전을 함께 적는다.

## 4bit 추론 점검 (eval/infer.py의 load_model · generate 그대로)

설정: NF4 · double quant · compute bf16 · `enable_thinking=False` · greedy. 입력은 **test/fixtures(옛 라벨, 코드 점검 전용)** 이며
아래 수치는 환경 확인용이다. 성능 근거로 쓰지 않는다.

| 항목 | 값 |
|---|---|
| 모델 로딩 | 약 10초(캐시 후) |
| 로딩 후 GPU 메모리 | 2.49 GiB |
| 생성 중 최대 GPU 메모리 | 2.91 GiB (입력 1,870 토큰 · 출력 590 토큰) |
| 생성 속도 | 약 19.5 토큰/초 (590 토큰 30초) |
| infer → score 한 바퀴 | 동작 확인 (fixture val 2건, `--out-root` 임시 폴더) |

## 확인한 것 · 남은 것

- **max_new_tokens:** fixture 1건이 임시 기본값 1024에서 잘렸다(JSON 미완성 → 파싱 실패). 새 라벨로 train · val 정답 최장 토큰을 잰 뒤
  × 1.3으로 정해 실험 고정 전에 바꾼다(plan 6절). 그 전까지 val 실행 결과는 `n_hit_max_new_tokens`를 함께 본다.
- 학습(QLoRA, max_length 4096, gradient checkpointing) VRAM은 1차 학습 스모크 때 따로 적는다.
- `HF_TOKEN`이 없어도 내려받기는 되지만 속도 제한 경고가 나온다. 필요하면 `.env`에 둔다(커밋 금지).

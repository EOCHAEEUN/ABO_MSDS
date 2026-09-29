# G5 스모크 결과 (2026-09-30) — 통과

모델: Qwen/Qwen3-1.7B 원본 (형식 확인용, 수치는 판정에 쓰지 않음)
기기: RTX 5070 Laptop + Ryzen AI NPU (같은 기기)

## 양자화 (WSL, .venv-quark)
- 환경: torch 2.9.1+cu128, transformers 4.57.6, amd-quark 0.11, lm_eval 0.4.8
  - torch 2.14는 torch.ao.quantization.pt2e 부재로 Quark import 실패 → 2.9.1로 낮춤
  - lm_eval 0.4.13은 load_yaml_config 부재 → 0.4.8
  - CUDA_HOME 경고(C++ 커널)는 무시해도 진행됨
- 설정: uint4_wo_128, AWQ(pipeline/configs/awq_qwen3.json, 3쌍, v→o 제외), pileval 128×512, 제외 층 없음(`--exclude_layers` 인자 없이)
- Linear 197/197 양자화(lm_head 포함), embed_tokens bf16
- AWQ 28층 65분(층당 87~140초), GPU 메모리 피크 12.71GB (8GB 초과분은 시스템 RAM 사용)
- 출력 model.safetensors 1.52GB

## 후처리 (Windows, ryzen-ai-1.8.0)
- model_generate --hybrid 성공. 쓰기 가능한 폴더(C:\models)에서 실행해야 함(Program Files에서 exit code 1)
- generation_config.json이 결과 폴더로 복사되지 않음 → 수동 복사
- context_length 40960, eos [151645, 151643]
- U14: lm_head 별도 양자화 저장 + config tie=true. AMD 정답지도 tie=true. OGA가 MatMulNBits 197개로 수용

## 생성 (OGA 0.14.0)
- genai_config 기본값이 샘플링(do_sample=True, temp 0.6) → do_sample=False 명시 필요
- (a) 문자열 입력: 243토큰 7.4초
- (b) 토큰 ID 입력(U9): thinking 없이 한국어 답, EOS에서 정지, 35토큰 1.2초

# 배포 경량화 계획 — r1 병합 + AMD Quark AWQ int4

> **상태: v2, PM 조건부 승인 (2026-09-29).** 배포 경량화는 plan 1절 범위 밖이라(제외 목록에 "Ollama · GGUF 변환") G1~G3 통과를 조건으로 승인했다(`report/decisions.md` "배포 경량화" 절). 3.3절 설정 · 5절 판정 기준 승인 여부는 9절.
> **이번 범위:** r1 어댑터 병합 → Quark AWQ int4 양자화 → val 품질 확인까지. 모두 **RTX 5070 기기**(r1 학습 · val 기록 기기)에서 한다. Windows 후처리 · OGA 추론 · 서빙은 **NPU 노트북**에서 할 일이며 윤곽만 적는다(4.2절).
> 함께 볼 파일: `docs/plan.md` 5 · 6 · 9절, `report/decisions.md`(r1 · r2 · r3 val 결과, 단계 7 모델 고정)
> **[확인]** 표시는 아직 확인하지 않은 항목이다. 전체 목록은 10절에 있다.

## v2 변경 요약 (v1 검토 반영)

| # | v1 | v2 | 이유 |
|---|---|---|---|
| 1 | D0~D4를 RTX 4060 노트북에서 | D0~D4는 RTX 5070 기기에서. 기기별 역할을 3.0절에 명시 | 병합 · 양자화를 5070에서 하므로 |
| 2 | D0 = 4060 ↔ 5070 기기 잡음 측정 | D0 = 5070에서 r1 재현 확인 | 같은 기기라 기기 차이 측정은 필요 없다. 재현되지 않으면 기준선을 D0 출력으로 바꾼다(5절) |
| 3 | 없음 | D4r(선택) 추가: `.venv-quark`에서 양자화 전 병합본 생성 | D4는 환경(`.venv` → `.venv-quark`)과 양자화가 함께 바뀐다. 양자화 단독 효과를 분리 |
| 4 | AWQ 매핑에 v → o 포함 | v → o 제외(GQA)를 결과 보기 전에 고정 | Qwen3-4B는 v_proj 출력 1,024 ≠ o_proj 입력 4,096 |
| 5 | G2 통과 조건: 입력 ≥ 3,100, 입력 + 출력 ≥ 4,200 | 한도 L 확인 후 문서 단위 규칙 | 한도가 4,096이면 최장 문서(4,064)는 들어가는데 v1 조건으로는 불통과라 표가 모순 |
| 6 | WSL 메모리 · 디스크를 4060 노트북 수치로 적음 | 5070 기기에서 다시 확인 | 작업 기기가 다름 |
| 7 | G1 전부 미확인 | NPU 노트북의 NPU · 드라이버 확인, 나머지 [확인] | 작업 관리자 확인 |
| 8 | 코드 PR부터 | G1~G3(문서 확인) → G5 → 코드 PR 순서 | 막히면 코드 작업 없이 종료 |

**v2 점검 반영 (main `948f5cf` 기준):**

| # | 고친 곳 | 내용 |
|---|---|---|
| a | 2절 · 3.2절 · 9절 | 모델 고정이 기록됐다(PR #40, `eval/experiment.json`). "기록 없음" 서술과 체크 항목을 완료로 바꿈 |
| b | 4.1절 D0 · 6절 | D0 채점을 기본 설정으로 돌리면 `report/scores.csv`의 공식 `qlora_r1 / val` 행을 덮어쓴다(`upsert_scores`는 같은 condition · split 행을 지우고 새로 씀). D0 채점은 `--scores-csv`로 따로 쓴다 |
| c | 4.1절 D2 · D4r · D4 | bf16 병합본(약 8GB)은 RTX 5070 Laptop(8GB)에 올라가지 않는다. "GPU에서, 안 되면 CPU"가 아니라 처음부터 CPU로 적음 |
| d | 2절 | 4060 checkout에서 `268e4e4^` 텍스트를 복원해 val `inputs_digest` = `6536e4c4…`를 확인함 |
| e | 3.0절 · 10절 U11 | 4060 노트북은 Intel i7-13620H라 NPU 노트북과 다른 기기다 |
| f | 3.1절 G5 | G5는 형식 확인용이다. 예제 스크립트 기본 보정 데이터(pileval)를 써도 되고, 형식 관련 설정만 3.3절과 같게 둔다 |
| g | 10절 U14 | Qwen3-4B는 `tie_word_embeddings: true`(lm_head = 임베딩 공유). 후처리가 이를 처리하는지 확인 항목 추가 |
| h | 3.3절 보정 데이터 | 최대 길이 2,048 → **3,200**(자르지 않음). train 예시 입력 + 정답은 P50 2,144 · 최장 3,149토큰이라 2,048이면 절반 넘는 예시에서 정답 JSON 뒷부분이 빠진다(PM 결정) |
| i | 5절 잡음 바닥 | k = 출력이 달라진 문서 수 → **문서 완전 정답 판정이 바뀐 문서 수**. 판정 조건(맞다가 틀린 문서 수)과 같은 단위로 맞춤. 출력이 달라진 문서 수는 따로 기록(PM 결정) |
| j | 4.1절 D4r · 5 · 8 · 9절 | D4r 선택 → **필수**. D4는 기준선 대비 병합 · venv · 기기(GPU → CPU) · 양자화가 함께 바뀌어 D4r 없이는 원인을 가를 수 없다(PM 결정) |
| k | 3.1절 G1~G4 | **G1~G4 통과.** Ryzen AI 1.8.0 문서(사용자가 붙여 준 본문 · 직접 조회, 2026-09-29). 근거는 3.1절 각 행 |
| l | 3.3절 제외 층 · 형식 이름 · data_type · Quark 버전 | Ryzen AI 양자화 안내대로 고침(U5가 정한 "결과 보기 전 3.3절 수정"): 제외 층 lm_head → **없음**(`--exclude_layers []`), 형식 이름 `uint4_wo_128`(= UINT4 · group 128 · 비대칭), `--data_type bfloat16`, Quark **0.11** + transformers 4.57.6 |
| m | 3.3절 AWQ 매핑 | Quark 0.11은 `qwen3` 템플릿이 AWQ 설정 이름 `qwen3`을 가리키지만 `AWQ_MAP`에 `qwen3` 항목이 없어 **AWQ 설정이 None**이 된다. 3쌍을 `--quant_algo_config_file`(JSON)로 반드시 넘기고, 적용 여부를 `quant.json`에 기록 · 확인 |
| n | 3.1절 G5 | 스모크 모델 Qwen3-0.6B → **Qwen3-1.7B**. 1.8.0 hybrid 목록의 Qwen3는 1.7B · 4B · 8B뿐이다 |
| o | 3.3절 대안 | pileval 대안을 AMD 안내 명령 그대로(`pileval_for_awq_benchmark`, `--seq_len 512`)로 맞춤. 보정 데이터 외 설정은 본 설정과 같다 |

## 0. 무엇을 하려는가

**질문:** qlora_final로 고정한 r1(Qwen3-4B + LoRA, NF4 위에서 학습)을 int4 AWQ로 경량화해도 val 추출 품질이 유지되는가.

- **배포 트랙이다.** Base · Few-shot · QLoRA 비교(plan 5 · 10절)의 결론에 영향을 주지 않는다.
- 주장 범위는 "같은 모델을 경량화했을 때 val 품질이 얼마나 유지되는가"뿐이다. 경량화로 정확도가 오른다는 주장은 하지 않는다.
- 결과가 어느 쪽이든 보고한다(5절 판정).

## 1. 원칙

- **비교표에 섞지 않는다.** 본 비교군(base_zs · base_fs · qlora_*)은 같은 런타임(Transformers, 4bit NF4)으로 조건을 맞췄다(`eval/infer.py` 머리말). 경량화 결과는 런타임이 다르므로 `report/scores.csv` · `report/final_table.md`에 넣지 않고, `report/deploy/`에 "배포 경량화 결과"로 따로 적는다.
- **test를 쓰지 않는다.** 경량화 모델은 val로만 돌린다. test 비교군은 base_zs · base_fs · qlora_final 3개, 각 1회뿐이다. 경량화 스크립트는 `--split test`를 거부한다.
- **보정(calibration) 데이터는 train만 쓴다.** AWQ 보정은 모델을 바꾸는 데이터 사용이라 학습과 같이 본다. val · test 텍스트는 넣지 않는다.
- **프롬프트 · 전처리는 `core/`를 그대로 쓴다.** `core/`는 고치지 않는다. 입력은 HF 토크나이저 `apply_chat_template(..., enable_thinking=False)`로 만든 토큰 ID를 쓰고, 입력 토큰 수 · 해시를 기준과 대조한다.
- **한 번에 하나만 바꾼다.** 재현 확인(D0) → 병합(D1 · D2) → 환경 변경(D4r) → 양자화(D4) → (다음 단계) 런타임 변경(W2) 순서로, 품질 변화의 원인을 단계별로 나눈다.
- **결과를 보기 전에 정한다.** 양자화 설정(3.3절), 기준선 규칙과 판정 기준(5절)은 이 문서로 고정한다. 바꾸려면 결과를 보기 전에 이 문서를 고치는 PR을 먼저 올린다.

## 2. 받은 메모에서 고칠 점

| 받은 메모 | 확인한 사실 | 계획에 반영 |
|---|---|---|
| bf16 원본 가중치에 어댑터를 올려 병합 | 어댑터는 NF4로 반올림된 베이스 위에서 학습됐다. bf16 원본에 병합하면 어댑터가 학습 때 본 가중치와 달라진다. 4bit 위에서 바로 병합하면 안 된다는 점은 맞다 | 기본은 `nf4dq`: NF4 베이스를 bf16으로 풀어(dequantize) 그 위에 병합. bf16 원본 병합은 비교용으로 함께 잰다(3.3절) |
| 이 노트북 RAM 31GB | 4060 노트북 WSL2에서 보이는 메모리는 15GB였다(`free -g`). 31GB는 Windows 전체다. 작업은 5070 기기에서 하므로 그 기기 수치를 따로 봐야 한다 | 5070 기기의 WSL 메모리를 확인하고, 부족하면 `.wslconfig`로 올린다(3.2절) |
| Val 8건으로 짝 비교 | 재시작 val은 10건 · 8개 그룹이다 | 10건 전체로 짝 비교 |
| 입력 1,024토큰 제한이라 컨텍스트 걱정 없음 | 반대다. r1 val 입력은 1,319~3,043토큰, 입력 + 출력은 최대 4,064토큰(KR-NEOGEN-002)이다 | Ryzen AI 쪽 컨텍스트 한도를 맨 먼저 확인(3.1절 G2) |
| Qwen3 계열은 지원됨 | PyPI 최신 amd-quark 0.13에는 `qwen3`의 AWQ 스케일링 매핑이 기본으로 없다(`qwen2` · `qwen3_5`는 있음). 템플릿(lm_head 제외 등)은 있다 | Quark 버전은 Ryzen AI 문서 지정 버전으로 고정하고, 매핑은 3.3절 3쌍을 명시한다 |

그 밖에 확인한 것:

- **모델 고정이 기록됐다(PR #40, `948f5cf`).** `report/decisions.md` "단계 7: qlora_final = r1"과 `eval/experiment.json`(`adapter_sha256` `a9a32341…`, `prompt_version` v1, `max_new_tokens` 2048). 경량화 트랙은 이 `adapter_sha256`과 같은 어댑터만 쓰고, 생성 길이도 2048을 쓴다.
- **r1 어댑터는 5070 기기에 있다.** 이 4060 checkout의 `runs/0928_r1/`에는 `config.json` · `loss.csv`만 있지만, 작업을 5070에서 하므로 옮길 필요는 없다. 5070 기기에서 `sha256_dir`로 `a9a32341…`과 대조만 한다.
- **r1 val 추론 뒤에 val 입력 텍스트가 바뀌었다.** `268e4e4`에서 KR-3DSYS-001 · KR-NEOGEN-001 · KR-SOTL-001 텍스트가 수정됐다. r1 val 출력은 수정 전 입력(`inputs_sha256` `6536e4c4…`)으로 만들었다. 짝 비교는 같은 입력으로 해야 하므로 `268e4e4^`의 텍스트를 복원해 쓴다.
  - 4060 checkout에서 확인함: `268e4e4^`의 `data/text/`(`_cut_log.csv` 포함)로 계산한 val `inputs_digest` = `6536e4c4…`, 현재 HEAD는 `4566ab6a…`.
  - r1 val 추론(09-29 05:57) 뒤 `eval/infer.py`의 생성 코드(`load_model` · `generate`)는 바뀌지 않았다. 바뀐 것은 프롬프트 버전 인자뿐이고, v1 문구는 `LEGACY_V1_FILE_SHA256`으로 같음을 확인한다.
- **파일럿 `feat/npu-inference`**(Intel OpenVINO, `9bceb0a`)에 병합 스크립트(`pipeline/merge_adapter.py`, `nf4dq` · `bf16`)가 있다. 파일럿 수치는 근거로 쓰지 않고, 코드만 파일 단위 PR로 가져와 재시작판 규약에 맞춘다(6절).

## 3. 준비

### 3.0 기기 구성

| 기기 | 확인된 것 | 하는 일 | 환경 |
|---|---|---|---|
| RTX 5070 기기 | r1 학습 · val 기록 기기, 어댑터 보관. GPU 메모리 7.96GiB(`runs/0928_r1/config.json`) | D0 · D1 · D2 · D3 · D4r · D4, G5 양자화 | WSL2 [확인], `.venv`(기존), `.venv-quark`(신규) |
| NPU 노트북 | 프로세서 AMD Ryzen AI 9 365 w/ Radeon 880M. 작업 관리자: NPU 0(NPU Compute Accelerator Device, 드라이버 32.0.203.329 · 2025-12-04), GPU 0 AMD Radeon 880M, 메모리 31GB | G5 후처리 · 추론, W1~W4 | Windows 네이티브, Ryzen AI conda |
| RTX 4060 노트북 | Intel i7-13620H, WSL 메모리 15GB. 이 계획을 쓴 checkout | 코드 작성 · 리뷰만 | — |

NPU 노트북과 4060 노트북은 다른 기기다(CPU가 다름). NPU 노트북에서 WSL을 쓰고 있다면 W 단계 전에 `wsl --shutdown`으로 메모리를 Windows에 돌려준다.

### 3.1 go/no-go — 먼저 확인할 것

| # | 항목 | 통과 조건 | 못 넘으면 |
|---|---|---|---|
| G1 | NPU 노트북 칩 · 드라이버 · SW | **통과.** 칩 AMD Ryzen AI 9 365 w/ Radeon 880M(Windows 시스템 정보) = Ryzen AI 300 시리즈 → LLM Overview "Supported Processor Configurations"에서 Ryzen AI 300 (STX/KRK) NPU-only ✓ · Hybrid ✓. SW는 **Ryzen AI 1.8.0**(OGA 0.14.0, conda `ryzen-ai-1.8.0`). 요구 NPU 드라이버 **32.0.203.280 이상** → 현재 32.0.203.329 충족(설치 안내의 최신 배포 드라이버는 32.0.203.376). Windows 11 build ≥ 22621.3527 요구 [확인] | 드라이버는 G5 전에 정하고 W 단계가 끝날 때까지 바꾸지 않는다. 바꾸면 G5부터 다시 |
| G2 | hybrid 컨텍스트 한도 L | **통과.** OGA Flow: 입력 + 출력은 모델 `genai_config.json`의 `context_length`를 넘을 수 없다. hybrid는 `genai_config.json`에 `"hybrid_opt_chunk_context": "1"`(decoder의 RyzenAI provider options) · `"chunk_size": 2048`(`search`)을 넣으면 16K까지. NPU Full Fusion은 4,096, Token Fusion은 16K. val 최장 입력 + 출력 4,064라 L = 4,096이어도 넘는 문서 0건 | 실제 L은 W1에서 생성된 `genai_config.json`의 `context_length`로 기록. **L < 4,200이면 16K 설정(위 두 키)을 켜고 켠 상태로 W2 전체를 돈다**(결과 보기 전 고정) |
| G3 | Qwen3-4B(dense) hybrid 지원 | **통과.** Hugging Face `amd/ryzen-ai-180-hybrid` 모음에 `amd/Qwen3-4B_rai_1.8.0_hybrid`(모델 카드: "AWQ / Group 128 / Asymmetric / BFP16 activations / UINT4 Weights", Quark 양자화 + 후처리). Qwen3는 1.7B · 4B · 8B. Preparing OGA Models: 지원 모델의 파인튜닝 버전만 이 흐름을 쓸 수 있다 → r1(Qwen3-4B 파인튜닝) 해당 | — |
| G4 | Quark 버전 · 양자화 명령 · data_type · 후처리 | **확인.** Quark **0.11**(Python 3.12, `transformers==4.57.6`, datasets · accelerate · evaluate · nltk), 예제 `examples/torch/language_modeling/llm_ptq/quantize_quark.py --no_trust_remote_code --quant_scheme uint4_wo_128 --num_calib_data 128 --seq_len 512 --quant_algo awq --dataset pileval_for_awq_benchmark --model_export hf_format --data_type bfloat16 --exclude_layers []`(bf16 모델은 bfloat16). AWQ 기본 매핑이 없는 구조는 `--quant_algo_config_file awq <json>`. 후처리: `conda activate ryzen-ai-1.8.0` → `model_generate --hybrid --input <양자화본> --output <폴더>`(메모리 16GB 기기용 `--mem_optimize`는 31GB라 쓰지 않음) | 3.3절에 반영 |
| G5 | 소형 모델 스모크: **Qwen3-1.7B**(1.8.0 hybrid 목록의 가장 작은 Qwen3)를 양자화(5070, Quark 0.11 예제 스크립트) → NPU 노트북에서 `model_generate --hybrid` → OGA로 한 문장 생성. 형식 확인용이므로 형식 관련 설정(형식 · 제외 층 · export · data_type · AWQ 매핑 JSON)만 3.3절과 같게 두고, 보정 데이터는 예제 기본값(pileval)을 쓴다. 로그에서 AWQ가 실제로 적용됐는지(설정 None이 아닌지) 확인 | 끝까지 동작 | 4B 작업 전에 형식 문제 해결 |

G2 문서 단위 규칙(W2에 적용, 결과 보기 전 고정):

- 입력 토큰이 최대 입력 길이를 넘으면 그 문서는 실패로 센다.
- 넘지 않으면 생성 한도를 `min(2048, L − 입력 토큰)`으로 두고(2048 = `eval/experiment.json`의 `max_new_tokens`), EOS 없이 한도에 도달하면 실패로 센다.
- 어느 경우에도 입력을 자르지 않는다.

D4는 5070의 transformers에서 돌아 이 한도가 없다. G2는 W 단계가 가능한지를 먼저 보려는 문턱이다. G1~G3은 문서 확인만으로 끝나므로, 하나라도 막히면 코드 작업 없이 트랙을 종료하고 `decisions.md`에 한 줄 남긴다.

### 3.2 준비물

| 항목 | 할 일 |
|---|---|
| PM 결정 | 조건부 승인(G1~G3 통과 시 착수)(9절). qlora_final = r1은 기록 완료(`948f5cf`) |
| r1 어댑터 | 5070 기기 `runs/0928_r1/adapter/`에서 `python3 -c "from eval.infer import sha256_dir; print(sha256_dir('runs/0928_r1/adapter'))"` = `eval/experiment.json`의 `adapter_sha256`(`a9a32341…`) |
| 패키지 대조 | 5070 기기 `.venv`의 torch · transformers · peft · bitsandbytes · accelerate 버전이 `runs/0928_r1/config.json`의 `env`와 같은지 확인. 다르면 D0 재현 실패 원인이 될 수 있으므로 기록 |
| val 입력 복원 | 5070 기기에서 `git archive 268e4e4^ data/text`를 `runs/deploy/text_r1/`(git 제외)에 풀고 `inputs_digest` = `6536e4c4…` 확인(4060 checkout에서는 확인됨) |
| 5070 기기 메모리 | WSL에서 `free -g` [확인]. 목표 24GB(bf16 병합본 약 8GB + AWQ 보정 활성값 + CPU 생성). 부족하면 `.wslconfig` memory · swap을 올리고 `wsl --shutdown` 후 재확인 |
| Quark venv | 기존 `.venv`(torch 2.14 · transformers 5.17 · bitsandbytes 0.50.2)는 건드리지 않는다. 5070 기기에 `.venv-quark`(Python 3.12)를 따로 만들고 G4대로 AMD Quark 0.11 배포 압축본의 wheel · `transformers==4.57.6` · datasets · accelerate · evaluate · nltk와 CUDA torch를 `requirements-quark.txt`에 고정. 예제 스크립트는 배포 압축본의 `examples/`에 있다(PyPI wheel에는 없음) |
| 5070 기기 디스크 | bf16 병합본 2벌(`nf4dq` · `bf16`) 약 16GB + 양자화본 약 3GB = 약 19GB 여유 [확인] |
| NPU 노트북 | Ryzen AI 1.8.0 설치(NPU 드라이버 · GPU 드라이버 · MSI 설치 프로그램, conda `ryzen-ai-1.8.0`). Windows 빌드 확인. W 단계 전에 WSL 종료 |

### 3.3 병합 · 양자화 설정 (고정)

**병합** (`pipeline/merge_adapter.py`, `.venv`, 5070 기기)

| 방식 | 내용 | 용도 |
|---|---|---|
| `nf4dq` (기본) | bf16 베이스를 CPU에 올리고, 학습 · 추론과 같은 NF4 설정(double quant, compute bf16)으로 GPU에 올린 모델의 양자화 Linear를 하나씩 bf16으로 풀어 덮어쓴 뒤 `merge_and_unload()` | 양자화 입력. r1(NF4 + LoRA)과 가중치가 같다 |
| `bf16` | bf16 원본 베이스에 바로 `merge_and_unload()` | 비교용 |

- GPU에는 NF4 베이스(약 2.5GB)만 올린다. bf16 한 벌(약 8GB)은 CPU 메모리에서 다룬다.
- 기록: `runs/deploy_r1/merge_{방식}.json` — 베이스 리비전 `1cfa9a72…`, 어댑터 해시, 방식, 풀어 덮어쓴 Linear 수, 패키지 버전, git 커밋.

**양자화** (`pipeline/quantize_quark.py`, `.venv-quark`, 5070 기기)

| 항목 | 값 | 근거 |
|---|---|---|
| 입력 | `nf4dq` 병합본 (D2 결과로 bf16이 명백히 가까워도 바꾸지 않고 기록만 한다) | 3.3절 병합 |
| 알고리즘 · 형식 | AWQ, `uint4_wo_128`(UINT4 가중치 · group 128 · 비대칭, 활성값 bf16) | Ryzen AI 1.8.0 양자화 안내(G4), `amd/Qwen3-4B_rai_1.8.0_hybrid` 모델 카드와 같음 |
| 제외 층 | **없음**(`--exclude_layers []`, lm_head도 양자화) | Ryzen AI 양자화 안내 명령 그대로. 이 인자를 빼면 Quark 템플릿 기본값이 lm_head를 뺀다고 안내에 적혀 있다. v1의 "lm_head 제외"(Quark 템플릿 기본값)에서 G4 결과로 결과 보기 전에 바꿈. lm_head는 임베딩과 공유 가중치라 U14 확인 |
| AWQ 스케일링 매핑 | input_layernorm → q/k/v, post_attention_layernorm → gate/up, up → down (3쌍). **v → o는 제외.** `--quant_algo_config_file awq pipeline/configs/awq_qwen3.json`으로 항상 넘긴다 | Quark 0.11은 `qwen3` 템플릿의 AWQ 설정 이름이 `AWQ_MAP`에 없어 AWQ 설정이 None이 된다(wheel 코드 확인). Qwen3-4B는 GQA(어텐션 헤드 32, KV 헤드 8, head_dim 128)라 v_proj 출력 1,024와 o_proj 입력 4,096이 맞지 않는다. q_norm · k_norm은 q · k 출력 뒤라 입력 채널 스케일링과 겹치지 않는다. 적용된 매핑을 `quant.json`에 기록하고, AWQ가 적용되지 않았으면 중단 |
| 보정 데이터 | `data/train.jsonl`(train 35건, 282예시)에서 seed 42로 128개, chat template(v1, thinking 끔)으로 만든 입력 + 정답, 최대 3,200토큰(자르지 않음) | 1절 원칙. 공개 사례의 pileval(영문 일반 텍스트)보다 입력 분포가 가깝다. train 예시 입력 + 정답은 P50 2,144 · 최장 3,149토큰(`runs/0928_r1/config.json`)이라 3,200이면 정답 JSON까지 모두 들어간다. 3,200을 넘는 예시가 있으면 자르지 않고 빼고, 뺀 목록을 `quant.json`에 기록 |
| 메모리 부족 시 | 64개로 줄임 (품질 선택이 아니라 자원 문제로 기록) | |
| 출력 | `--model_export hf_format` → `runs/deploy_r1/quark_awq_w4g128/` + `quant.json`(원본 해시 · 설정 · 적용 매핑 · 보정 표본 목록 해시 · 패키지 · 소요 시간 · 최대 메모리) | |
| data_type | `bfloat16` | G4: bf16 모델은 bfloat16. Qwen3-4B · 병합본 모두 bf16 |

**미달일 때의 대안 1개 (지금 고정):** 보정 데이터만 AMD 안내 명령 그대로(`--dataset pileval_for_awq_benchmark --num_calib_data 128 --seq_len 512`) 바꾼 `quark_awq_w4g128_pile`. 5절 판정이 "미달"일 때만 1회 돌린다. 둘 다 미달이면 한계로 보고한다. 재학습은 하지 않는다.

### 3.4 Ryzen AI 1.8.0 "Preparing OGA Models" 요약과 이 계획에서 쓰는 방식

출처: Ryzen AI 1.8.0 문서 "Preparing OGA Models"(사용자가 붙여 준 본문, 2026-09-29). 준비는 **양자화**(Linux + GPU)와 **후처리**(Ryzen AI를 설치한 Windows PC) 두 단계다.

**적용 범위**

- 이미 지원하는 모델의 파인튜닝 버전만 이 흐름을 쓸 수 있다. 구조가 다른 모델, 새 연산 모양이 필요한 구조 변경은 안 된다.
- r1은 Qwen3-4B에 LoRA(q · k · v · o_proj)를 합친 것이라 구조가 바뀌지 않는다. `amd/Qwen3-4B_rai_1.8.0_hybrid`가 있으므로 대상이다(G3).

**양자화 — 안내 내용 → 이 계획**

| 안내 | 이 계획 |
|---|---|
| Linux 기기 + AMD 또는 Nvidia GPU. GPU 기기에서 30~60분 | 5070 기기 WSL2 + CUDA. 4B bf16(약 8GB)이 8GB GPU에 다 올라가지 않아 더 걸릴 수 있다(U7) |
| conda 환경(Python 3.12). AMD GPU면 ROCm용 torch | `.venv-quark`(Python 3.12, CUDA torch). conda 대신 venv를 쓰고 패키지는 `requirements-quark.txt`로 고정 |
| AMD Quark 0.11 배포 압축본을 받아 그 안의 wheel 설치 | 같음. 예제 `examples/torch/language_modeling/llm_ptq/quantize_quark.py`는 압축본에만 있다 |
| `pip install datasets transformers==4.57.6 accelerate evaluate nltk` | 같음 |
| `--quant_scheme uint4_wo_128`(group 32 · 64 · 128 가능) | `uint4_wo_128` |
| `--num_calib_data 128 --seq_len 512 --dataset pileval_for_awq_benchmark` | 본 설정은 train 보정 데이터(128개, 최대 3,200토큰, 3.3절). pileval 명령 그대로는 G5와 미달 시 대안에만 씀 |
| `--quant_algo awq`. 기본 AWQ 설정이 없는 구조는 `--quant_algo_config_file awq <custom awq config json>` | Quark 0.11의 `qwen3` AWQ 설정이 비어 있어 3쌍 매핑 JSON을 항상 넘긴다(3.3절) |
| `--model_export hf_format` | 같음 |
| `--data_type bfloat16`(bf16 모델), fp32 · fp16 모델은 float16 | `bfloat16` |
| `--exclude_layers []`. 이 인자를 빼면 모델별 기본값이 출력층 등을 뺄 수 있음 | `[]`(lm_head도 양자화) |
| `--layer_quant_scheme lm_head uint4_wo_32`로 층마다 group 크기를 다르게 할 수 있음(Phi-4 권장: GPTQ + 이 옵션) | 쓰지 않음. 설정은 1개로 고정 |
| 일부 모델은 양자화 폴더로 복사되지 않는 파일이 있음(Phi-4 · ChatGLM 예) | Qwen3는 목록에 없음. 병합본의 토크나이저 · `chat_template` · `generation_config.json`이 양자화 폴더에 있는지 확인하고, 없으면 복사해 기록 |

G5 명령(Qwen3-1.7B, 형식 확인용):

```bash
cd <quark-0.11>/examples/torch/language_modeling/llm_ptq/
python quantize_quark.py \
     --no_trust_remote_code \
     --model_dir Qwen/Qwen3-1.7B \
     --output_dir <runs/deploy_smoke/quark_qwen3_1.7b> \
     --quant_scheme uint4_wo_128 \
     --num_calib_data 128 \
     --seq_len 512 \
     --quant_algo awq \
     --quant_algo_config_file awq <저장소>/pipeline/configs/awq_qwen3.json \
     --dataset pileval_for_awq_benchmark \
     --model_export hf_format \
     --data_type bfloat16 \
     --exclude_layers []
```

D3(r1)은 같은 형식 인자로 `pipeline/quantize_quark.py`가 돌린다. 입력은 `nf4dq` 병합본이고, 보정 데이터만 train으로 바꾼다.

**후처리 — 안내 내용 → 이 계획**

| 안내 | 이 계획 |
|---|---|
| 양자화본을 Ryzen AI를 설치한 Windows PC로 복사 → `conda activate ryzen-ai-<version>` | NPU 노트북, `ryzen-ai-1.8.0`. 복사한 파일 해시를 `quant.json`과 대조 |
| Hybrid(NPU prefill + GPU token): `model_generate --hybrid --input <양자화본> --output <폴더>` | **이것만 쓴다** |
| NPU Full Fusion(최고 성능, 최대 4,096) · Token Fusion(`--extra_options max_seq_len=16384`, 16K) · Basic · Eager | 쓰지 않음. 실행 방식은 hybrid 하나로 고정 |
| `--mem_optimize`(16GB 노트북용) | 쓰지 않음(NPU 노트북 31GB). 후처리가 메모리 부족으로 실패하면 붙이고 기록 |
| `model_generate --oga_only`(OGA 변환만), 또는 `onnxruntime-genai==0.14.0` Model Builder를 따로 돌린 OGA 모델을 `--input`으로 넘겨 후처리만 | 쓰지 않음. `model_generate --hybrid`가 내부에서 Model Builder 0.14.0으로 변환한다. 변환 단계에서 막히면 이 경로로 원인을 나눠 본다 |

## 4. 단계

### 4.1 이번 범위 (RTX 5070 기기, WSL2)

| 단계 | 할 일 | 환경 | 통과 기준 · 산출물 |
|---|---|---|---|
| D0 재현 확인 | r1(NF4 + LoRA)을 복원 입력으로 val 10건 다시 생성 → 채점 → 기록된 r1 출력과 짝 비교 | `.venv`, GPU. 생성: `eval/infer.py --condition qlora_r1 --split val --adapter runs/0928_r1/adapter --text-dir runs/deploy/text_r1 --out-root runs/deploy/out`. 채점: `eval/score.py --condition qlora_r1 --split val --text-dir runs/deploy/text_r1 --out-root runs/deploy/out --scores-csv report/deploy/scores_d0.csv` | 입력 토큰 수가 기록과 모두 같아야 함(다르면 중단). 출력 문자열 10건이 모두 같으면 기준선 = r1 기록, k = 0. 하나라도 다르면 5절 규칙대로 기준선 = D0 출력. **`--scores-csv` 없이 채점하면 `report/scores.csv`의 공식 `qlora_r1 / val` 행이 덮어써진다** |
| D1 병합 | `nf4dq` · `bf16` 병합 | `.venv` | `merge_*.json`, 어댑터 해시 일치 |
| D2 병합 동등성 | teacher forcing: val 10건의 (입력 + 기준선 출력)을 넣고 위치별 top-1 일치율 · 최대 logit 차이를 잰다. 기준 = NF4 + LoRA(GPU), 비교 = 병합본(bf16, **CPU** — 약 8GB라 8GB GPU에 올라가지 않음) | `.venv`, `eval/check_merge.py` | 두 방식의 수치를 `report/deploy/merge_check.md`에 기록. 기기(GPU ↔ CPU) 차이가 섞인 값이므로 절대값보다 `nf4dq` · `bf16` 두 방식의 상대 비교로 읽는다. 생성을 하지 않아 빠르다 |
| D3 양자화 | 3.3절 설정으로 AWQ int4 | `.venv-quark` | `quant.json`, 소요 시간 · 최대 메모리 |
| D4r 환경 기준선 (필수) | `nf4dq` 병합본(bf16, 양자화 전)으로 val 10건 생성 → 채점 | `.venv-quark`, CPU, `eval/infer_deploy.py --condition deploy_r1_merged_ref` | D4와 짝 비교해 양자화 단독 효과를 본다. D4와 같은 기기 · dtype으로 돌린다. 기준선과도 짝 비교해 환경 변경(venv · GPU → CPU · 병합) 효과를 본다 |
| D4 양자화 품질 | 양자화본을 transformers + Quark로 불러 val 10건 생성 → 채점 → 짝 비교 | `.venv-quark`, CPU(가짜 양자화는 bf16으로 풀려 약 8GB라 GPU 불가 [확인]), `eval/infer_deploy.py` → `eval/score.py --scores-csv report/deploy/scores_deploy.csv` → `eval/deploy_compare.py` | 5절 판정. `report/deploy/deploy_r1_awq_w4g128_val.md` |

- D4는 가짜 양자화(fake quant)라 속도는 의미가 없다. 품질만 본다. NPU 런타임 효과는 다음 단계(W2)에서 따로 잰다.
- D4r · D4는 CPU 생성이라 한 번에 수십 분~1시간 이상 걸릴 수 있다(val 출력 합계 약 5,700토큰 + 입력 약 20,000토큰) [확인].
- 조건 이름: `deploy_r1_awq_w4g128`(D4), `deploy_r1_merged_ref`(D4r). 출력은 `outputs/deploy/{조건}/val/`, 점수는 `report/deploy/scores_deploy.csv`.
- D0 · D1(NF4 적재) · D2(기준 쪽)가 5070 GPU를 쓴다. plan 9절 단계 8(test 평가)과 같은 GPU라 일정이 겹치지 않게 잡는다.

### 4.2 다음 단계 (NPU 노트북, Windows — 이번에 하지 않음, 윤곽만)

| 단계 | 할 일 | 챙길 것 |
|---|---|---|
| W1 후처리 | 양자화본을 5070 기기에서 NPU 노트북으로 옮겨 `conda activate ryzen-ai-1.8.0` → `model_generate --hybrid --input <양자화본> --output <폴더>` | WSL2에서는 NPU가 잡히지 않는다. 옮긴 파일 해시를 `quant.json`과 대조. 생성된 `genai_config.json`의 `context_length`를 L로 기록하고 G2 규칙 적용. 작업 전 `wsl --shutdown` |
| W2 OGA 추론 | `og.Model` · `og.Tokenizer`로 val 10건 → 채점 → D4 · 기준선과 짝 비교 | thinking 끄기: OGA의 chat template을 쓰지 않고, HF 토크나이저로 만든 입력 토큰 ID(`enable_thinking=False`의 빈 `<think></think>` 포함)를 그대로 넣는다. 입력 토큰 수 · 해시를 D0과 대조. 출력에 `<think>`가 섞이면 고치지 않고 파싱 실패로 센다. greedy, 종료 토큰은 모델 `generation_config.json`의 eos. 생성 한도는 3.1절 G2 문서 단위 규칙 |
| W3 효율 | 문서당 생성 시간 · 첫 토큰 시간 · 메모리 | 기기가 달라 GPU 수치와 속도 우열을 주장하지 않는다. "GPU 없는 PC에서 동작"을 보고 |
| W4 서빙 | FastAPI에 OGA 로더를 쓰는 추론 방식을 따로 둠 (transformers + peft 경로는 그대로) | plan 8절 화면 범위와 PM 결정 필요. 앱은 WSL, 추론만 Windows 워커로 둘지 결정 |

## 5. 판정 — 결과를 보기 전에 정한다

**기준선** (D0 결과로 정한다):

- D0 출력이 r1 기록(`outputs/qlora_r1/val/`, 입력 `6536e4c4…`)과 10건 모두 같으면 기준선 = r1 기록. 수치는 파싱 1.00 · 스키마 0.80 · 제품명 0.90 · 신호어 0.90 · GHS F1 0.976 · H코드 F1 1.000 · CAS · pair F1 0.970 · nocas F1 0.750 · 문서 완전 정답 0.60 · 무근거 생성 0(`report/decisions.md` r3 절 표).
- 하나라도 다르면 기준선 = D0 출력(같은 기기 · 같은 입력 · 현재 코드). r1 기록은 참고로 나란히 적는다.

**잡음 바닥** k: D0과 r1 기록 사이에 문서 완전 정답 판정이 바뀐 문서 수(맞다 → 틀림, 틀림 → 맞다 모두). 출력이 모두 같으면 0이다. 출력 문자열이 달라진 문서 수는 따로 적되 판정에는 쓰지 않는다.

**비교 대상**: D4(이번 판정), D4r(원인 분리용, 판정에 쓰지 않음), W2(다음 단계). 각각 기준선과 짝 비교한다.

| 판정 | 조건 |
|---|---|
| 미달 | 파싱률 또는 스키마 준수율이 기준선보다 낮음 · 무근거 생성 문서 1건 이상 · 악화 불허 필드(제품명 · CAS F1 · pair F1) 하락 · max_new_tokens 도달 문서가 새로 생김 |
| 부분 유지 | 미달이 아니고, 나머지 핵심 필드(신호어 · GHS · H코드 · nocas) 중 하나라도 문서 1건 몫(1/10)을 넘게 하락, 또는 문서 완전 정답이 맞다가 틀린 문서가 k건보다 많음 |
| 유지 | 위 둘에 해당하지 않음 |
| 판정 불가 | 입력 토큰 수 불일치 · 문서 구성이 다름 · 채점 행 없음 |

- D4가 미달 · 부분 유지이면, 떨어진 문서 · 필드가 D4r에서도 같이 떨어졌는지 적는다. 같이 떨어졌으면 원인을 환경 변경으로, D4에서만 떨어졌으면 양자화로 적는다. 판정 자체는 바꾸지 않는다.
- val 10건 · 8개 그룹이라 방향 확인 수준이다. "유지"는 "val에서 품질 하락을 확인하지 못했다"는 뜻이지 동등하다는 뜻이 아니다. 문서별 승 · 패 · 무와 달라진 필드를 함께 적는다.
- 판정 결과와 상관없이 D0 · D2 · D4r · D4 수치를 모두 적는다.

## 6. 파일 구성

`core/` · `eval/infer.py`는 고치지 않는다. 새 파일 위주로 하고, 기존 파일 수정은 아래 두 곳뿐이다.

| 파일 | 내용 | 비고 |
|---|---|---|
| `pipeline/merge_adapter.py` | 병합(`nf4dq` · `bf16`) | 파일럿 `9bceb0a`에서 파일 단위로 가져옴. 파일럿 `eval.experiment` 의존을 빼고 `eval.infer.sha256_dir` · `verify_commit`을 씀. 리뷰: 데 |
| `pipeline/quantize_quark.py` | Quark API로 AWQ 양자화 + `quant.json`. 3.3절 매핑 3쌍을 명시하고 적용 매핑을 기록. 보정 표본은 `split=train` 문서의 JSONL만 받음(각 줄의 `doc_id`를 `data/splits.csv`와 대조해 train이 아니면 거부) | 새 파일 |
| `eval/check_merge.py` | D2 teacher forcing 일치율 | 새 파일 |
| `eval/infer_deploy.py` | 병합본 · 양자화본 추론(D4r · D4). 입력 · 출력 형식은 `eval/infer.py` 함수를 import해 같게 씀. `_run.jsonl`은 `score.py`의 프롬프트 버전 검사를 통과하도록 `infer.py`와 같은 키로 남김. 조건 이름은 `deploy_`로 시작해야 하고, `--split test`는 거부 | 새 파일 |
| `eval/deploy_compare.py` | 5절 기준선 선택(D0 결과) · 짝 비교 · 판정 → `report/deploy/*.md`. 정답은 읽지 않고 채점 상세(`_score_detail.jsonl`)만 읽음 | 새 파일 |
| `eval/score.py` | `--scores-csv` 옵션 추가(기본값 · 동작 불변). D0(`qlora_r1` 이름을 그대로 씀)이 공식 행을 덮어쓰지 않게, 경량화 점수가 `report/scores.csv`에 섞이지 않게. `--no-write`는 `_score_detail.jsonl`도 쓰지 않아 짝 비교에 쓸 수 없다 | 기존 파일 수정, 평 리뷰 필수. 회귀 테스트(`test/test_score.py`) 통과 |
| `test/test_deploy.py` | test split 거부, 조건 이름 규칙, 보정 표본에 val 문서 섞임 거부, 입력 해시 대조, 적용 매핑이 3.3절 3쌍과 같은지 | 새 파일 |
| `pipeline/configs/awq_qwen3.json` | 3.3절 AWQ 스케일링 매핑 3쌍(v → o 제외). `quantize_quark.py --quant_algo_config_file awq`로 넘김 | 새 파일, **PR 1(계획서와 함께)에 포함** — G5 전에 필요. 형식은 Quark 0.11 `AWQConfig`(name · scaling_layers · model_decoder_layers) 기준, G5에서 적용 확인(U4) |
| `requirements-quark.txt` | `.venv-quark` 패키지 고정 | 새 파일 |
| `.gitignore` | `runs/**/merged*/`, `runs/**/quark_*/`, `runs/deploy/text_r1/`, `runs/deploy/out/`, `runs/_ov_cache/` 추가 | 기존 파일 수정. 가중치는 이미 `*.safetensors`로 제외되지만 폴더째 뺀다 |

커밋하는 것: 이 문서, 위 코드, `merge_*.json` · `quant.json`, `report/deploy/`. 커밋하지 않는 것: 병합본 · 양자화본 가중치, 복원한 입력 텍스트, D0 출력.

## 7. 순서와 담당 (제안)

본 과제 필수 작업(test 평가, 강사 지시 GPT 심판 평가) 뒤에 진행한다. 일정이 겹치면 이 트랙이 밀린다.

| 순서 | 할 일 | 담당 제안 | 막히면 |
|---|---|---|---|
| 1 | PM 조건부 승인 · 기록(9절) | 프(PM) | — |
| 2 | G1~G3 문서 확인 (약 30분) | 프 · NPU 노트북 소유자 | 트랙 종료, `decisions.md`에 한 줄 |
| 3 | 5070 기기: 어댑터 해시 · 패키지 · 입력 복원 · 메모리 · 디스크 확인 | 데 | 해시 · 입력 해시 불일치면 중단 |
| 4 | G5 스모크(Qwen3-1.7B): 양자화는 5070, 후처리 · OGA는 NPU 노트북 | 데 · NPU 노트북 소유자 | 형식 문제 해결 전 4B 작업 금지 |
| 5 | 코드 PR(6절) → 리뷰. `score.py --scores-csv`가 병합돼야 D0 채점을 할 수 있다 | 평(score.py) · 데(merge) | — |
| 6 | D0 → D1 → D2 → D3 → D4r → D4 | 평 · 데 | — |
| 7 | 판정 기록(`report/deploy/`, `decisions.md` 한 줄) | 프 | — |

## 8. 위험과 대응

| 위험 | 대응 |
|---|---|
| Ryzen AI hybrid 한도가 val 문서보다 짧음 | G2에서 먼저 확인. 자르지 않고 문서 단위 규칙으로 실패를 셈 |
| NPU 드라이버가 Ryzen AI SW 요구 버전보다 낮음 | G1에서 확인, 드라이버를 올린 뒤 G5로 재확인 |
| Quark 버전이 Qwen3 AWQ 매핑을 모름 | 3.3절 3쌍을 `algorithm_configs`로 명시. 적용 매핑을 `quant.json`에 기록 |
| Quark가 transformers 5.17과 안 맞음 | `.venv-quark`를 따로 둠. Quark가 요구하는 버전으로 고정 |
| 환경 변경(`.venv` → `.venv-quark`, GPU → CPU)만으로 결과가 달라짐 | D4r(필수)로 분리 |
| AWQ 보정 중 메모리 부족 | 5070 기기 WSL 메모리를 `.wslconfig`로 올림. 그래도 부족하면 보정 표본 64개 |
| NF4로 학습한 어댑터 + uint4 group 양자화로 품질 하락 | D2(병합)와 D4(양자화)를 나눠 원인 특정. 대안은 보정 데이터 교체 1회뿐 |
| 같은 기기에서도 r1이 재현되지 않음 | D0 결과로 기준선을 D0 출력으로 바꾸고 k를 판정에 넣음(5절). 패키지 버전 차이부터 확인 |
| val 입력이 r1 때와 다름 | `268e4e4^` 텍스트 복원 + 입력 해시 대조. 다르면 중단 |
| D0 채점이 공식 r1 점수를 덮어씀 | `score.py --scores-csv`로 따로 씀. 이 옵션 병합 전에는 D0 채점을 하지 않는다 |
| 경량화 결과가 본 비교표에 섞임 | 조건 이름 `deploy_`, 점수 파일 분리, test 거부 |
| Windows 후처리가 양자화 형식을 거부 | G5 스모크로 먼저 확인 |

## 9. PM이 정할 것

- [x] 배포 경량화를 조건부로 범위에 넣을지 — 조건부 승인(2026-09-29, `report/decisions.md` "배포 경량화" 절)
- [x] qlora_final = r1 확정 기록 — 완료(`948f5cf`, PR #40: `decisions.md` 단계 7 · `eval/experiment.json`)
- [ ] 3.3절 양자화 설정(v → o 제외 포함) · 5절 기준선 규칙 · 판정 기준 승인
- [x] D4r 실시 여부 — 필수로 결정(2026-09-29)
- [x] 보정 데이터 최대 3,200토큰 · 잡음 바닥 k 정의 — 결정(2026-09-29, v2 점검 반영 h · i)
- [ ] `eval/score.py`에 `--scores-csv` 옵션 추가 동의(평)
- [ ] NPU 노트북 담당자와 W 단계 진행 여부(이번 범위 밖)

`decisions.md` 기록 예시(승인 시):

> ### 2026-09-XX · 배포 경량화 트랙 조건부 추가 (PM 결정)
> - r1(qlora_final, `adapter_sha256` `a9a32341…`)을 `nf4dq`로 병합한 뒤 AMD Quark AWQ int4(`w_uint4_per_group_asym`, group 128, v → o 스케일링 제외)로 양자화해 val 10건에서 품질 유지 여부를 본다. 작업은 RTX 5070 기기, 기준선은 D0 재현 결과로 정한다. G1~G3(Ryzen AI 지원 · 컨텍스트 한도 · Qwen3-4B 지원) 중 하나라도 막히면 코드 작업 없이 종료한다. 계획: `docs/deploy_quant_plan.md`
> - 본 비교표 · test 평가에 넣지 않는다. 결과는 `report/deploy/`에 "배포 경량화 결과"로 따로 적는다. 보정 데이터는 train만 쓴다.

## 10. 확인하지 않은 것

| # | 항목 | 확인 방법 | 틀렸을 때 |
|---|---|---|---|
| U1 | ~~NPU 노트북 칩 · SW 버전 · hybrid 지원~~ — **확인됨**(G1): Ryzen AI 9 365, Ryzen AI 1.8.0, hybrid 지원 | — | — |
| U2 | ~~hybrid 컨텍스트 한도~~ — **확인됨**(G2): `genai_config.json`의 `context_length`, 설정으로 16K. 실제 값은 W1에서 기록 | — | — |
| U3 | ~~Qwen3-4B hybrid 지원~~ — **확인됨**(G3): `amd/Qwen3-4B_rai_1.8.0_hybrid` | — | — |
| U4 | Quark 0.11에서 3쌍 AWQ 설정 JSON이 오류 없이 적용되는지(0.11 기본 `qwen3` AWQ 설정은 None으로 확인됨), 배포 압축본 예제 스크립트가 PyPI 0.11 코드와 같은지 | G5 스모크 로그, `quant.json` | JSON 형식을 Quark AWQ 예제 문서에 맞춰 고침 |
| U5 | ~~후처리가 요구하는 data_type · 제외 층~~ — **확인됨**(G4): `bfloat16`, `--exclude_layers []`. 3.3절 반영 | — | — |
| U6 | bitsandbytes 0.50.2의 `dequantize_4bit` 결과가 학습 · 추론 때 NF4 계산과 같은가 | D2 top-1 일치율 | `nf4dq` 대신 `bf16` 사용 여부 PM 판단 |
| U7 | Quark AWQ를 5070 기기 CPU에서 돌릴 수 있는가, 걸리는 시간 | D3 실행 | GPU 층 단위 실행 옵션 확인 |
| U8 | transformers에서 Quark hf_format을 불러 생성할 수 있는가(D4), CPU에서 걸리는 시간 | 소형 모델로 먼저 시험 | D4를 건너뛰고 W2만으로 판정(병합 · 양자화 · 런타임 효과가 섞임을 보고에 밝힘) |
| U9 | OGA에 토큰 ID를 직접 넣을 수 있는가 | G5 스모크 | 문자열 입력 + OGA 템플릿 끔, 입력 토큰 수로 대조 |
| U10 | NPU greedy 재현성 | W2를 두 번 실행 | 판정을 여러 번 실행 기준으로 바꿔 재승인 |
| U11 | ~~NPU 노트북과 4060 노트북이 같은 기기인가~~ — **확인됨: 다른 기기**(4060 노트북은 Intel i7-13620H) | — | — |
| U12 | 5070 기기의 WSL 메모리 · 디스크 여유 | `free -g`, `df -h` | `.wslconfig` 조정, 보정 표본 64개 |
| U13 | ~~요구 NPU 드라이버 버전~~ — **확인됨**(G1): 32.0.203.280 이상, 현재 32.0.203.329 충족 | — | — |
| U14 | Qwen3-4B는 `tie_word_embeddings: true`(lm_head와 임베딩 공유). 병합 저장 · Quark export · Ryzen AI 후처리가 공유 가중치를 그대로 처리하는가 | G5 스모크(Qwen3-1.7B도 공유 구조), 병합본 `config.json` | 후처리 안내에 따라 lm_head를 풀어 저장하고 기록 |

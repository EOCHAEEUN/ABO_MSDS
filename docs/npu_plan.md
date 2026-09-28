# NPU 추론 계획 — Intel Core Ultra 9 (OpenVINO)

> **참고용 브랜치 — 병합 대상 아님.** 이 브랜치(`feat/npu-inference`)는 파일럿 `feat/web`(9920c8f) 위에서 만들었다. main · feat/web로 PR을 만들지 않는다.
> 2026-09-28 재시작(`docs/restart`의 plan.md · CLAUDE.md) 기준으로 보면: NPU는 plan 1절 범위 밖이라 PM 결정이 먼저 필요하고, 아래의 파일럿 수치 · C안 · test2 서술은 근거로 쓰지 않는다.
> 재시작 main에서 쓰려면 main에서 새 브랜치를 만들고 필요한 파일만 파일 단위 PR로 옮긴다. `eval/infer_npu.py` · `eval/npu_compare.py`는 파일럿 `eval/gate.py` · `eval/experiment.py` · 출력 형식에 의존하므로 재시작판 `infer.py` · `score.py` 규약에 맞춰 고친 뒤 옮긴다.
>
> 상태: **초안 v2 (2026-09-28)**. 파일·코드 구성은 확정했고(6절), 결정권자 승인은 아직이다. 승인되면 `report/decisions.md`에 한 줄 남긴다.
> 브랜치: `feat/npu-inference` (`feat/web` 9920c8f에서 분기)
> 함께 볼 파일: `docs/plan.md`(기획서 요약) · `docs/plan_c.md`(C안) · `eval/experiment.json`(test2 실험 정의)
> **[확인]** 표시는 NPU 장비에서 아직 확인하지 않은 항목이다. 전체 목록은 11절에 있다.

## 0. 무엇을 하려는가

**질문:** GPU(RTX 4060, bitsandbytes NF4)에서 학습·평가한 QLoRA 모델을 Intel Core Ultra 9 노트북의 NPU에서 돌렸을 때 추출 품질이 유지되는가. 유지된다면 지연 시간·메모리·전력은 어떤가.

- 이것은 **배포 트랙**이다. QLoRA가 Base보다 나은지는 C안 test2가 답하고, 이 계획은 그 결론에 영향을 주지 않는다.
- 주장 범위는 두 가지다. "같은 모델을 NPU에서 돌려도 val 기준 품질이 얼마나 유지되는가"와 "NPU 효율 수치". NPU로 정확도가 오른다는 주장은 하지 않는다.
- 결과가 어느 쪽이든 보고한다(7절 판정).

## 1. 원칙

1. **학습은 GPU에서, NPU는 추론·서빙만 한다.** QLoRA 학습은 bitsandbytes NF4(CUDA 전용)에 묶여 있다.
2. **C안 게이트를 건드리지 않는다.**
   - `eval/experiment.json`의 `generation_files` · `scoring_files`는 고치지 않는다. 이 브랜치는 새 파일만 추가하고 `.gitignore`에 3줄을 더했다.
   - NPU 조건은 test2 비교군 4개에 넣지 않는다. NPU 평가는 **val · val_var**로만 한다. `eval/infer_npu.py`가 다른 split을 거부한다.
   - test · test2를 NPU로 돌리려면 test2 최종 평가가 끝난 뒤 결정 기록을 남긴다. 결과는 "사후 배포 확인"으로 따로 보고하고 합산하지 않는다.
3. **GPU 결과와 같다고 가정하지 않는다.** 어댑터는 NF4 베이스 위에서 학습됐다. 합치고 다시 양자화하면 출력이 바뀔 수 있으므로 동등성을 측정한다.
4. **변경은 한 번에 하나.** 병합 → OV 변환(CPU) → NPU 양자화 순서로, 원인을 단계별로 분리한다.
5. **프롬프트는 한 토큰도 바꾸지 않는다.** HF 토크나이저로 만든 입력 ID를 그대로 넣는다(5절 "디코딩").

## 2. 대상 장비 — 먼저 세대를 확정한다

"Core Ultra 9"는 세대마다 NPU가 다르다.

| 세대 (예시 모델) | NPU | NPU 성능(제조사 표기) | 이 계획에서의 차이 |
|---|---|---|---|
| Meteor Lake (185H) | NPU 3720 | 약 11 TOPS | INT4 채널 단위(`int4cw`)만 후보 **[확인]** |
| Arrow Lake H (285H) | NPU 3720 계열 | 약 13 TOPS | 위와 같음 **[확인]** |
| Lunar Lake (288V) | NPU 4 | 약 48 TOPS | 그룹 양자화(`int4g128`)도 후보 **[확인]** |

기록할 것: CPU 모델명, 시스템 메모리, NPU 드라이버 버전, Windows 빌드, 패키지 버전(`requirements-npu.txt`). 기록 위치는 `report/npu/env.md`.

## 3. 실행 환경 — 두 venv, 두 OS

| 작업 | 스크립트 | 환경 | 이유 |
|---|---|---|---|
| 어댑터 병합 | `pipeline/merge_adapter.py` | WSL2 + RTX 4060, 기존 `.venv` | `nf4dq` 방식은 bitsandbytes(CUDA)가 필요 |
| OV 변환·양자화 | `pipeline/export_openvino.py` | NPU 노트북(권장) 또는 WSL2, `requirements-npu.txt` venv | optimum-intel 2.2.0이 transformers 5.5.x를 요구해 GPU venv(5.17)와 섞을 수 없음 |
| OV CPU 기준선 추론 | `eval/infer_npu.py --device CPU` | 어느 쪽이든 NPU venv | |
| NPU 추론 | `eval/infer_npu.py --device NPU` | **Windows 네이티브** NPU venv | WSL2 안에서는 NPU 장치가 보이지 않는 것으로 알려져 있음 **[확인]** |
| 채점 · 비교 | `eval/score.py` · `eval/npu_compare.py` | 기존 `.venv` | 출력 파일만 읽음 |
| 서빙 | `app/npu_worker.py`(Windows) ↔ `app/backends/ov_http.py`(WSL 앱) | 각자 | 앱은 WSL에 두고 추론만 Windows |

- Windows 쪽 저장소는 따로 clone한다(`\\wsl$\` 경로에서 직접 돌리지 않음). 출력의 `_load.jsonl`에 git 커밋이 남는다.
- 추론 입력인 `data/text/*.txt`, `data/splits.csv`, `data/labels/`는 git에 있다. 단 KR-GSC-003 · 004 텍스트는 아직 없다(11절 C2).

## 4. 단계와 실행 순서

| 단계 | 할 일 | 명령 (요약) | 통과 기준 |
|---|---|---|---|
| 0. 장비 확인 | 2절 기록, NPU에서 작은 모델 생성 확인 | — | NPU `LLMPipeline`이 동작 |
| 0'. GPU 기준 갱신 | 이 checkout의 `outputs/qlora_r1/val`은 **6건**이다. 09-28 val 8건 출력을 받아 두거나, 없으면 다시 생성·채점(기존 6건 출력을 덮어쓰므로 담당자 확인 후) | `eval/infer.py --condition qlora_r1 --split val --adapter runs/0926_r1/adapter --max-new-tokens 1269 --overwrite` → `eval/score.py` | 8건 출력, 보고서 수치(4/8 등)와 일치 |
| 1. 병합 | r1을 `nf4dq`로 병합 | `pipeline/merge_adapter.py --adapter runs/0926_r1/adapter --out runs/npu_r1` | `merge.json`의 어댑터 해시가 r1과 같음 |
| 2. OV CPU 기준선 | INT8 변환 → CPU 추론 → 채점 → 비교 | `export_openvino.py --src runs/npu_r1 --preset int8` → `infer_npu.py --device CPU --condition qlora_r1_ov_cpu_int8` | 병합 + 변환만의 영향 측정. 7절 판정 기록 |
| 3. NPU | INT4 변환 → NPU 추론(val, val_var) → 채점 → 비교 | `--preset int4cw` → `infer_npu.py --device NPU --condition qlora_r1_npu_int4cw` | 7절 판정 |
| 4. Base | Qwen3-4B를 같은 preset으로 변환해 NPU에서 base_zs | `export_openvino.py --base Qwen/Qwen3-4B --out runs/npu_base --preset int4cw` → `--condition base_zs_npu_int4cw` | 화면의 Base ↔ QLoRA 전환용. 기준은 GPU `base_zs` |
| 5. 효율 | 출력 기록의 `gen_time_sec` · `ttft_sec` · `throughput_tok_s`, `_load.jsonl`의 로딩·컴파일 시간, 메모리·전력 | `npu_compare.py --write` | GPU r1과 같은 문서로 비교 |
| 6. 서빙 | Windows 워커 + WSL 앱(`MSDS_BACKEND=ov_http`) | `uvicorn app.npu_worker:app` | 시연 시나리오 1회 무중단 |

각 단계가 끝나면 `python eval/npu_compare.py --ref <GPU 조건> --cand <NPU 조건> --split val --write` → `report/npu/{cand}_{split}.md`.

**동등성 지표 (`eval/npu_compare.py`)**
- 출력 글자 단위 일치율, 입력 토큰 수 불일치 건수(1건이라도 있으면 프롬프트가 다르다는 뜻이므로 중단)
- 문서 완전 정답(확장) 뒤집힘 목록과 문서별로 달라진 필드
- `report/scores.csv` 지표 나란히: 형식 · 핵심 필드 · nocas · 무근거 생성 · 다른 칸 오입력 · 시간 · TTFT · 처리량
- 재현성: 같은 조건을 `--overwrite`로 한 번 더 돌려 글자 단위로 같은지

## 5. 변환·양자화·디코딩 (확정)

### 병합 — `nf4dq` 기본
- **`nf4dq`:** 원본 bf16 베이스를 CPU에 올린다. 학습 때와 같은 NF4 설정으로 GPU에 올린 모델에서 양자화된 Linear를 하나씩 bf16으로 풀어 덮어쓴 뒤 어댑터를 합친다. 어댑터가 학습 때 본 베이스 가중치를 그대로 쓰는 방식이다.
- **`bf16`:** 원본 bf16 베이스에 바로 합친다. 비교용이다.
- **사전 점검 (2026-09-28, WSL2, Qwen3-1.7B + 무작위 LoRA r16, 문서 1건 2,133토큰의 위치별 top-1 일치율, 기준 = NF4 + LoRA):**

  | 병합 방식 | top-1 일치 | 최대 logit 차이 |
  |---|---:|---:|
  | `nf4dq` | 98.1% | 5.0 |
  | `bf16` | 83.9% | 17.6 |

  4B + 실제 r1에서도 같은 경향인지는 1단계에서 확인한다(11절 B1).
- bf16 4B 한 벌(약 8GB)은 RTX 4060 8GB에 올라가지 않는다. 그래서 병합 모델을 GPU에서 돌리는 기준선은 두지 않고, OV CPU INT8(2단계)을 병합·변환 기준선으로 쓴다.
- 런타임 LoRA 전환은 쓰지 않는다. Base와 QLoRA를 별도 IR 두 개로 둔다.

### 양자화 preset (`pipeline/export_openvino.py`, 결과를 보기 전에 목록 고정)

| preset | optimum-cli 인자 | 용도 |
|---|---|---|
| `int8` | `--weight-format int8 --sym` | OV CPU 기준선, 품질 상한 |
| `int4cw` | `--weight-format int4 --sym --ratio 1.0 --group-size -1` | NPU 기본 후보 |
| `int4g128` | `--weight-format int4 --sym --ratio 1.0 --group-size 128` | NPU 4 세대에서만 후보 |

- 데이터 기반 보정(AWQ·scale estimation)은 쓰지 않는다. 나중에 쓰게 되면 보정 데이터는 train 텍스트만 쓴다.
- preset을 추가하려면 결과를 보기 전에 이 표와 코드를 같은 PR로 고친다.

### 길이 (`eval/infer_npu.py` 기본값)

| 설정 | 값 | 근거 (`report/length_stats.md`, train·val 28건) |
|---|---|---|
| `--max-prompt-len` (NPU `MAX_PROMPT_LEN`) | 4096 | zero-shot·QLoRA 프롬프트 P95 2,790 · MAX 2,949 |
| `--min-response-len` (NPU `MIN_RESPONSE_LEN`) | 1280 | `max_new_tokens`보다 커야 함 |
| `--max-new-tokens` | 1269 | 정답 MAX 976 × 1.3, GPU val 8건 재평가와 같음 |

- 입력이 4096을 넘으면 자르지 않는다. `skipped="PROMPT_TOO_LONG"`으로 남기고, 채점에서는 실패로 센다.
- base_fs(프롬프트 MAX 5,310)는 NPU에 올리지 않는 것이 기본이다. 조건 이름 `base_fs_npu_*`는 막지 않았으므로 올릴 때는 `--max-prompt-len`을 따로 정하고 결정 기록을 남긴다.

### 디코딩 (`app/backends/ov_genai.py`)
- **입력:** HF 토크나이저(모델 폴더의 파일)로 `apply_chat_template(add_generation_prompt=True, enable_thinking=False)` → 토큰화 → `TokenizedInputs`로 전달한다. OV 쪽 chat template·토크나이저는 거치지 않는다.
- **출력:** 생성 토큰 ID를 같은 HF 토크나이저로 `decode(skip_special_tokens=True)`. `eval/infer.py`와 같다.
- **생성 설정:** greedy(`do_sample=False`), `stop_token_ids`는 모델 `generation_config.json`의 eos.
- **사전 점검 (WSL2, OV CPU INT8, Qwen3-1.7B 병합 모델, val 2건 × 64토큰):**
  - 입력 토큰 수가 GPU r1 출력 기록과 같았다(1,698 / 1,767).
  - 출력이 GPU(bf16, `eval/infer.py generate`)와 글자 단위로 같았다.
  - NPU 장치에서는 아직 확인하지 않았다(11절 A3).

## 6. 파일 구성 (확정)

기존 파일은 `.gitignore` 말고는 고치지 않는다. 추론·채점 스크립트는 아래 표대로 쓴다.

| 용도 | 쓰는 스크립트 | 새로 만든 것인가 |
|---|---|---|
| GPU 추론 (기준) | `eval/infer.py` | 기존 그대로 |
| NPU · OV CPU 추론 | `eval/infer_npu.py` | 새 파일 |
| 채점 | `eval/score.py` (`--condition <NPU 조건 폴더>`) | 기존 그대로. 조건 이름 제한이 없어 NPU 출력도 같은 규칙으로 채점 |
| 동등성 비교 · 판정 | `eval/npu_compare.py` | 새 파일 |
| 형식 변형 안정성 | `eval/variant_stability.py` | 기존 그대로(필요할 때) |

| 파일 | 내용 |
|---|---|
| `pipeline/merge_adapter.py` | 어댑터 병합(`nf4dq` · `bf16`) → `runs/<run>/merged/` + `merge.json`(베이스 리비전 · 어댑터 해시 · 방식 · 패키지 · 커밋) |
| `pipeline/export_openvino.py` | preset 3종으로 optimum-cli 호출 → `runs/<run>/ov_<preset>/` + `export_<preset>.json`(원본 · 인자 · IR 해시 · 패키지) |
| `app/backends/ov_genai.py` | OpenVINO GenAI 추론기(`OVGenAIRunner`). 평가·서빙 공용. 입력 토큰 대조, NPU 길이 초과 거부, TTFT · 처리량 기록 |
| `eval/infer_npu.py` | 입력 준비·출력 형식은 `eval/infer.py` 함수를 import해 그대로 사용. 재개 대조는 `eval/gate.check_resume` |
| `eval/npu_compare.py` | 4절 동등성 지표 + 7절 판정. 정답 파일은 읽지 않고 채점 결과만 읽음 |
| `app/backends/__init__.py` · `torch_nf4.py` · `ov_http.py` | 서빙 추론 방식 선택(`MSDS_BACKEND=torch_nf4`(기본) / `ov_http`). `app/model.py`(담당: 양세윤)가 `get_backend("base"/"qlora")`로 부르면 됨. `app/model.py`는 고치지 않았음 |
| `app/npu_worker.py` | Windows NPU 워커(`/health`, `/generate`). base · qlora 두 IR을 시작 시 올리고 한 번에 한 건씩 생성 |
| `test/test_infer_npu.py` | OpenVINO 없이 도는 테스트 9건: GPU 조건 이름 거부, 이름 형식, 모델 종류 일치, 봉인 split 거부, 변환 기록 요구, 판정 규칙 |
| `requirements-npu.txt` | NPU venv 패키지(2026-09-28 설치 확인 버전) |
| `.gitignore` | `runs/**/merged/`, `runs/**/ov_*/`, `runs/_ov_cache/` 추가 |

**조건 이름 규칙:** `base_zs_…` · `base_fs_…` · `qlora_<run>_…`로 시작하고 `_ov_` 또는 `_npu_`를 포함한다(예: `qlora_r1_ov_cpu_int8`, `qlora_r1_npu_int4cw`, `base_zs_npu_int4cw`). GPU 조건 이름(`qlora_r1` 등)은 거부한다.

**출력 형식:** `outputs/{조건}/{split}/{doc_id}.json`. 키는 `eval/infer.py`와 같고 `device` · `ov_model` · `quant` · `ttft_sec` · `throughput_tok_s` · `input_ids_sha256`가 더 있다. 폴더에는 `_run.jsonl`(실행 설정 — IR 해시 · preset · 병합 방식 · 길이 · 프롬프트 해시)과 `_load.jsonl`(로딩·컴파일 시간 · 커밋)이 남는다.

**점검 결과 (2026-09-28):**
- 기존 테스트 8개 파일과 `test_infer_npu.py` 9건이 모두 통과했다.
- `generation_files` · `scoring_files` 변경은 0건이다.
- 1.7B 모델로 병합 → INT8 변환 → CPU 추론 → `score.py` → `npu_compare.py` → 워커 `/generate`까지 한 번 돌렸다. 점검용 출력과 scores.csv 행은 지웠다.

## 7. 판정 — 결과를 보기 전에 정한다 (`eval/npu_compare.py verdict()`)

기준은 **같은 checkout에서 다시 만든** GPU r1의 val 8건 결과다(4절 0'). 보고서 수치는 파싱 1.00 · 스키마 0.88 · GHS 1.00 · CAS 1.00 · pair 0.96 · nocas 0.80 · 확장 완전 정답 4/8 · 무근거 0이다.

| 판정 | 조건 |
|---|---|
| **미달** | 파싱률 또는 스키마 준수율이 GPU보다 낮음, 또는 무근거 생성 문서 1건 이상 |
| **부분 유지** | 형식은 유지. 핵심 지표(제품명 · 신호어 · GHS · H코드 · CAS · pair · nocas · 확장 완전 정답) 중 하나라도 GPU보다 1/n(문서 1건 몫)을 넘게 하락 |
| **유지** | 위 둘에 해당하지 않음 |
| 판정 불가 | 두 조건의 문서 구성이 다르거나 scores.csv 행이 없음 |

- val 8건 · 4그룹이고, val_var 30개는 독립 30건이 아니다. **pilot 수준 판정**이다.
- 양자화 후보가 여럿 "유지"면 평균 처리량이 가장 높은 것을 고르고, 고른 뒤에는 바꾸지 않는다.
- 미달이면 `int8`을 NPU에서 시도한다. 그래도 미달이면 서빙은 GPU로 두고 NPU는 한계로 보고한다. 재학습은 범위 밖이다.

## 8. 위험과 대응

| 위험 | 대응 |
|---|---|
| Qwen3-4B가 NPU에서 컴파일되지 않음 | OpenVINO 버전 올림 → 안 되면 iGPU(`--device GPU`)로 대체하고 NPU는 한계로 보고 |
| 4096 프롬프트 컴파일 실패·메모리 부족 | `--max-prompt-len 3072`(현재 최장 2,949). 넘는 문서는 실패로 셈 |
| 양자화로 품질 하락 | 2단계(INT8 CPU)와 3단계를 비교해 원인 특정. NPU INT8 시도 |
| NPU가 GPU보다 느림 | 그대로 보고. 속도 개선은 주장하지 않고 전력·메모리·GPU 없는 장비 동작만 주장 |
| Windows · WSL 코드 불일치 | `_load.jsonl` 커밋, `_run.jsonl` 프롬프트 해시로 대조 |
| test2 게이트 파일 실수 수정 | PR 전에 `git diff --stat origin/feat/web`으로 `generation_files` · `scoring_files` 변경 0 확인 |
| 어댑터 가중치 혼동 | `merge.json`의 `adapter_sha256`을 `eval/experiment.py`가 계산하는 r1 해시와 대조 |

## 9. 순서

| 시점 | NPU 작업 |
|---|---|
| test2 고정 전 (지금) | 0 · 0' · 1단계. 이 브랜치 PR 검토(core/ 수정 없음) |
| test2 고정 후 ~ 평가 전 | 2 · 3단계. GPU를 쓰지 않아 평가 실행과 자원 충돌 없음 |
| test2 평가 후 | 4 · 5 · 6단계. 필요하면 결정 기록 후 test2 사후 배포 확인 |

- `qlora_final`이 r1이 아닌 것으로 정해지면 1단계부터 그 어댑터로 다시 한다.
- 담당 제안: 평가·서빙(양세윤)이 0' · 2~6단계, 데이터·학습(강덕우)이 어댑터 전달과 1단계. 팀 확인이 필요하다.

## 10. 착수 전에 정할 것

- [ ] 대상 노트북의 정확한 CPU 모델명과 메모리 (2절)
- [ ] NPU 작업을 C안과 병행할지, test2 평가 뒤로 미룰지
- [ ] r1 어댑터 가중치 전달 방법과 해시 대조
- [ ] base_fs를 NPU에 올리지 않는 것에 대한 동의
- [ ] 7절 판정 기준 승인
- [ ] 서빙 구조: WSL 앱 + Windows NPU 워커(권장) / 전체 Windows 이전

## 11. 확실하지 않은 것

### A. NPU 장비가 있어야 확인할 수 있는 것

| # | 항목 | 지금 아는 것 | 확인 방법 | 틀렸을 때 |
|---|---|---|---|---|
| A1 | 정확한 NPU 세대 | "Core Ultra 9"만 알려짐 | 장치 관리자 · `ov.Core().get_property("NPU", "FULL_DEVICE_NAME")` | preset 후보가 바뀜(`int4g128` 제외 여부) |
| A2 | Qwen3-4B가 NPU에서 컴파일·실행되는가 | CPU에서 1.7B는 동작 확인. NPU·4B는 미확인 | 0단계 | iGPU로 대체 |
| A3 | `TokenizedInputs` 입력과 `stop_token_ids`가 NPU 파이프라인에서도 CPU와 같이 동작하는가 | CPU에서 GPU와 글자 단위 일치 | 3단계, `npu_compare`의 입력 토큰 대조 | 문자열 입력 + `apply_chat_template=False` 경로로 바꿔야 함 |
| A4 | `MAX_PROMPT_LEN` 4096 · `MIN_RESPONSE_LEN` 1280 설정이 받아들여지고 메모리에 들어가는가 | 속성 이름은 OpenVINO 문서 기준 | 0단계 컴파일 로그, 메모리 | 3072로 내림 |
| A5 | NPU 긴 프롬프트 prefill 시간(약 2천 토큰) | 모름. CPU INT8 1.7B는 TTFT 약 3.7~5초 | `ttft_sec` | 문서당 지연이 GPU(24.7초)보다 길 수 있음 → 효율 주장 축소 |
| A6 | NPU greedy 재현성(같은 입력 → 같은 출력) | 모름 | 같은 조건 두 번 실행 | 재현이 안 되면 판정을 여러 번 실행 평균으로 바꿔야 함(판정 기준 재승인) |
| A7 | `perf_metrics`(TTFT · 처리량)가 NPU에서 채워지는가 | CPU에서는 채워짐 | 출력 기록 | 벽시계 시간만 보고 |
| A8 | base · qlora IR 두 개를 동시에 NPU에 올릴 수 있는가 | 모름(INT4 4B 한 벌 약 2.5GB 예상) | 워커 시작 | 모델 전환 때마다 다시 로드(전환이 느려짐) |
| A9 | WSL2에서 NPU가 정말 안 보이는가 | 일반적으로 그렇다고 알려짐 | WSL에서 `ov.Core().available_devices` | 보이면 Windows 워커 없이 WSL에서 전부 실행 |
| A10 | Windows용 패키지 버전 호환(`requirements-npu.txt`는 Linux에서 설치 확인) | Linux 2026.4.0 | Windows venv 설치 | 버전 고정 갱신 |
| A11 | NPU 드라이버 최소 버전 | 모름 | OpenVINO 릴리스 노트 | 드라이버 업데이트 |
| A12 | WSL 앱 → Windows 워커 네트워크 접근(방화벽 · 미러 네트워킹) | 모름 | `curl http://<호스트>:8765/health` | 전체 Windows 이전 |
| A13 | 전력 측정 방법 | 정하지 않음 | 전원 연결 여부 고정, Windows 전력 도구 후보 조사 | 전력 수치 제외 |

### B. 품질에 관한 것 (측정 전에는 모름)

| # | 항목 | 지금 아는 것 |
|---|---|---|
| B1 | `nf4dq` 병합이 4B + 실제 r1에서도 NF4 + LoRA와 가깝게 나오는가 | 1.7B + 무작위 어댑터에서 top-1 98.1%(bf16 병합 83.9%). 실제 어댑터·4B에서는 미확인 |
| B2 | INT4 채널 단위 양자화가 4B의 추출 품질을 유지하는가 | 모름. NF4로 학습한 모델에 다른 4bit 방식을 씌우는 것이라 하락 가능성이 있음 |
| B3 | 작은 수치 차이로 결과가 뒤집히는 문서가 NPU에서도 나오는가 | r1과 C1이 같은 설정인데 2건(KR-ITW-002, KR-NHCHEM-001)에서 갈림 → 뒤집힐 수 있는 문서가 있다는 신호 |
| B4 | OpenVINO의 `nf4` 가중치 형식(optimum-cli에 있음)을 NPU가 지원하는가 | 모름. 지원하면 학습 때와 같은 양자화라 후보가 될 수 있지만 preset 목록 변경이 필요(결과 보기 전에) |

### C. 이 저장소 쪽 준비 상태

| # | 항목 | 상태 |
|---|---|---|
| C1 | r1 어댑터 가중치(`adapter_model.safetensors`) | 저장소에 없음(gitignore). 학습 담당에게 받아야 함 |
| C2 | KR-GSC-003 · 004 전처리 텍스트 | `data/text/`에 없음. PDF로 `pipeline/extract_text.py`를 돌려야 val 8건이 됨 |
| C3 | GPU 기준 출력 | 이 checkout의 `outputs/qlora_r1/val`은 6건(scores.csv `n_docs` 6). 보고서의 val 8건 출력은 원격 브랜치 어디에도 없음(병합 전 PR #2 또는 로컬로 추정) → 받아 오거나 0'단계에서 다시 생성 |
| C4 | 4B 병합·변환 메모리 | 이 PC 메모리 15GB. 병합(bf16 약 8GB)은 될 것으로 보이나 4B 변환은 미확인. 부족하면 NPU 노트북에서 변환 |
| C5 | `app/model.py` 연결 | 빈 틀(담당 양세윤). `get_backend()`를 부르는 코드는 담당자가 넣음 |

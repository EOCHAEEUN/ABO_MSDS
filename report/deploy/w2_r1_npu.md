# 4B(r1) NPU 변환 · 실행 기록 (2026-09-30)

배포 경량화 결과다. 본 비교표(`report/scores.csv` · `final_table.md`)에 넣지 않는다(`docs/deploy_quant_plan.md` 2절).

## 대상
- 입력 모델: runs/deploy_r1/quark_awq_w4g128 (r1 nf4dq 병합 → AWQ uint4_wo_128, train 보정 32×512, attn sdpa, 제외 층 없음)
- 환경: Windows, Ryzen AI 1.8.0 (conda ryzen-ai-1.8.0), OGA 0.14.0, NPU 드라이버 32.0.203.329
- 기기: RTX 5070 기기와 같은 노트북. 양자화본을 /mnt/c/models/r1_quark 로 복사 후 wsl --shutdown
- 옮긴 파일 확인: `model.safetensors` sha256 `758c0aee2e14fd0f…` — 5070 쪽 원본과 같음 (`quant.json`은 D3에서 만들지 않아 원본 파일 해시와 직접 대조)

## W1 후처리
- 명령: C:\models 에서 `model_generate --hybrid --input C:\models\r1_quark --output C:\models\r1_hybrid`
- 결과: 성공 ("Model generated successfully"). "cache/ directory not found" 경고는 직후 cache\txn_bins.zip 생성으로 해소 (G5와 동일)
- generation_config.json 이 결과 폴더로 복사되지 않아 r1_quark 에서 수동 복사
- context_length 40960 → G2 통과 (val 최장 입력 3,043토큰). 16K 설정 키(`hybrid_opt_chunk_context` · `chunk_size`)는 L ≥ 4,200이라 넣지 않음
- 참고: 같은 `genai_config.json`의 RyzenAI provider 옵션에 `hybrid_opt_max_seq_length: 4096`이 있다. KR-SOTL-001은 입력 + 출력이 4,181(2,133 + 2,048)로 이 값을 넘었다. 이 값이 hybrid 품질에 영향을 주는지는 확인하지 않았다. 설정 사본: `runs/deploy_r1/w1_genai_config.json`
- 소요 시간: 미측정

## W2 val 10건 (NPU hybrid)
- 스크립트: `runs/deploy_r1/npu_demo.py` (원본 C:\models\npu_demo.py) — 입력은 runs/deploy_r1/demo/*.json (r1 val 평가와 같은 프롬프트 v1, thinking 끔, 토큰 수 1,319~3,043으로 `outputs/qlora_r1/val/_log.jsonl`의 input_tokens와 10건 모두 일치)
- 조건: greedy (do_sample=False 명시, genai_config 기본값은 샘플링), max_length = min(입력 + 2048, 40960)
- 출력: `outputs/deploy/deploy_r1_npu_hybrid/val/{doc_id}.json` (C:\models\r1_npu_out\{doc}.txt를 내용 그대로 옮김, 파싱 실패도 원문 그대로)
- prefill · total 시간은 실행 콘솔 출력을 옮겨 적은 값이다(로그 파일 없음)

| 문서 | 입력 | 출력 | prefill(s) | total(s) | json.loads | 공식 파서 | 스키마 |
|---|---|---|---|---|---|---|---|
| KR-3DSYS-001 | 1452 | 277 | 5.1 | 31.6 | OK | OK | FAIL |
| KR-ASIACEM-001 | 1592 | 831 | 3.1 | 116.5 | FAIL | OK (코드펜스) | FAIL |
| KR-ITW-001 | 1746 | 2048 (한도) | 3.8 | 254.7 | FAIL | FAIL (잘림) | — |
| KR-ITW-002 | 1559 | 433 | 3.2 | 59.3 | FAIL | FAIL (끝에 `}` 1개 더) | — |
| KR-KCC-001 | 2014 | 2048 (한도) | 3.7 | 270.1 | FAIL | FAIL (잘림) | — |
| KR-KCCSIL-001 | 1319 | 346 | 2.7 | 37.3 | OK | OK | FAIL |
| KR-NEOGEN-001 | 3043 | 360 | 13.0 | 52.2 | FAIL | OK (코드펜스) | FAIL |
| KR-NEOGEN-002 | 2987 | 720 | 6.2 | 96.0 | FAIL | OK (코드펜스) | FAIL |
| KR-NHCHEM-001 | 1570 | 805 | 3.2 | 80.7 | FAIL | OK (코드펜스) | FAIL |
| KR-SOTL-001 | 2133 | 2048 (한도) | 3.2 | 167.4 | FAIL | FAIL (잘림) | — |

- 공식 파서 = `core.schema.extract_json`(코드펜스 · 앞뒤 군말 제거), 스키마 = `core.schema.check_schema`. 채점기(`eval/score.py`)는 아직 돌리지 않았다
- **파싱 6/10, 스키마 0/10.** GPU r1 기록은 파싱 1.00 · 스키마 0.80
- 한도 미도달 json.loads FAIL 5건 중 4건은 ```` ```json ```` 코드펜스(공식 파서는 통과), 1건(KR-ITW-002)은 JSON 뒤에 `}`가 하나 더 붙은 형식 오류
- 스키마 실패(파싱된 6건, 오류 메시지 집계): 구조가 무너진 것이 대부분이다 — 문자열 자리에 객체(ingredients 15 · hazard_statements 8 · supplier 4), 필수 키 누락(ingredients 11 · ghs_classification 7 · product_name · recommended_use 각 2), 없는 키 추가(list_status 7 · ghs_classification 7 · supplier 5). 값 규칙 위반은 적다 — `ke_number` · `cas_number`에 "자료없음"(4 · 2), 자료없음인데 value를 채움(2), "구분 3(호흡기 자극)"(2). 그 밖에 `cas_number`에 "57-13-6 / KE-35144"처럼 CAS와 KE를 합친 사례
- 한도 도달 3건은 반복 출력 (예: KR-ITW-001 끝부분이 {"hazard_class":"구분 2","category":"구분 2"} 무한 반복)
- 속도: prefill 입력 1.3~2.1k토큰에서 2.7~5.1초, 3k토큰대 6~13초. decode 약 8~10토큰/초
- 참고: AMD 사전 최적화 amd/Qwen3-4B_rai_1.8.0_hybrid 는 243토큰 18.2초(약 13토큰/초)

## 예비 판정 (계획서 5절)
- 미달 (예비): 파싱(0.60)이 기준(r1 GPU 1.00)보다 낮고, 스키마 0/10, max_new_tokens 도달 문서가 새로 생김(3건)
- 정식 판정은 eval/score.py 채점 후 (점수는 report/deploy/ 에만)

## 원인 분리
- KR-KCCSIL-001 비교
  - GPU r1 기록: 한 줄 압축 JSON, 신호어 null/해당없음, CAS "63148-62-9"
  - NPU int4: 들여쓰기 JSON, 신호어 "경고"/기재 (없는 값 생성), CAS "63148-62-9 / KE-31068"
- 병합본 1건 확인: bf16 병합본을 GPU(transformers 5.17, venv, device_map auto, greedy)로 생성 → GPU r1 기록(`outputs/qlora_r1/val/KR-KCCSIL-001.json`)과 글자 단위로 동일 (228토큰, 75초). 스크립트 runs/deploy_r1/check_merged.py, 출력 runs/deploy_r1/demo/KR-KCCSIL-001.merged.txt
  → 이 1건에서는 병합(D1)이 결과를 바꾸지 않았다. 품질 저하는 양자화 또는 NPU 런타임 단계에서 생겼을 가능성이 크다
  - 계획서의 D4r(`.venv-quark` · CPU · val 10건)와는 환경 · 건수가 다르다. D4r를 대신하지 않는다
- D4 (양자화본 GPU): 실패. transformers 4.57.6 + Quark 0.11 에서 quark_awq_w4g128 로딩 시 "RuntimeError: expected a floating-point or complex dtype, but got dtype=torch.int32" (device_map auto · {"":0} 모두). 계획서 U8 "틀렸을 때"에 해당. 스크립트 runs/deploy_r1/check_quant.py
- 대안: `model_generate --oga_only` 로 NPU 없이 CPU int4 모델을 만들어 같은 문서 실행 → 양자화 탓인지 NPU(BFP16 · hybrid) 탓인지 분리
  - C:\models\r1_oga 는 만들어져 있다(10:20). 이 모델로 생성한 출력은 아직 없다
- 기타 관찰: .venv-quark 에서 양자화본 토크나이저 로딩 시 "incorrect regex pattern" 경고. 시연 입력은 venv 에서 만든 토큰 ID라 영향 없음. 다만 AWQ 보정 표본 토큰화에는 영향이 있었을 수 있음 (미확인)

## 원인 후보 (미확정)
1. 보정 데이터 축소 (계획 128×3,200 → 실제 32×512)
2. NF4 격자에 맞춰 학습된 어댑터와 uint4 group 128 격자의 차이
3. lm_head int4 양자화
4. NPU 런타임 (BFP16 활성값, hybrid 변환)
5. 보정 표본 토큰화 (regex 경고)

## 저장소 밖에 있는 것 (Windows)
- C:\models\r1_hybrid (NPU 모델), C:\models\r1_oga (CPU int4 모델) — 가중치라 저장소 제외

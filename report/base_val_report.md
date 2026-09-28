# val Base 채점 결과 (base_zs · base_fs)

- 실행일: 2026-09-28
- 조건: `base_zs`, `base_fs` (few-shot: `KR-HANIL-002`, `KR-KUMHO-002`, train)
- split: val 10건(8개 그룹, 현행 5 · 수입품 국문판 5) — 전부 `subset=ko`
- 정답: `data/gold_set`(정리 전, `data/labels`는 아직 09-23 옛 라벨이 섞여 있어 사용 안 함)
- 실행: `python3 eval/infer.py --condition {base_zs,base_fs} --split val [--label-dir data/gold_set]` → `python3 eval/score.py --condition {base_zs,base_fs} --split val --label-dir data/gold_set`
- 결과 원본: `report/scores.csv` / 문서별 상세: `outputs/{condition}/val/_score_detail.jsonl`

> val은 조건 선택용 수치이며, 그룹 수(8개)가 적어 이 결과 자체를 최종 보고 수치로 쓰지 않는다(plan 5절).

## 결과표

| metric | base_zs | base_fs |
|---|---:|---:|
| n_docs | 10 | 10 |
| n_missing_output | 0 | 0 |
| parse_rate | 1.0000 | 1.0000 |
| schema_rate | 0.5000 | 0.8000 |
| product_name_acc | 0.9000 | 0.9000 |
| signal_word_acc | 1.0000 | 0.9000 |
| ghs_status_acc | 1.0000 | 0.9000 |
| hazard_status_acc | 1.0000 | 0.9000 |
| ghs_p / r / f1 | 0.4242 / 0.3415 / 0.3784 | 0.8372 / 0.8780 / 0.8571 |
| hcode_p / r / f1 | 1.0000 / 1.0000 / 1.0000 | 1.0000 / 1.0000 / 1.0000 |
| htext_p / r / f1 | (해당 없음, 0/0) | 0.0000 / 0.0000 / 0.0000 |
| cas_p / r / f1 | 1.0000 / 0.8529 / 0.9206 | 1.0000 / 0.7647 / 0.8667 |
| pair_p / r / f1 | 1.0000 / 0.8529 / 0.9206 | 1.0000 / 0.7647 / 0.8667 |
| nocas_p / r / f1 | 0.3333 / 0.6667 / 0.4444 | 0.4286 / 1.0000 / 0.6000 |
| content_acc | 1.0000 | 1.0000 |
| doc_exact_rate | 0.3000 | 0.4000 |
| doc_exact_ext_rate | 0.2000 | 0.4000 |
| fab_hcode_n / fab_hcode_docs / fab_ghs_docs / fab_cas_n / fab_any_docs | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| misplace_ke_n / misplace_content_n | 4 / 0 | 2 / 0 |
| gen_time_mean_s | 29.5760 | 30.5361 |
| input_tokens_mean | 1941.5000 | 4282.5000 |
| output_tokens_mean | 597.8000 | 595.2000 |
| n_hit_max_new_tokens | 0 | 0 |

## 관찰

- **schema_rate가 낮음** (base_zs 0.50 / base_fs 0.80, 목표 95%). 길이 초과로 잘린 문서는 없음(`n_hit_max_new_tokens = 0`) — 형식 자체의 문제로 보임. `_score_detail.jsonl`에서 위반 필드 확인 필요.
- **GHS F1은 few-shot이 크게 우위** (0.378 → 0.857). 아래 "별칭표 밖 분류명" 항목과 연결해서 볼 것.
- **CAS/pair F1은 zero-shot이 근소 우위** (0.921 → 0.867) — few-shot이 항상 낫지는 않음. 표본이 작아(10건) 우연일 가능성도 있음.
- **base_fs의 htext_f1 = 0** — H코드 없이 문구만 있는 케이스를 few-shot에서 전부 놓침. 실패 사례 후보.
- **misplace_ke_n**(KE 칸 오입력)이 두 조건 모두 발생(4건 / 2건). fab_* 계열(무근거 생성)은 0으로, 원문에 없는 값을 지어내는 문제는 없음.
- input_tokens_mean: few-shot이 zero-shot 대비 2.2배(1941→4283). 목표(fs 대비 60% 이하)는 QLoRA와 비교할 때 지표.

## 별칭표(`eval/hazard_class_alias.csv`) 보강 후보

score.py가 화면에 출력한, 별칭표에 없는 **모델 출력(pred)** 분류명 목록. val 단계라 자동으로 알려주는 것이며, **아직 별칭표에 반영하지 않았음** — 고시 원문 대조 후 정규 분류명을 확정해서 넣어야 함(plan 8절: "대응표는 고시 원문에서 만든다. 모델 출력에서 거꾸로 만들지 않는다").

### base_zs
- 구분 1
- 구분 2
- 구분 5
- 구분2
- 구분3
- 구분4
- 급성 독성 (경구), 구분 4
- 급성 독성 (경피), 구분 4
- 급성 독성 (흡입: 분진, 미스트), 구분 4
- 만성 수생환경, 구분 2
- 생식독성, 구분 1A
- 심한 눈 손상성/눈 자극성, 구분 2
- 특정 표적장기 독성 (1회 노출), 구분 2
- 특정 표적장기 독성 (반복 노출), 구분 2
- 피부 과민성, 구분 1
- 피부 부식성/피부 자극성, 구분 2

⚠️ **주의:** 위 목록 중 `구분 1`·`구분 2`·`구분 5`·`구분2`·`구분3`·`구분4`는 `category`가 아니라 `hazard_class` 자리에서 별칭표 밖으로 잡힌 값이다. 즉 base_zs가 일부 문서에서 `hazard_class`에 분류명 대신 "구분 N"만 적었거나, `hazard_class`·`category`를 통째로 한 문자열로 합쳐 낸 것으로 보인다. 이건 별칭표를 늘려서 해결할 문제가 아니라 **base_zs의 GHS 필드 형식 오류(스키마·GHS F1 저하의 원인 중 하나로 의심)** 이므로 `_score_detail.jsonl`에서 해당 문서를 먼저 확인해야 한다.

### base_fs
- 건강 유해성
- 물리적 위험성
- 수생환경 유해성
- 인화성
- 환경 유해성

⚠️ 이쪽은 개별 위험군을 나타내는 **상위 범주명**으로 보인다(예: "물리적 위험성" 아래 여러 세부 분류가 있어야 하는데 상위 범주만 적었을 가능성). 원문 대조가 필요하다.

## 다음 확인 사항
- [ ] `schema_rate` 낮은 원인 — `_score_detail.jsonl`에서 위반 필드·문서 확인
- [ ] base_zs의 `hazard_class`에 "구분 N"만 들어간 문서 확인 (원문 대조)
- [ ] base_fs `htext_f1 = 0` 사례 원문 대조
- [ ] 별칭표 보강 여부는 고시 원문 대조 후 PM/규 담당 판단

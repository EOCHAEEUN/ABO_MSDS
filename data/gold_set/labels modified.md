## 요약

- 변경된 파일: **5개** / 43개
- 변경 없는 파일: **38개** / 43개
- 세부 변경 항목: **20개** (값 변경 7, 추가 2, 삭제 1)

| 파일 | 변경 항목 수 |
|---|---:|
| `KR-3DSYS-001.json` | 1 |
| `KR-HANIL-003.json` | 3 |
| `KR-NOROO-002.json` | 8 |
| `KR-OCI-003.json` | 5 |
| `KR-OCI-004.json` | 3 |

## 파일별 변경 내역

### `KR-3DSYS-001.json`

| JSON 경로 | 유형 | 원본 값 | 수정본 값 |
|---|---|---|---|
| `$.supplier.company_name` | 변경 | `"3D SYSTEMS"` | `null` |

### `KR-HANIL-003.json`

| JSON 경로 | 유형 | 원본 값 | 수정본 값 |
|---|---|---|---|
| `$.hazard_statements[3].code` | 변경 | `"17"` | `null` |

### `KR-NOROO-002.json`

| JSON 경로 | 유형 | 원본 값 | 수정본 값 |
|---|---|---|---|
| `$.ghs_classification[2].hazard_class` | 변경 | `"급성독성물질 흡입"` | `"급성독성물질 흡입(증기)"` |

### `KR-OCI-003.json`

| JSON 경로 | 유형 | 원본 값 | 수정본 값 |
|---|---|---|---|
| `$.ghs_classification[1]` | 추가 | — | `{"category": "구분 4", "hazard_class": "급성 독성-경피"}` |
| `$.hazard_statements[2]` | 추가 | — | `{"code": "H312", "text": "피부와 접촉하면 유해함"}` |
| `$.ingredients[0].content` | 변경 | `"24~26"` | `"49~51"` |
| `$.ingredients[1].content` | 변경 | `"74~76"` | `"49~51"` |

### `KR-OCI-004.json`

| JSON 경로 | 유형 | 원본 값 | 수정본 값 |
|---|---|---|---|
| `$.hazard_statements[2]` | 삭제 | `{"code": "H312", "text": "피부와 접촉하면 유해함"}` | — |
| `$.ingredients[0].content` | 변경 | `"49~51"` | `"24~26"` |
| `$.ingredients[1].content` | 변경 | `"49~51"` | `"74~76"` |

## 변경 없는 파일

`KR-ASIACEM-001.json`, `KR-DUKSAN-001.json`, `KR-GSC-001.json`, `KR-GSC-002.json`, `KR-GSC-003.json`, `KR-GSC-004.json`, `KR-HANIL-001.json`, `KR-HENKEL-001.json`, `KR-HENKEL-002.json`, `KR-KCCSIL-001.json`, `KR-KNAUF-001.json`, `KR-KNAUF-002.json`, `KR-KUMHO-001.json`, `KR-KUMHO-002.json`, `KR-KUMHO-003.json`, `KR-KUMHO-004.json`, `KR-KUMHO-005.json`, `KR-KUMHO-006.json`, `KR-NEOGEN-001.json`, `KR-NEOGEN-002.json`, `KR-NOROO-003.json`, `KR-NOROO-004.json`, `KR-NOROO-006.json`, `KR-NOROO-007.json`, `KR-OCI-001.json`, `KR-OCI-002.json`, `KR-SOTL-001.json`, `KR-THERMO-001.json`, `KR-OCI-006.json`, `KR-OCI-005.json`, `KR-NOROO-001.json`, `KR-NHCHEM-001.json`, `KR-KCC-001.json`, `KR-HANIL-006.json`, `KR-HANIL-005.json`, `KR-HANIL-004.json`, `KR-HANIL-002.json`

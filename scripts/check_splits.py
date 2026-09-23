"""splits.csv가 v5 분할 규칙을 지키는지 검사한다.  사용법: python scripts/check_splits.py data/splits.csv"""
import csv, sys, collections
path = sys.argv[1] if len(sys.argv) > 1 else "data/splits.csv"
rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
by = collections.defaultdict(list)
for r in rows: by[r["split"]].append(r)
err = []
cnt = {k: len(v) for k, v in by.items()}
print("건수:", cnt)
ko = lambda s: [r for r in by[s] if r["lang"] == "ko"]
en = lambda s: [r for r in by[s] if r["lang"] == "en"]
if len(by["train"]) != 24: err.append("train은 24건이어야 함")
if len(by["val"]) != 4: err.append("val은 4건이어야 함")
if len(ko("test")) != 15 or len(en("test")) != 5: err.append("test는 국문 15 + 영문 5여야 함")
if en("train") or en("val"): err.append("영문은 train·val에 들어갈 수 없음(학습·few-shot 금지)")
# 같은 split_group이 train과 평가용(val/test)에 걸치면 안 됨. 예외: 노루 구서식(train 2 / test 3)
EVAL = {"val", "test"}
grp = collections.defaultdict(set)
for r in rows: grp[r["split_group"]].add(r["split"])
for g, ss in grp.items():
    if "train" in ss and ss & EVAL and g != "NOROO":
        err.append(f"split_group {g}가 train과 {ss & EVAL}에 걸침")
# val 제조사는 train과 겹치면 안 됨
tm = {r["manufacturer"] for r in by["train"]}
for r in by["val"]:
    if r["manufacturer"] in tm: err.append(f"val {r['doc_id']} 제조사가 train과 겹침")
# test 제조사는 노루 계열 예외만 허용
for r in by["test"]:
    if r["manufacturer"] in tm and r["split_group"] != "NOROO": err.append(f"test {r['doc_id']} 제조사가 train과 겹침")
old_tr = [r for r in by["train"] if r["form"] == "구서식"]; old_te = [r for r in by["test"] if r["form"] == "구서식"]
if len(old_tr) != 2 or len(old_te) != 3: err.append("구서식은 train 2 / test 3이어야 함")
# 사전 검증에 쓴 문서는 test 금지
for d in ("KR-THERMO-001", "KR-NOROO-004", "KR-NOROO-005"):
    if any(r["doc_id"] == d and r["split"] == "test" for r in rows): err.append(f"{d}는 사전 검증 문서라 test 불가")
print("test 국문 서식:", collections.Counter(r["form"] for r in ko("test")))
print("train 서식:", collections.Counter(r["form"] for r in by["train"]))
print("\n".join(err) if err else "규칙 위반 없음")
sys.exit(1 if err else 0)

"""배정 제안(scripts/propose_splits.py) 테스트 — 결정적 순서, 부족분 비율 · 동률 규칙, 기존 그룹 따르기,
메타데이터 외 열을 읽지 않는지 본다. 실제 splits.csv 대신 가짜 기존 분할을 쓴다.

실행: python -m pytest test/test_propose_splits.py -v
      (pytest 없으면) python test/test_propose_splits.py
"""
import csv
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scripts.propose_splits as ps  # noqa: E402


def existing(train=24, val=6, t2_cur=3, t2_imp=5):
    """가짜 기존 분할. 분할마다 제조사 그룹 하나"""
    rows = []
    for split, form, k, g in (("train", "현행", train, "TR"), ("val", "현행", val, "VA"),
                              ("test2", "현행", t2_cur, "T2C"), ("test2", "수입품 국문판", t2_imp, "T2I"),
                              ("test", "현행", 1, "TE")):
        rows += [{"doc_id": f"KR-{g}-{i:03d}", "split": split, "lang": "ko", "form": form,
                  "manufacturer": g, "split_group": g} for i in range(k)]
    return rows


def cand(doc_id, group, form="현행", lang="ko", mfr=None):
    return {"doc_id": doc_id, "lang": lang, "form": form, "manufacturer": mfr or group, "split_group": group}


def pick(rows):
    return {r["doc_id"]: r["제안"] for r in rows}


def test_01_same_result_regardless_of_input_order():
    cs = [cand(f"KR-N{i}-001", f"N{i}") for i in range(12)]
    a, _, after_a = ps.propose(existing(), cs)
    b, _, after_b = ps.propose(existing(), list(reversed(cs)))
    assert pick(a) == pick(b) and after_a == after_b


def test_02_tie_goes_to_test2_then_val():
    # train 25/50 부족 = 0.5, test2 현행 15/30 부족 = 0.5, val 부족 0 → test2
    rows, _, _ = ps.propose(existing(train=25, val=15, t2_cur=15, t2_imp=10), [cand("KR-X-001", "X")])
    assert pick(rows)["KR-X-001"] == "test2", rows
    # test2 가득, val 3/15 = 0.2, train 10/50 = 0.2 → val
    rows, _, _ = ps.propose(existing(train=40, val=12, t2_cur=30, t2_imp=10), [cand("KR-X-001", "X")])
    assert pick(rows)["KR-X-001"] == "val", rows


def test_03_group_that_fits_beats_higher_ratio():
    # 3건 그룹: val 2/15 = 0.13(안 들어감), train 5/50 = 0.10(들어감) → train
    cs = [cand(f"KR-Y-00{i}", "Y") for i in range(3)]
    rows, _, _ = ps.propose(existing(train=45, val=13, t2_cur=30, t2_imp=10), cs)
    assert set(pick(rows).values()) == {"train"}, rows
    # 어디에도 안 들어가면 비율이 큰 곳 + 목표 초과 표시
    rows, _, _ = ps.propose(existing(train=49, val=13, t2_cur=30, t2_imp=10), cs)
    assert set(pick(rows).values()) == {"val"} and "목표 초과" in rows[0]["확인"], rows


def test_04_existing_groups_are_followed():
    ex = existing() + [{"doc_id": "EN-VE-001", "split": "val_en", "lang": "en", "form": "영문",
                        "manufacturer": "VE", "split_group": "VE"}]
    cs = [cand("KR-VA-900", "VA"), cand("EN-T2C-900", "T2C", "영문", "en"), cand("KR-TE-900", "TE"),
          cand("KR-VE-900", "VE"), cand("KR-T2C-900", "T2C")]
    got = pick(ps.propose(ex, cs)[0])
    assert got["KR-VA-900"] == "val"
    assert got["EN-T2C-900"] == "excluded"          # test2 그룹의 영문판
    assert got["KR-TE-900"] == "excluded"           # 기존 test 그룹(동결)
    assert got["KR-VE-900"] in ("train", "val")     # val_en 그룹의 국문판은 test2 불가
    assert got["KR-T2C-900"] == "test2"


def test_05_exposed_or_shared_manufacturer_never_test2():
    ex = existing(train=40, val=15, t2_cur=3, t2_imp=10)   # test2 현행 부족이 가장 큼
    rows, _, _ = ps.propose(ex, [cand("KR-Z-001", "Z")], seen={"KR-Z-001": ["학습 JSONL"]})
    assert pick(rows)["KR-Z-001"] != "test2", rows
    rows, _, _ = ps.propose(ex, [cand("KR-W-001", "W", mfr="TR")])  # 제조사가 train과 같음
    assert pick(rows)["KR-W-001"] == "train" and "split_group 확인" in rows[0]["확인"], rows


def test_07_test2_target_counts_main_and_pending_only():
    ex = existing(train=50, val=15, t2_cur=4, t2_imp=10)
    roles = {"KR-T2C-000": {"role": "main"}, "KR-T2C-001": {"role": "pending"},
             "KR-T2C-002": {"role": "exposed"}, "KR-T2C-003": {"role": "exposed"}}
    _, before, _ = ps.propose(ex, [], roles=roles)
    assert before["test2/현행"] == 2, before                  # exposed 2건은 주 분석 자리로 세지 않음
    rows, _, after = ps.propose(ex, [cand("KR-T2C-900", "T2C")], roles=roles)
    assert pick(rows)["KR-T2C-900"] == "test2" and "영향받은 그룹" in rows[0]["확인"], rows
    assert after["test2/현행"] == 2, after                    # 영향받은 그룹을 따른 문서도 세지 않음


def test_06_only_metadata_columns_are_read():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.csv")
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(ps.META) + ["signal_word", "n_ghs"])
            w.writerow(["KR-Q-001", "ko", "현행", "Q", "Q", "위험", "3"])
            w.writerow(["KR-OLD-001", "ko", "현행", "OLD", "OLD", "경고", "1"])
        got = ps.read_candidates(p, assigned={"KR-OLD-001"})
    assert got == [{"doc_id": "KR-Q-001", "lang": "ko", "form": "현행", "manufacturer": "Q", "split_group": "Q"}]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}  {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)

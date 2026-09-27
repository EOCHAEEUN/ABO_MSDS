"""짝 비교(eval/paired.py) 테스트 — 부트스트랩이 split_group 단위로 뽑는지 본다.

실행: python -m pytest test/test_paired.py -v
      (pytest 없으면) python test/test_paired.py
"""
import collections
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eval.paired as paired  # noqa: E402


def docs_in(groups):
    """{doc: 그룹} 과 문서 목록"""
    group_of = {d: g for g, ds in groups.items() for d in ds}
    return group_of, sorted(group_of)


def row(ext):
    return {"ext": ext, "exact": ext}


def test_01_resample_keeps_groups_whole():
    group_of, docs = docs_in({"DAIKIN": ["D1", "D2", "D3"], "KZ": ["K1", "K2"], "NEOGEN": ["N1"]})
    rng = random.Random(0)
    for _ in range(200):
        s = collections.Counter(paired.resample(paired.clusters(docs, group_of), rng))
        for g in ("DAIKIN", "KZ"):
            counts = {s[d] for d in docs if group_of[d] == g}
            assert len(counts) == 1, f"{g} 문서가 따로 뽑힘: {s}"


def test_02_clustered_wins_do_not_look_certain():
    """한 그룹(5건)에서만 이기고 다른 그룹(5건)은 무승부 — 문서 단위면 0을 넘는 CI가 나오지만 그룹 단위면 0을 포함"""
    group_of, docs = docs_in({"X": [f"X{i}" for i in range(5)], "Y": [f"Y{i}" for i in range(5)]})
    a = {d: row(False) for d in docs}
    b = {d: row(d.startswith("X")) for d in docs}
    point, lo, hi = paired.bootstrap(a, b, docs, "ext", random.Random(1), group_of)
    assert point == 0.5
    assert lo == 0.0, f"그룹 단위 하한이 0이어야 함: {lo}"
    doc_level = {d: d for d in docs}                         # 문서마다 다른 그룹 = 기존 방식
    _, lo_doc, _ = paired.bootstrap(a, b, docs, "ext", random.Random(1), doc_level)
    assert lo_doc > 0.0, f"대조: 문서 단위면 하한이 0보다 커야 함: {lo_doc}"


def test_03_single_group_has_no_ci():
    group_of, docs = docs_in({"ITW": ["I1", "I2"]})
    a = {d: row(False) for d in docs}
    b = {d: row(True) for d in docs}
    assert paired.bootstrap(a, b, docs, "ext", random.Random(2), group_of) == (1.0, None, None)
    assert "그룹 1개" in paired.fmt_ci((1.0, None, None))


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

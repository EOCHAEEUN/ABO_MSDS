"""채점기 회귀 테스트 — 한 필드만 일부러 틀린 예측이 그 필드에서만 틀린 것으로 잡히는지 본다.

self-check(정답 = 예측)는 "다 맞으면 1.0"만 확인하므로, nocas 계산이 pair 판정 변수를 덮어써
문서 완전 정답이 틀리게 나온 버그(2026-09-27)를 잡지 못했다. 그 경우를 포함해 고정한다.
정답은 train·val 라벨(data/labels/)만 쓴다.

실행: python -m pytest test/test_score.py -v
      (pytest 없으면) python test/test_score.py
"""
import copy
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from eval.score import Acc, doc_exact, score_doc  # noqa: E402


def label(doc_id):
    with open(os.path.join(ROOT, "data", "labels", f"{doc_id}.json"), encoding="utf-8") as f:
        return json.load(f)


def text(doc_id):
    with open(os.path.join(ROOT, "data", "text", f"{doc_id}.txt"), encoding="utf-8") as f:
        return f.read()


def run(gold, pred, source=None):
    acc = Acc()
    d = score_doc(gold, pred, acc, False, defaultdict(set), source)
    exact, ext = doc_exact(d, pred)
    return d, dict(acc.rows()), exact, ext


# KR-GSC-001: 성분 4 (CAS 있는 3 + 영업비밀 1, CAS null · 함유량 0.1~2)
GSC = "KR-GSC-001"
# KR-KCC-001: H코드 있는 유해·위험문구 7건
KCC = "KR-KCC-001"


def test_01_identical_is_all_ok():
    g = label(GSC)
    d, m, exact, ext = run(g, copy.deepcopy(g), text(GSC))
    assert exact and ext
    assert all(d[k] == "ok" for k in ("ghs", "hcode", "htext", "cas", "pair", "nocas"))
    assert m["misplace_ke_n"] == 0 and m["misplace_content_n"] == 0 and m["fab_any_docs"] == 0


def test_02_pair_only_wrong():
    """CAS는 맞고 함유량만 틀림 → pair만 오답, 나머지는 ok, 두 기준 모두 오답"""
    g = label(GSC)
    p = copy.deepcopy(g)
    i = next(i for i, c in enumerate(p["ingredients"]) if c["cas_number"])
    p["ingredients"][i]["content"] = "50~60"
    d, m, exact, ext = run(g, p)
    assert d["pair"] != "ok" and d["cas"] == "ok" and d["nocas"] == "ok"
    assert not exact and not ext


def test_03_nocas_only_wrong_keeps_legacy_exact():
    """CAS 없는 성분만 하나 더 지어냄 → nocas만 오답. 기존 기준은 정답, 확장 기준만 오답.
    (2026-09-27 버그: nocas의 fp가 pair 판정 변수를 덮어써 기존 기준까지 오답으로 나왔다)"""
    g = label(GSC)
    p = copy.deepcopy(g)
    p["ingredients"].append({"chemical_name": "영업비밀2", "cas_number": None, "ke_number": None,
                             "content": "1~2", "is_substitute_data": True})
    d, m, exact, ext = run(g, p)
    assert d["pair"] == "ok" and d["cas"] == "ok"
    assert d["nocas"] != "ok" and d["nocas"]["fp"] == 1
    assert exact and not ext


def test_04_substitute_flag_wrong():
    """영업비밀 성분의 is_substitute_data만 틀림 → nocas 오답(plan 4절: 영업비밀은 플래그와 함유량으로 판정)"""
    g = label(GSC)
    p = copy.deepcopy(g)
    for c in p["ingredients"]:
        if c["is_substitute_data"]:
            c["is_substitute_data"] = False
    d, m, exact, ext = run(g, p)
    assert d["nocas"] != "ok" and d["pair"] == "ok"
    assert exact and not ext


def test_05_ec_number_in_ke_field():
    """EC 번호를 ke_number에 넣음 → misplace_ke 1, 확장 기준 오답(스키마에서도 걸림)"""
    g = label(GSC)
    p = copy.deepcopy(g)
    i = next(i for i, c in enumerate(p["ingredients"]) if c["cas_number"])
    p["ingredients"][i]["ke_number"] = "265-157-1"
    d, m, exact, ext = run(g, p)
    assert m["misplace_ke_n"] == 1 and m["misplace_content_n"] == 0
    assert not ext


def test_06_cas_in_content_field():
    """함유량 칸에 CAS → misplace_content 1, pair 오답"""
    g = label(GSC)
    p = copy.deepcopy(g)
    i = next(i for i, c in enumerate(p["ingredients"]) if c["cas_number"])
    p["ingredients"][i]["content"] = p["ingredients"][i]["cas_number"]
    d, m, exact, ext = run(g, p)
    assert m["misplace_content_n"] == 1 and d["pair"] != "ok"
    assert not exact and not ext


def test_07_fabricated_h_code():
    """원문에 없는 H코드를 붙임 → 무근거 생성 1, H코드 오답"""
    g = label(KCC)
    p = copy.deepcopy(g)
    p["hazard_statements"].append({"code": "H999", "text": "지어낸 문구"})
    d, m, exact, ext = run(g, p, text(KCC))
    assert d["fabricated"]["hcode"] == ["H999"] and m["fab_hcode_n"] == 1
    assert d["hcode"] != "ok" and not exact


def test_08_split_cas_is_not_fabricated():
    """PDF에서 "134759-18-" / "5"로 줄이 갈린 CAS를 무근거 생성으로 세지 않는다(KR-GSC-002)"""
    g = label("KR-GSC-002")
    assert "134759-18-5" not in text("KR-GSC-002").replace("\n", "").replace(" ", "")
    d, m, exact, ext = run(g, copy.deepcopy(g), text("KR-GSC-002"))
    assert "fabricated" not in d and m["fab_cas_n"] == 0


def test_09_empty_prediction_counts_everything_missing():
    """파싱 실패(빈 예측) → 두 기준 모두 오답, 정답 항목은 전부 FN"""
    g = label(KCC)
    d, m, exact, ext = run(g, {})
    assert not exact and not ext
    assert m["hcode_r"] == 0.0 and m["cas_r"] == 0.0


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

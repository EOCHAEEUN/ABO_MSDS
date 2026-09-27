"""봉인(eval/seal.py) 테스트 — test2 두 단계 봉인이 바꿔치기를 잡는지 본다.

실제 저장소 파일은 건드리지 않는다: 임시 폴더에 가짜 splits·sources·PDF·정답·텍스트를 만들고
seal 모듈의 경로를 그쪽으로 돌린다.

실행: python -m pytest test/test_seal.py -v
      (pytest 없으면) python test/test_seal.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eval.seal as seal  # noqa: E402

DOCS = ["KR-NEWA-001", "KR-NEWB-001"]


def sandbox():
    """임시 프로젝트를 만들고 seal 경로를 돌린다 → 임시 루트"""
    t = Path(tempfile.mkdtemp())
    for sub in ("data/raw", "data/text", "eval/test", "eval/test2", "report"):
        (t / sub).mkdir(parents=True)
    rows = ["doc_id,split,lang,form,manufacturer,split_group"]
    rows += [f"{d},test2,ko,현행,m{i},G{i}" for i, d in enumerate(DOCS)] + ["KR-OLD-001,train,ko,현행,old,OLD"]
    (t / "data/splits.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    src = ["doc_id,source_file"] + [f"{d},{d}.pdf" for d in DOCS] + ["KR-OLD-001,old.pdf"]
    (t / "data/sources.csv").write_text("\n".join(src) + "\n", encoding="utf-8")
    for d in DOCS:
        (t / f"data/raw/{d}.pdf").write_bytes(f"pdf {d}".encode())
    for name, rel in (("SPLITS_CSV", "data/splits.csv"), ("SOURCES_CSV", "data/sources.csv"),
                      ("RAW_DIR", "data/raw"), ("TEXT_DIR", "data/text"), ("TEST_DIR", "eval/test"),
                      ("MANIFEST", "report/test_manifest.csv"), ("TEST2_DIR", "eval/test2"),
                      ("TEST2_DOCS", "report/test2_docs_manifest.csv"), ("TEST2_MANIFEST", "report/test2_manifest.csv")):
        setattr(seal, name, t / rel)
    seal.ROOT = t
    return t


def write_cut(t, status):
    """data/text/_cut_log.csv — {doc_id: 상태}"""
    rows = ["doc_id,status"] + [f"{d},{st}" for d, st in status.items()]
    (t / "data/text/_cut_log.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def label_and_text(t, no_text=()):
    """정답은 모두, 텍스트는 no_text를 뺀 문서만. 추출 기록은 텍스트가 있으면 SUCCESS, 없으면 NOT_FOUND"""
    for d in DOCS:
        (t / f"eval/test2/{d}.json").write_text('{"x": 1}', encoding="utf-8")
        if d not in no_text:
            (t / f"data/text/{d}.txt").write_text(f"text {d}", encoding="utf-8")
    write_cut(t, {d: "NOT_FOUND" if d in no_text else "SUCCESS" for d in DOCS})


def sealed(t, no_text=()):
    seal._write_docs(False)
    label_and_text(t, no_text)
    seal._write_test2(False)


def raises_exit(fn, *a):
    try:
        fn(*a)
    except SystemExit as e:
        return str(e.code)
    return None


def test_01_full_flow_passes():
    t = sandbox()
    assert not seal.verify("test2")[0]                      # 봉인 전
    seal._write_docs(False)
    assert not seal.verify("test2")[0]                      # 1단계만: 아직 실패
    label_and_text(t)
    seal._write_test2(False)
    ok, msg = seal.verify("test2")
    assert ok, msg


def test_02_docs_seal_refused_after_labeling_started():
    t = sandbox()
    label_and_text(t)
    assert "라벨링 전" in raises_exit(seal._write_docs, False)


def test_03_label_seal_requires_docs_seal():
    t = sandbox()
    label_and_text(t)
    assert "1단계" in raises_exit(seal._write_test2, False)


def test_04_changed_label_detected():
    t = sandbox()
    seal._write_docs(False)
    label_and_text(t)
    seal._write_test2(False)
    (t / f"eval/test2/{DOCS[0]}.json").write_text('{"x": 2}', encoding="utf-8")
    ok, msg = seal.verify("test2")
    assert not ok and "정답" in msg


def test_05_changed_input_text_detected():
    t = sandbox()
    seal._write_docs(False)
    label_and_text(t)
    seal._write_test2(False)
    (t / f"data/text/{DOCS[1]}.txt").write_text("고친 추출", encoding="utf-8")
    ok, msg = seal.verify("test2")
    assert not ok and "입력 텍스트" in msg


def test_06_swapped_document_detected():
    """봉인 뒤 splits.csv에서 test2 문서를 다른 문서로 바꿈"""
    t = sandbox()
    seal._write_docs(False)
    s = (t / "data/splits.csv").read_text(encoding="utf-8").replace(DOCS[1], "KR-NEWZ-001")
    (t / "data/splits.csv").write_text(s, encoding="utf-8")
    assert any("봉인 목록과 다름" in p for p in seal._verify_docs())


def test_07_changed_pdf_detected():
    t = sandbox()
    seal._write_docs(False)
    (t / f"data/raw/{DOCS[0]}.pdf").write_bytes(b"other pdf")
    assert any("원본 PDF" in p for p in seal._verify_docs())


def test_08_legacy_test_unchanged():
    """기존 test 봉인 동작은 그대로: 봉인 전이면 실패 메시지"""
    sandbox()
    ok, msg = seal.verify()
    assert not ok and "test_manifest.csv" in msg


def test_09_stage2_row_removed_detected():
    """2단계 manifest에서 한 문서 행을 지워도 통과하던 빈틈"""
    t = sandbox()
    sealed(t)
    m = t / "report/test2_manifest.csv"
    lines = m.read_text(encoding="utf-8").splitlines()
    m.write_text("\n".join(l for l in lines if not l.startswith(DOCS[1])) + "\n", encoding="utf-8")
    ok, msg = seal.verify("test2")
    assert not ok and "1단계와 다름" in msg, msg


def test_10_missing_text_without_failure_record_refused():
    t = sandbox()
    seal._write_docs(False)
    label_and_text(t)
    (t / f"data/text/{DOCS[0]}.txt").unlink()               # 텍스트만 없고 기록은 SUCCESS
    assert "추출 실패 기록이 없음" in raises_exit(seal._write_test2, False)
    write_cut(t, {DOCS[1]: "SUCCESS"})                       # 기록 자체가 없음
    assert "추출 실패 기록이 없음" in raises_exit(seal._write_test2, False)


def test_11_recorded_extraction_failure_is_sealed_and_kept():
    """추출 실패는 기록이 있으면 봉인되고 manifest에 남는다(평가 분모에서 빼지 않음)"""
    t = sandbox()
    sealed(t, no_text=(DOCS[0],))
    ok, msg = seal.verify("test2")
    assert ok, msg
    rows = seal.read_csv(t / "report/test2_manifest.csv")
    assert set(rows) == set(DOCS) and rows[DOCS[0]]["cut_status"] == "NOT_FOUND" and rows[DOCS[0]]["text_sha256"] == ""


def test_12_cut_status_changed_after_seal_detected():
    """봉인 뒤 추출 기록만 NOT_FOUND로 바꿔 추론에서 빼는 경우"""
    t = sandbox()
    sealed(t)
    write_cut(t, {DOCS[0]: "NOT_FOUND", DOCS[1]: "SUCCESS"})
    ok, msg = seal.verify("test2")
    assert not ok and "추출 상태" in msg, msg


def test_13_text_present_but_marked_failed_refused():
    t = sandbox()
    seal._write_docs(False)
    label_and_text(t)
    write_cut(t, {DOCS[0]: "NOT_FOUND", DOCS[1]: "SUCCESS"})
    assert "건너뛰게 됨" in raises_exit(seal._write_test2, False)


def test_14_text_added_after_failure_seal_detected():
    """실패로 봉인한 문서에 나중에 텍스트를 만들어 넣은 경우"""
    t = sandbox()
    sealed(t, no_text=(DOCS[0],))
    (t / f"data/text/{DOCS[0]}.txt").write_text("재추출", encoding="utf-8")
    ok, msg = seal.verify("test2")
    assert not ok and "입력 텍스트" in msg, msg


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

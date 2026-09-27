"""test2 역할 목록(eval/test2_roles.py) 테스트 — 목록 검사, 채점 · 짝 비교가 같은 목록과 같은 분모를 쓰는지 본다.

가짜 test2 문서 4건(주 분석 2 · 구서식 1 · 노출 보조 1)을 임시 폴더에 만든다. 정답 내용은 train 라벨을 복사해 쓴다.
주 분석 대상 중 1건은 출력 파일이 없고(추출 · 생성 실패), 노출 보조 1건은 JSON이 깨져 있다.

실행: python -m pytest test/test_test2_roles.py -v
      (pytest 없으면) python test/test_test2_roles.py
"""
import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eval.paired as paired  # noqa: E402
import eval.score as score  # noqa: E402
from eval.test2_roles import analysis_set, check_files, current_analysis_set, problems, read_roles  # noqa: E402

GOLD_SRC = {"KR-TM-001": "KR-HANIL-001", "KR-TM-002": "KR-KUMHO-001", "KR-TO-001": "KR-HANIL-002",
            "KR-TX-001": "KR-KUMHO-002"}   # 가짜 test2 문서 → 정답 내용을 빌려 올 train 문서


def split_rows():
    meta = {"KR-TM-001": ("현행", "TM"), "KR-TM-002": ("수입품 국문판", "TM2"), "KR-TO-001": ("구서식", "TO"),
            "KR-TX-001": ("현행", "TX")}
    return [{"doc_id": d, "split": "test2", "lang": "ko", "form": f, "manufacturer": g, "split_group": g}
            for d, (f, g) in meta.items()]


def roles(**over):
    r = {"KR-TM-001": ("main", ""), "KR-TM-002": ("main", ""), "KR-TO-001": ("oldform", ""),
         "KR-TX-001": ("exposed", "개발 세션에 정답 유입(테스트)")}
    r.update(over)
    return {d: {"role": role, "note": note} for d, (role, note) in r.items()}


def sandbox():
    """임시 정답 · 출력 폴더. KR-TM-002는 출력 없음, KR-TX-001은 깨진 JSON"""
    t = Path(tempfile.mkdtemp())
    gold, out = t / "gold", t / "outputs" / "cond" / "test2"
    gold.mkdir(parents=True)
    out.mkdir(parents=True)
    for d, src in GOLD_SRC.items():
        shutil.copy(Path(ROOT) / "data" / "labels" / f"{src}.json", gold / f"{d}.json")
    rec = {"gen_time_sec": 1.0, "input_tokens": 10, "output_tokens": 10}
    for d in ("KR-TM-001", "KR-TO-001"):
        body = (gold / f"{d}.json").read_text(encoding="utf-8")
        (out / f"{d}.json").write_text(json.dumps({**rec, "raw_output": body}, ensure_ascii=False), encoding="utf-8")
    (out / "KR-TX-001.json").write_text(json.dumps({**rec, "raw_output": '{"product_name": '}), encoding="utf-8")
    return t, gold, out


def test_01_role_list_rules():
    rows = split_rows()
    assert problems(rows, roles()) == ([], [])
    missing = roles()
    del missing["KR-TO-001"]
    assert any("KR-TO-001: 역할이 없음" in e for e in problems(rows, missing)[0])
    extra = {**roles(), "KR-ZZ-001": {"role": "main", "note": ""}}
    assert any("KR-ZZ-001는 splits.csv의 test2가 아님" in e for e in problems(rows, extra)[0])
    assert any("주 분석 대상은 국문" in e for e in problems(rows, roles(**{"KR-TO-001": ("main", "")}))[0])
    assert any("note에 경로" in e for e in problems(rows, roles(**{"KR-TX-001": ("exposed", "")}))[0])
    pend = roles(**{"KR-TM-002": ("pending", "점검 대기(테스트)")})
    assert problems(rows, pend)[0] == [], "수집 중에는 점검 대기 허용"
    assert any("영향 점검 대기가 남음" in e for e in problems(rows, pend, final=True)[0])


def test_02_main_in_affected_group_warns():
    rows = split_rows()
    rows[3]["split_group"] = "TM"       # 노출 문서가 주 분석 문서와 같은 그룹
    err, warn = problems(rows, roles())
    assert not err and any("KR-TM-001" in w and "영향받은 그룹" in w for w in warn), warn


def test_03_score_uses_role_list_and_keeps_failures_in_denominator():
    t, gold, out = sandbox()
    splits = {r["doc_id"]: r for r in split_rows()}
    ids = sorted(splits)
    subset_of = score.subset_plan("test2", ids, splits, roles())
    accs, _, details = score.score_docs(ids, subset_of, splits, gold, out)
    assert sorted(accs) == ["exposed", "main", "oldform"], "test2는 언어(ko)로 합치지 않는다"
    m = accs["main"]
    assert (m.n, m.missing, m.parsed, m.exact_ext) == (2, 1, 1, 1), (m.n, m.missing, m.parsed, m.exact_ext)
    assert details["KR-TM-002"]["parse_error"] == "출력 파일 없음"
    assert (accs["exposed"].n, accs["exposed"].parsed) == (1, 0)
    assert accs["oldform"].n == 1
    shutil.rmtree(t)


def test_04_score_refuses_pending_or_mismatched_list():
    splits = {r["doc_id"]: r for r in split_rows()}
    for bad in (roles(**{"KR-TM-002": ("pending", "점검 대기(테스트)")}),
                {d: v for d, v in roles().items() if d != "KR-TX-001"}):
        try:
            score.subset_plan("test2", sorted(splits), splits, bad)
        except ValueError:
            continue
        raise AssertionError(f"거부해야 함: {bad}")


def test_05_paired_uses_same_list_and_denominator():
    t, gold, out = sandbox()
    splits = {r["doc_id"]: r for r in split_rows()}
    ids = sorted(splits)
    secs = paired.sections_for("test2", ids, splits, roles())
    titles = [s for s, _ in secs]
    assert titles[0].startswith("주 분석 대상") and "전체" not in titles, titles
    assert secs[0][1] == ["KR-TM-001", "KR-TM-002"], secs[0]
    assert any(s.startswith("주 분석 대상 · 서식") for s in titles) and any(s.startswith("구서식") for s in titles)
    # 채점기와 같은 목록
    subset_of = score.subset_plan("test2", ids, splits, roles())
    assert secs[0][1] == sorted(d for d, r in subset_of.items() if r == "main")
    # 출력이 없는 문서도 실패로 들어간다
    old = paired.GOLD_DIRS, paired.OUTPUT_ROOT
    paired.GOLD_DIRS, paired.OUTPUT_ROOT = {"test2": gold}, t / "outputs"
    try:
        rows = paired.per_doc("cond", "test2", secs[0][1])
    finally:
        paired.GOLD_DIRS, paired.OUTPUT_ROOT = old
    assert len(rows) == 2 and rows["KR-TM-001"]["ext"] and not rows["KR-TM-002"]["ext"], rows
    shutil.rmtree(t)


def write_roles(t, lines):
    p = t / "roles.csv"
    p.write_text("doc_id,role,note\n" + "".join(l + "\n" for l in lines), encoding="utf-8")
    return p


def test_07_duplicate_doc_id_rejected_even_with_same_role():
    """중복 줄이 조용히 덮어써져(exposed 뒤 main → main만 남음) 검사를 통과하던 문제"""
    t = Path(tempfile.mkdtemp())
    base = ["KR-TM-001,main,", "KR-TM-002,main,", "KR-TO-001,oldform,"]
    for dup in (["KR-TX-001,exposed,유입", "KR-TX-001,main,"], ["KR-TX-001,exposed,유입", "KR-TX-001,exposed,유입"]):
        p = write_roles(t, base + dup)
        try:
            read_roles(p)
            raise AssertionError(f"중복을 거부해야 함: {dup}")
        except ValueError as e:
            assert "KR-TX-001" in str(e) and "중복" in str(e), e
        sp = t / "splits.csv"
        with open(sp, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(split_rows()[0]))
            w.writeheader()
            w.writerows(split_rows())
        errs, _ = check_files(sp, p)
        assert errs and "중복" in errs[0], errs
        aset, probs = current_analysis_set(sp, p)
        assert aset == [] and probs, (aset, probs)
    shutil.rmtree(t)


def test_08_analysis_set_has_role_form_group():
    rows = split_rows()
    aset = analysis_set(rows, roles())
    assert [r[0] for r in aset] == sorted(r["doc_id"] for r in rows)
    assert ["KR-TX-001", "exposed", "ko", "현행", "TX"] in aset
    moved = analysis_set(rows, roles(**{"KR-TM-002": ("exposed", "사후 변경(테스트)")}))
    assert moved != aset                                     # 역할만 바꿔도 목록이 달라진다(고정 뒤 거부 근거)


def test_06_other_splits_unchanged():
    splits = {r["doc_id"]: {**r, "split": "val"} for r in split_rows()}
    ids = sorted(splits)
    assert set(score.subset_plan("val", ids, splits).values()) == {"ko"}
    secs = paired.sections_for("val", ids, splits)
    assert secs[0] == ("전체", ids)


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

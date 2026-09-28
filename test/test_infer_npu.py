"""NPU 트랙 스크립트(eval/infer_npu.py · eval/npu_compare.py) 테스트 — OpenVINO·GPU 없이 돈다.

모델을 올리지 않는 부분만 본다: 조건 이름·모델 종류 거부, 봉인 split 거부, 변환 기록 요구, 7절 판정 규칙.

실행: python test/test_infer_npu.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eval.infer_npu as infer_npu  # noqa: E402
import eval.npu_compare as npu_compare  # noqa: E402

QLORA = {"source": {"kind": "qlora_merged"}}
BASE = {"source": {"kind": "base"}}


def rejects(fn, *a):
    try:
        fn(*a)
    except SystemExit:
        return True
    return False


def test_01_gpu_condition_names_rejected():
    """GPU 출력 폴더(qlora_r1 등)에 NPU 출력이 섞이지 않는다"""
    for name in ("qlora_r1", "qlora_final", "base_zs", "base_fs"):
        assert rejects(infer_npu.check_condition, name, QLORA if name.startswith("qlora") else BASE), name


def test_02_condition_name_format():
    assert not rejects(infer_npu.check_condition, "qlora_r1_npu_int4cw", QLORA)
    assert not rejects(infer_npu.check_condition, "qlora_r1_ov_cpu_int8", QLORA)
    assert not rejects(infer_npu.check_condition, "base_zs_npu_int4cw", BASE)
    for bad in ("qlora_r1_int4cw", "npu_int4cw", "qlora_r1-npu-int4", "Qlora_r1_npu_x"):
        assert rejects(infer_npu.check_condition, bad, QLORA), bad


def test_03_model_kind_must_match_condition():
    """QLoRA 조건에 Base 모델, Base 조건에 병합 모델을 넣으면 거부"""
    assert rejects(infer_npu.check_condition, "qlora_r1_npu_int4cw", BASE)
    assert rejects(infer_npu.check_condition, "base_zs_npu_int4cw", QLORA)


def test_04_sealed_splits_rejected_by_cli():
    """test · test2 · val_en · train은 argparse 단계에서 거부(모델을 올리기 전)"""
    for split in ("test", "test2", "val_en", "train"):
        r = subprocess.run([sys.executable, "eval/infer_npu.py", "--model", "x/ov_int8", "--device", "CPU",
                            "--condition", "qlora_r1_ov_cpu_int8", "--split", split],
                           cwd=ROOT, capture_output=True, text=True)
        assert r.returncode != 0 and "invalid choice" in r.stderr, split


def test_05_manifest_required():
    with tempfile.TemporaryDirectory() as d:
        ir = Path(d) / "ov_int4cw"
        ir.mkdir()
        assert rejects(infer_npu.read_manifest, ir)
        (Path(d) / "export_int4cw.json").write_text(json.dumps({"source": {"kind": "base"}}), encoding="utf-8")
        assert infer_npu.read_manifest(ir)["source"]["kind"] == "base"


REF = {"parse_rate": 1.0, "schema_rate": 0.875, "fab_any_docs": 0, "ghs_f1": 1.0, "pair_f1": 0.96,
       "doc_exact_ext_rate": 0.5}


def test_06_verdict_keep():
    """형식 유지 + 핵심 지표 하락이 문서 1건(1/8) 이내면 유지"""
    cand = dict(REF, doc_exact_ext_rate=0.375)
    assert npu_compare.verdict(REF, cand, 8) == "유지"


def test_07_verdict_partial():
    cand = dict(REF, doc_exact_ext_rate=0.25)
    assert npu_compare.verdict(REF, cand, 8).startswith("부분 유지")


def test_08_verdict_fail():
    """파싱률·스키마 하락 또는 무근거 생성 1건이면 미달"""
    assert npu_compare.verdict(REF, dict(REF, schema_rate=0.75), 8) == "미달"
    assert npu_compare.verdict(REF, dict(REF, parse_rate=0.875), 8) == "미달"
    assert npu_compare.verdict(REF, dict(REF, fab_any_docs=1), 8) == "미달"


def test_09_judge_needs_same_docs():
    assert npu_compare.judge(REF, REF, 8, ["KR-GSC-003"]).startswith("판정 불가")
    assert npu_compare.judge({}, REF, 8, []).startswith("판정 불가")


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

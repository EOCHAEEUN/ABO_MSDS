"""평가 게이트(eval/gate.py) · 실험 고정(eval/experiment.py) 테스트.

실제 저장소는 건드리지 않는다: 임시 폴더에 git 저장소와 가짜 실험 정의·코드·어댑터·few-shot을 만들고
두 모듈의 경로를 그쪽으로 돌린다. 봉인 대조는 test/test_seal.py가 따로 보므로 여기서는 통과로 둔다.

실행: python test/test_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eval.experiment as experiment  # noqa: E402
import eval.gate as gate  # noqa: E402

DOCS = ["KR-NEWA-001", "KR-NEWB-001"]
EXP = {
    "common": {"base_model": "Base/M", "max_new_tokens": 1200, "decoding": "greedy", "enable_thinking": False,
               "generation_files": ["core/prompt.py", "gen.py"], "scoring_files": ["score.py"], "packages": ["pip"]},
    "conditions": {"base_zs": {"fewshot": False, "adapter": None}, "base_fs": {"fewshot": True, "adapter": None},
                   "qlora_final": {"fewshot": False, "adapter": "runs/a/adapter"}},
    "frozen": None,
}


def git(t, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=t, check=True, capture_output=True)


def sandbox(frozen=True):
    t = Path(tempfile.mkdtemp())
    files = {"core/prompt.py": "P = 1\n", "gen.py": "G = 1\n", "score.py": "S = 1\n",
             "eval/fewshot.json": json.dumps({"fewshot_doc_ids": ["KR-FS-001"]}),
             "data/text/KR-FS-001.txt": "fs text", "data/labels/KR-FS-001.json": "{}",
             "runs/a/adapter/adapter_model.safetensors": "w", "runs/a/adapter/adapter_config.json": "{}",
             "eval/experiment.json": json.dumps(EXP, ensure_ascii=False, indent=2)}
    for rel, body in files.items():
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / rel).write_text(body, encoding="utf-8")
    git(t, "init", "-q")
    git(t, "add", ".")
    git(t, "commit", "-qm", "init")
    for name, rel in (("EXPERIMENT_JSON", "eval/experiment.json"), ("FEWSHOT_JSON", "eval/fewshot.json"),
                      ("TEXT_DIR", "data/text"), ("LABEL_DIR", "data/labels")):
        setattr(experiment, name, t / rel)
    experiment.ROOT = t
    experiment.model_revision = lambda base: "rev1"
    gate.ROOT, gate.OUTPUT_ROOT = t, t / "outputs"
    gate.verify_seal = lambda split: (True, "봉인 대조 통과(테스트)")
    if frozen:
        experiment.freeze()
        git(t, "commit", "-qam", "freeze")
    return t


def rec_for(t, condition="base_zs", split="test2", max_new=1200, adapter=None, fewshot=()):
    return gate.run_record(condition, split, "Base/M", str(t / adapter) if adapter else None, list(fewshot), max_new)


def outputs(t, condition, split, rec, docs=DOCS):
    d = t / "outputs" / condition / split
    gate.check_resume(d, rec, DOCS, overwrite=False, partial=False)
    for doc in docs:
        (d / f"{doc}.json").write_text("{}", encoding="utf-8")


def exits(fn, *a, **k):
    try:
        fn(*a, **k)
    except SystemExit as e:
        return str(e.code)
    return None


# ---------------------------------------------------------------- 재개 대조 (모든 split)
def test_01_resume_with_other_adapter_refused():
    """같은 조건 이름으로 어댑터를 바꿔 이어 돌리면 한 폴더에 두 모델 출력이 섞이던 문제"""
    t = sandbox(frozen=False)
    (t / "runs/b/adapter").mkdir(parents=True)
    for f in ("adapter_model.safetensors", "adapter_config.json"):
        (t / "runs/b/adapter" / f).write_text("other", encoding="utf-8")
    d = t / "outputs/qlora_final/val"
    gate.check_resume(d, rec_for(t, "qlora_final", "val", adapter="runs/a/adapter"), DOCS, False, False)
    msg = exits(gate.check_resume, d, rec_for(t, "qlora_final", "val", adapter="runs/b/adapter"), DOCS, False, False)
    assert msg and "설정이 다름" in msg and "adapter" in msg, msg


def test_02_resume_same_config_ok_but_partial_overwrite_refused():
    t = sandbox(frozen=False)
    d = t / "outputs/base_zs/val"
    gate.check_resume(d, rec_for(t, split="val"), DOCS, False, False)
    assert exits(gate.check_resume, d, rec_for(t, split="val"), DOCS, False, False) is None
    msg = exits(gate.check_resume, d, rec_for(t, split="val", max_new=900), DOCS, True, True)
    assert msg and "일부 문서만" in msg, msg


# ---------------------------------------------------------------- 실험 고정
def test_03_freeze_refused_with_uncommitted_file():
    t = sandbox(frozen=False)
    (t / "gen.py").write_text("G = 2\n", encoding="utf-8")
    msg = exits(experiment.freeze)
    assert msg and "커밋되지 않은" in msg, msg


def test_04_check_fails_until_experiment_json_committed():
    t = sandbox(frozen=False)
    experiment.freeze()
    ok, problems, _ = experiment.check("generate")
    assert not ok and any("experiment.json이 커밋되지 않음" in p for p in problems), problems
    git(t, "commit", "-qam", "freeze")
    ok, problems, _ = experiment.check("generate")
    assert ok, problems


# ---------------------------------------------------------------- 출력 생성 게이트
def test_05_generate_requires_frozen_experiment():
    t = sandbox(frozen=False)
    msg = exits(gate.gate_generate, "test2", "base_zs", rec_for(t), True, False, None)
    assert msg and "고정되지 않음" in msg, msg


def test_06_generate_rules():
    t = sandbox()
    assert exits(gate.gate_generate, "test2", "base_zs", rec_for(t), True, False, None) is None
    assert "--allow-test" in exits(gate.gate_generate, "test2", "base_zs", rec_for(t), False, False, None)
    assert "만 돌린다" in exits(gate.gate_generate, "test2", "qlora_c2", rec_for(t, "qlora_c2"), True, False, None)
    assert "max_new_tokens" in exits(gate.gate_generate, "test2", "base_zs", rec_for(t, max_new=1024), True, False, None)
    assert "--limit" in exits(gate.gate_generate, "test2", "base_zs", rec_for(t), True, False, 3)
    ok_fs = rec_for(t, "base_fs", fewshot=["KR-FS-001"])
    assert exits(gate.gate_generate, "test2", "base_fs", ok_fs, True, False, None) is None
    ok_q = rec_for(t, "qlora_final", adapter="runs/a/adapter")
    assert exits(gate.gate_generate, "test2", "qlora_final", ok_q, True, False, None) is None


def test_07_generation_file_changed_after_freeze_refused():
    t = sandbox()
    (t / "core/prompt.py").write_text("P = 2\n", encoding="utf-8")
    git(t, "commit", "-qam", "prompt change")
    msg = exits(gate.gate_generate, "test2", "base_zs", rec_for(t), True, False, None)
    assert msg and "generation_sha256" in msg, msg


def test_08_fewshot_changed_after_freeze_refused():
    t = sandbox()
    (t / "data/labels/KR-FS-001.json").write_text('{"x": 1}', encoding="utf-8")
    git(t, "commit", "-qam", "fewshot label change")
    msg = exits(gate.gate_generate, "test2", "base_fs", rec_for(t, "base_fs", fewshot=["KR-FS-001"]), True, False, None)
    assert msg and "conditions" in msg, msg


# ---------------------------------------------------------------- 채점 게이트
def test_09_score_refused_before_inference_complete():
    t = sandbox()
    assert "실행 기록 없음" in exits(gate.gate_score, "test2", ["base_zs"], True, DOCS)
    outputs(t, "base_zs", "test2", rec_for(t), docs=DOCS[:1])
    assert "추론이 끝나지 않음" in exits(gate.gate_score, "test2", ["base_zs"], True, DOCS)


def test_10_score_rules_and_pass():
    t = sandbox()
    outputs(t, "base_zs", "test2", rec_for(t))
    assert "--allow-test" in exits(gate.gate_score, "test2", ["base_zs"], False, DOCS)
    assert "비교군이 아님" in exits(gate.gate_score, "test2", ["qlora_c2"], True, DOCS)
    assert gate.gate_score("test2", ["base_zs"], True, DOCS) == ""
    assert gate.gate_score("val", ["anything"], False, DOCS) == ""      # 봉인 평가셋이 아니면 검사 없음


def test_11_output_made_with_other_setting_refused():
    """게이트 밖에서(다른 생성 길이로) 만든 출력은 채점하지 않는다"""
    t = sandbox()
    outputs(t, "base_zs", "test2", rec_for(t, max_new=900))
    msg = exits(gate.gate_score, "test2", ["base_zs"], True, DOCS)
    assert msg and "고정된 정의와 다른 설정" in msg, msg


def test_12_rescoring_after_scorer_change_is_tagged():
    t = sandbox()
    outputs(t, "base_zs", "test2", rec_for(t))
    (t / "score.py").write_text("S = 2\n", encoding="utf-8")
    assert "커밋되지 않은 채점 파일" in exits(gate.gate_score, "test2", ["base_zs"], True, DOCS)
    git(t, "commit", "-qam", "scorer change")
    tag = gate.gate_score("test2", ["base_zs"], True, DOCS)
    assert tag.startswith("[채점기변경-"), tag


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
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {name}  {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)

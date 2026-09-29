"""
[양세윤] 추론 스크립트 회귀 테스트 — GPU 없이 모델 로딩·생성을 가짜로 바꿔 입출력 규약만 본다.
입력은 test/fixtures/(옛 라벨, 코드 테스트 전용).

  python3 test/test_infer.py -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import LEGACY_V1_FILE_SHA256  # noqa: E402
from eval import infer  # noqa: E402

FIX = ROOT / "test" / "fixtures"
VAL_IDS = ["KR-HANIL-001", "KR-HENKEL-001"]  # fixtures/splits.csv의 val


def fake_generate(tok, model, messages, max_new_tokens):
    """마지막 user 메시지 길이만 보고 정해진 문자열을 낸다. few-shot이면 메시지가 5개(system + 2쌍 + user)."""
    return f"not json ({len(messages)} msgs)", 0.5, 123, 7


def write_run_config(run_dir, version):
    """train_qlora.py가 run 폴더에 남기는 config.json 중 프롬프트 기록 부분"""
    aug = {"prompt": {"version": version, "text_sha256": infer.prompt_sha256(version)}}
    (Path(run_dir) / "config.json").write_text(json.dumps({"augmentation": aug}), encoding="utf-8")


class InferTest(unittest.TestCase):
    def run_infer(self, out, *extra, text_dir=FIX / "text"):
        argv = ["--condition", "base_zs", "--split", "val", "--splits", str(FIX / "splits.csv"),
                "--text-dir", str(text_dir), "--out-root", str(out), "--base", "dummy", "--revision", "rev-x", *extra]
        with mock.patch.object(infer, "load_model", return_value=(None, None)), \
             mock.patch.object(infer, "verify_commit", return_value="rev-x"), \
             mock.patch.object(infer, "generate", side_effect=fake_generate):
            infer.main(argv)

    def test_writes_raw_output_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_infer(tmp)
            d = Path(tmp) / "base_zs" / "val"
            self.assertEqual(sorted(p.stem for p in d.glob("*.json")), VAL_IDS)
            # {doc_id}.json에는 모델 출력 원문만(파싱 실패도 그대로)
            self.assertEqual((d / f"{VAL_IDS[0]}.json").read_text(encoding="utf-8"), "not json (2 msgs)")
            log = [json.loads(line) for line in (d / "_log.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["doc_id"] for r in log], VAL_IDS)
            self.assertEqual((log[0]["input_tokens"], log[0]["output_tokens"]), (123, 7))
            self.assertEqual(log[0]["base_commit"], "rev-x")        # 확인한 실제 스냅샷
            run = json.loads((d / "_run.jsonl").read_text(encoding="utf-8"))
            self.assertEqual((run["condition"], run["max_new_tokens"]), ("base_zs", infer.DEFAULT_MAX_NEW_TOKENS))

    def test_resume_skips_done_and_refuses_changed_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_infer(tmp, "--limit", "1")
            self.run_infer(tmp)  # 나머지 1건만 생성
            d = Path(tmp) / "base_zs" / "val"
            self.assertEqual(len((d / "_log.jsonl").read_text(encoding="utf-8").splitlines()), 2)
            with self.assertRaises(SystemExit) as cm:
                self.run_infer(tmp, "--max-new-tokens", str(infer.DEFAULT_MAX_NEW_TOKENS + 1000), "--overwrite")
            self.assertIn("설정이 다름", str(cm.exception))

    def test_not_found_is_logged_not_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            text_dir = Path(tmp) / "text"
            text_dir.mkdir()
            (text_dir / f"{VAL_IDS[0]}.txt").write_text((FIX / "text" / f"{VAL_IDS[0]}.txt").read_text(encoding="utf-8"),
                                                        encoding="utf-8")
            (text_dir / "_cut_log.csv").write_text(f"doc_id,status\n{VAL_IDS[1]},NOT_FOUND\n", encoding="utf-8")
            self.run_infer(Path(tmp) / "out", text_dir=text_dir)
            d = Path(tmp) / "out" / "base_zs" / "val"
            self.assertFalse((d / f"{VAL_IDS[1]}.json").exists())
            log = {r["doc_id"]: r for r in map(json.loads, (d / "_log.jsonl").read_text(encoding="utf-8").splitlines())}
            self.assertEqual(log[VAL_IDS[1]]["skipped"], "NOT_FOUND")

    def test_resume_refuses_changed_input(self):
        """이어 돌릴 때 입력 텍스트가 바뀌었으면 거부(기존 출력과 새 출력이 다른 입력으로 섞이지 않게)"""
        with tempfile.TemporaryDirectory() as tmp:
            text_dir = Path(tmp) / "text"
            text_dir.mkdir()
            for d in VAL_IDS:
                (text_dir / f"{d}.txt").write_text((FIX / "text" / f"{d}.txt").read_text(encoding="utf-8"), encoding="utf-8")
            self.run_infer(Path(tmp) / "out", "--limit", "1", text_dir=text_dir)
            (text_dir / f"{VAL_IDS[1]}.txt").write_text("바뀐 텍스트", encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                self.run_infer(Path(tmp) / "out", text_dir=text_dir)
            self.assertIn("inputs_sha256", str(cm.exception))
            # cut_log 상태만 바뀌어도 거부
            (text_dir / f"{VAL_IDS[1]}.txt").write_text((FIX / "text" / f"{VAL_IDS[1]}.txt").read_text(encoding="utf-8"),
                                                        encoding="utf-8")
            (text_dir / "_cut_log.csv").write_text(f"doc_id,status\n{VAL_IDS[1]},NOT_FOUND\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                self.run_infer(Path(tmp) / "out", text_dir=text_dir)
            self.assertIn("inputs_sha256", str(cm.exception))

    def test_default_base_is_r1_model_and_revision(self):
        """--base가 없으면 학습과 같은 r1.yaml의 model · model_revision으로 불러오고 _run.jsonl에 남긴다"""
        import yaml
        cfg = yaml.safe_load(infer.DEFAULT_CONFIG.read_text(encoding="utf-8"))
        self.assertTrue(cfg.get("model_revision"))
        with tempfile.TemporaryDirectory() as tmp:
            argv = ["--condition", "base_zs", "--split", "val", "--splits", str(FIX / "splits.csv"),
                    "--text-dir", str(FIX / "text"), "--out-root", tmp]
            with mock.patch.object(infer, "load_model", return_value=(None, None)) as lm, \
                 mock.patch.object(infer, "verify_commit", return_value=cfg["model_revision"]), \
                 mock.patch.object(infer, "generate", side_effect=fake_generate):
                infer.main(argv)
            self.assertEqual(lm.call_args.args, (cfg["model"], None, cfg["model_revision"]))
            run = json.loads((Path(tmp) / "base_zs" / "val" / "_run.jsonl").read_text(encoding="utf-8"))
            self.assertEqual((run["base_model"], run["base_revision"]), (cfg["model"], cfg["model_revision"]))
            self.assertEqual(run["n_docs"], len(VAL_IDS))

    def test_verify_commit(self):
        def model(commit):
            cfg = type("Cfg", (), {"_commit_hash": commit})()
            return type("Model", (), {"config": cfg})()

        self.assertEqual(infer.verify_commit(model("aaa"), "aaa"), "aaa")
        for m, rev, msg in ((model("aaa"), "bbb", "다르다"), (model(None), "aaa", "확인할 수 없다")):
            with self.subTest(msg=msg), self.assertRaises(SystemExit) as cm:
                infer.verify_commit(m, rev)
            self.assertIn(msg, str(cm.exception))

    def test_base_without_revision_refused(self):
        with self.assertRaises(SystemExit) as cm:
            infer.main(["--condition", "base_zs", "--split", "val", "--splits", str(FIX / "splits.csv"),
                        "--text-dir", str(FIX / "text"), "--out-root", "/tmp/unused", "--base", "dummy"])
        self.assertIn("리비전이 없다", str(cm.exception))

    def test_refusals(self):
        cases = [
            (["--condition", "base_zs", "--split", "test"], "--allow-test"),
            (["--condition", "base_zs", "--split", "test", "--allow-test"], "experiment.json"),
            (["--condition", "qlora_r1", "--split", "val"], "--adapter"),
            (["--condition", "base_zs", "--split", "val", "--adapter", "x"], "베이스 모델 조건"),
        ]
        for argv, msg in cases:
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as cm:
                infer.main(argv)
            self.assertIn(msg, str(cm.exception))

    def test_test_split_gates(self):
        """test: 저장소 밖 --out-root, 비교군 3개, experiment.json의 max_new_tokens · adapter_sha256과 대조"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            adapter = tmp / "adapter"
            adapter.mkdir()
            (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
            write_run_config(tmp, "v1")
            other = tmp / "other_adapter"
            other.mkdir()
            (other / "adapter_config.json").write_text('{"r": 8}', encoding="utf-8")
            exp = tmp / "experiment.json"
            exp.write_text(json.dumps({"max_new_tokens": 1300, "adapter": "runs/x/adapter",
                                       "adapter_sha256": infer.sha256_dir(adapter), "prompt_version": "v1"}),
                           encoding="utf-8")
            text_dir = tmp / "text"  # test 텍스트는 저장소 밖이어야 하므로 fixture를 복사
            text_dir.mkdir()
            for d in VAL_IDS:
                (text_dir / f"{d}.txt").write_text((FIX / "text" / f"{d}.txt").read_text(encoding="utf-8"),
                                                   encoding="utf-8")
            base = ["--split", "test", "--allow-test", "--text-dir", str(text_dir), "--base", "dummy", "--revision", "rev-x"]
            out = ["--out-root", str(tmp / "out")]
            cases = [
                (["--condition", "base_zs", *base], "--out-root"),  # 기본 outputs/(저장소 안)
                (["--condition", "base_zs", *base, "--out-root", str(ROOT / "outputs")], "--out-root"),
                (["--condition", "qlora_r1", *base, *out, "--adapter", str(adapter)], "비교군"),
                (["--condition", "base_zs", *base, *out, "--max-new-tokens", "2048"], "experiment.json의 1300"),
                (["--condition", "qlora_final", *base, *out, "--adapter", str(other)], "adapter_sha256"),
                (["--condition", "base_zs", *base, *out, "--prompt", "v2"], "prompt_version v1"),
            ]
            with mock.patch.object(infer, "EXPERIMENT_JSON", exp):
                for argv, msg in cases:
                    with self.subTest(argv=argv), self.assertRaises(SystemExit) as cm:
                        infer.main(argv)
                    self.assertIn(msg, str(cm.exception))
                # 고정값과 같으면 돈다: 저장소 밖 출력, 생성 길이는 experiment.json 값
                with mock.patch.object(infer, "load_model", return_value=(None, None)), \
                     mock.patch.object(infer, "verify_commit", return_value="rev-x"), \
                     mock.patch.object(infer, "generate", side_effect=fake_generate):
                    infer.main(["--condition", "qlora_final", *base, *out, "--adapter", str(adapter),
                                "--max-new-tokens", "1300"])
            run = json.loads((tmp / "out" / "qlora_final" / "test" / "_run.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(run["max_new_tokens"], 1300)


class PromptVersionTest(unittest.TestCase):
    """v2 출력은 prompt_v2/ 아래에만 쌓이고, v1 폴더를 덮어쓰거나 섞지 않는다."""

    def run_infer(self, out, *extra):
        InferTest.run_infer(self, out, *extra)

    def test_v2_goes_to_own_folder_and_leaves_v1_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_infer(tmp)
            v1 = Path(tmp) / "base_zs" / "val"
            before = {p.name: p.read_bytes() for p in v1.iterdir()}
            self.run_infer(tmp, "--prompt", "v2", "--overwrite")
            v2 = Path(tmp) / "prompt_v2" / "base_zs" / "val"
            self.assertEqual(sorted(p.stem for p in v2.glob("*.json")), VAL_IDS)
            self.assertEqual({p.name: p.read_bytes() for p in v1.iterdir()}, before)
            run = json.loads((v2 / "_run.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(run["prompt_version"], "v2")
            self.assertEqual(run["prompt_text_sha256"], infer.prompt_sha256("v2"))

    def test_v2_1_goes_to_own_folder_and_leaves_v2_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_infer(tmp, "--prompt", "v2")
            v2 = Path(tmp) / "prompt_v2" / "base_zs" / "val"
            before = {p.name: p.read_bytes() for p in v2.iterdir()}
            self.run_infer(tmp, "--prompt", "v2_1")
            self.assertEqual({p.name: p.read_bytes() for p in v2.iterdir()}, before)
            run = json.loads((Path(tmp) / "prompt_v2_1" / "base_zs" / "val" / "_run.jsonl").read_text(encoding="utf-8"))
            self.assertEqual((run["prompt_version"], run["prompt_text_sha256"]), ("v2_1", infer.prompt_sha256("v2_1")))

    def test_edited_prompt_text_refused_in_same_folder(self):
        """같은 버전 이름의 문구를 고친 뒤 기존 폴더로 돌리면 --overwrite여도 거부(새 버전으로 돌려야 함)"""
        with tempfile.TemporaryDirectory() as tmp:
            self.run_infer(tmp, "--prompt", "v2", "--limit", "1")
            edited = {**infer.PROMPTS, "v2": infer.PROMPTS["v2"] + "\n15. 고친 규칙"}
            with mock.patch.dict("core.prompt.PROMPTS", edited), self.assertRaises(SystemExit) as cm:
                self.run_infer(tmp, "--prompt", "v2", "--overwrite")
            self.assertIn("문구가 바뀌었다", str(cm.exception))

    def test_version_mismatch_refused_even_with_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_infer(tmp, "--prompt", "v2")
            with self.assertRaises(SystemExit) as cm:  # --out-root를 v2 폴더 위로 잡아 v1로 덮어쓰려 해도
                self.run_infer(Path(tmp) / "prompt_v2", "--overwrite")
            self.assertIn("프롬프트 v2의 결과 폴더", str(cm.exception))

    def test_legacy_v1_record_resumes_as_v1_and_refuses_v2(self):
        """09-29 이전 _run.jsonl(파일 해시만 있음) = main의 v1 결과. v1로는 이어 돌고, v2 설정은 거부."""
        with tempfile.TemporaryDirectory() as tmp:
            self.run_infer(tmp, "--limit", "1")
            run_path = Path(tmp) / "base_zs" / "val" / "_run.jsonl"
            current = json.loads(run_path.read_text(encoding="utf-8"))
            legacy = {k: v for k, v in current.items() if k not in ("prompt_version", "prompt_text_sha256")}
            legacy["prompt_sha256"] = LEGACY_V1_FILE_SHA256
            run_path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
            self.run_infer(tmp)  # v1로 나머지 1건
            self.assertEqual(len(list(run_path.parent.glob("*.json"))), 2)
            current.pop("created_at")
            with self.assertRaises(SystemExit) as cm:
                infer.check_resume(run_path.parent, {**current, "prompt_version": "v2",
                                                     "prompt_text_sha256": infer.prompt_sha256("v2")})
            self.assertIn("프롬프트 v1의 결과 폴더", str(cm.exception))
    def test_adapter_must_match_trained_prompt(self):
        """어댑터를 학습한 프롬프트 버전과 --prompt가 다르면 거부, 확인할 수 없어도 거부"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "runs" / "0929_r2"
            adapter = run_dir / "adapter"
            adapter.mkdir(parents=True)
            (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
            out = Path(tmp) / "out"
            qlora = ["--condition", "qlora_r2", "--adapter", str(adapter)]
            with self.assertRaises(SystemExit) as cm:          # config.json 없음
                self.run_infer(out, *qlora, "--prompt", "v2")
            self.assertIn("확인할 수 없다", str(cm.exception))
            write_run_config(run_dir, "v2")
            with self.assertRaises(SystemExit) as cm:          # v2로 학습한 어댑터를 v1으로
                self.run_infer(out, *qlora)
            self.assertIn("프롬프트 v2로 학습", str(cm.exception))
            self.run_infer(out, *qlora, "--prompt", "v2")      # 같은 버전이면 돈다
            self.assertEqual(len(list((out / "prompt_v2" / "qlora_r2" / "val").glob("*.json"))), len(VAL_IDS))
            # 문구가 바뀐 v2(같은 이름, 다른 해시)도 확인 불가로 거부
            (run_dir / "config.json").write_text(json.dumps({"augmentation": {"prompt": {"version": "v2",
                                                             "text_sha256": "0" * 64}}}), encoding="utf-8")
            self.assertIsNone(infer.adapter_prompt_version(adapter))
            # 09-29 이전 학습(r1): 버전 기록 없이 core/prompt.py 파일 해시만 → v1
            (run_dir / "config.json").write_text(json.dumps({"augmentation": {"code_sha256": {
                "core/prompt.py": LEGACY_V1_FILE_SHA256}}}), encoding="utf-8")
            self.assertEqual(infer.adapter_prompt_version(adapter), "v1")

    def test_r1_record_is_v1(self):
        r1 = ROOT / "runs" / "0928_r1"
        if not (r1 / "config.json").exists():
            self.skipTest("runs/0928_r1/config.json 없음")
        self.assertEqual(infer.adapter_prompt_version(r1 / "adapter"), "v1")


if __name__ == "__main__":
    unittest.main()

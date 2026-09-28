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

from eval import infer  # noqa: E402

FIX = ROOT / "test" / "fixtures"
VAL_IDS = ["KR-HANIL-001", "KR-HENKEL-001"]  # fixtures/splits.csv의 val


def fake_generate(tok, model, messages, max_new_tokens):
    """마지막 user 메시지 길이만 보고 정해진 문자열을 낸다. few-shot이면 메시지가 5개(system + 2쌍 + user)."""
    return f"not json ({len(messages)} msgs)", 0.5, 123, 7


class InferTest(unittest.TestCase):
    def run_infer(self, out, *extra, text_dir=FIX / "text"):
        argv = ["--condition", "base_zs", "--split", "val", "--splits", str(FIX / "splits.csv"),
                "--text-dir", str(text_dir), "--out-root", str(out), "--base", "dummy", *extra]
        with mock.patch.object(infer, "load_model", return_value=(None, None)), \
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
            other = tmp / "other_adapter"
            other.mkdir()
            (other / "adapter_config.json").write_text('{"r": 8}', encoding="utf-8")
            exp = tmp / "experiment.json"
            exp.write_text(json.dumps({"max_new_tokens": 1300, "adapter": "runs/x/adapter",
                                       "adapter_sha256": infer.sha256_dir(adapter)}), encoding="utf-8")
            text_dir = tmp / "text"  # test 텍스트는 저장소 밖이어야 하므로 fixture를 복사
            text_dir.mkdir()
            for d in VAL_IDS:
                (text_dir / f"{d}.txt").write_text((FIX / "text" / f"{d}.txt").read_text(encoding="utf-8"),
                                                   encoding="utf-8")
            base = ["--split", "test", "--allow-test", "--text-dir", str(text_dir), "--base", "dummy"]
            out = ["--out-root", str(tmp / "out")]
            cases = [
                (["--condition", "base_zs", *base], "--out-root"),  # 기본 outputs/(저장소 안)
                (["--condition", "base_zs", *base, "--out-root", str(ROOT / "outputs")], "--out-root"),
                (["--condition", "qlora_r1", *base, *out, "--adapter", str(adapter)], "비교군"),
                (["--condition", "base_zs", *base, *out, "--max-new-tokens", "2048"], "experiment.json의 1300"),
                (["--condition", "qlora_final", *base, *out, "--adapter", str(other)], "adapter_sha256"),
            ]
            with mock.patch.object(infer, "EXPERIMENT_JSON", exp):
                for argv, msg in cases:
                    with self.subTest(argv=argv), self.assertRaises(SystemExit) as cm:
                        infer.main(argv)
                    self.assertIn(msg, str(cm.exception))
                # 고정값과 같으면 돈다: 저장소 밖 출력, 생성 길이는 experiment.json 값
                with mock.patch.object(infer, "load_model", return_value=(None, None)), \
                     mock.patch.object(infer, "generate", side_effect=fake_generate):
                    infer.main(["--condition", "qlora_final", *base, *out, "--adapter", str(adapter),
                                "--max-new-tokens", "1300"])
            run = json.loads((tmp / "out" / "qlora_final" / "test" / "_run.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(run["max_new_tokens"], 1300)


if __name__ == "__main__":
    unittest.main()

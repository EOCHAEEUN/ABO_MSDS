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


if __name__ == "__main__":
    unittest.main()

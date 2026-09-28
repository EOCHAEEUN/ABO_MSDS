"""
[강덕우] 학습 스크립트 회귀 테스트 — GPU 없이 도는 부분(설정 · 데이터 검사 · 토큰화 · 정답 마스킹)만

  python3 test/test_train.py -v     (폴더 이름 test가 표준 라이브러리와 겹쳐 -m unittest test.… 는 안 됨)

토큰화 테스트는 Qwen3 토크나이저가 로컬 캐시에 있어야 한다(없으면 건너뜀).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pipeline.train_qlora as tq  # noqa: E402
from core.prompt import build_messages, format_target  # noqa: E402
from pipeline.guard import GuardError  # noqa: E402

FIX = ROOT / "test" / "fixtures"


def fixture_messages(doc_id="KR-KUMHO-002"):
    text = (FIX / "text" / f"{doc_id}.txt").read_text(encoding="utf-8")
    label = json.loads((FIX / "labels" / f"{doc_id}.json").read_text(encoding="utf-8"))
    return build_messages(text) + [{"role": "assistant", "content": format_target(label)}], label


def tokenizer():
    try:
        from transformers import AutoTokenizer
        cfg = tq.load_config(tq.BASE_CONFIG)
        return AutoTokenizer.from_pretrained(cfg["model"], revision=cfg.get("model_revision"), local_files_only=True)
    except Exception as e:  # 캐시 없음 등
        raise unittest.SkipTest(f"토크나이저 없음: {e}")


class ConfigTest(unittest.TestCase):
    def test_r1_has_plan_values(self):
        cfg = tq.load_config(tq.BASE_CONFIG)
        self.assertEqual(cfg["max_length"], 4096)          # plan 6절
        self.assertTrue(cfg["gradient_checkpointing"])
        self.assertEqual((cfg["lora_r"], cfg["lora_alpha"]), (16, 32))
        self.assertEqual((cfg["per_device_batch_size"], cfg["grad_accum"], cfg["num_epochs"]), (1, 8, 2))
        self.assertIn("max_grad_norm", cfg)                 # 기본값도 config.json에 남는다

    def test_r2_overrides_only_given_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r2.yaml"
            p.write_text("num_epochs: 3\n", encoding="utf-8")
            cfg = tq.load_config(p)
            self.assertEqual(cfg["num_epochs"], 3)
            self.assertEqual(cfg["learning_rate"], tq.load_config(tq.BASE_CONFIG)["learning_rate"])


class DataGuardTest(unittest.TestCase):
    """학습 데이터에 train이 아닌 문서가 섞이면 모델을 불러오기 전에 멈춘다."""

    def setUp(self):
        self.orig = tq.SPLITS_CSV
        tq.SPLITS_CSV = FIX / "splits.csv"                  # fixture 분할표: HANIL-001 · HENKEL-001은 val

    def tearDown(self):
        tq.SPLITS_CSV = self.orig

    def write(self, d, name, doc_ids):
        p = Path(d) / name
        p.write_text("".join(json.dumps({"doc_id": x, "variant": "orig", "messages": []}) + "\n" for x in doc_ids),
                     encoding="utf-8")
        return p

    def test_train_only_passes(self):
        with tempfile.TemporaryDirectory() as d:
            tq.check_data(self.write(d, "train.jsonl", ["KR-NOROO-004", "KR-OCI-005"]), Path(d) / "val.jsonl")

    def test_val_doc_in_train_stops(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(GuardError):
                tq.check_data(self.write(d, "train.jsonl", ["KR-NOROO-004", "KR-HANIL-001"]), Path(d) / "val.jsonl")

    def test_unknown_doc_stops(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(GuardError):
                tq.check_data(self.write(d, "train.jsonl", ["KR-NOPE-001"]), Path(d) / "val.jsonl")

    def test_sealed_path_stops(self):
        with self.assertRaises(GuardError):
            tq.check_data(Path("data/sealed/train.jsonl"), Path("data/val.jsonl"))


class EncodeTest(unittest.TestCase):
    """정답 구간만 학습하고, 프롬프트는 eval/infer.py의 추론 입력과 같아야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.tok = tokenizer()

    def test_prompt_matches_inference_and_only_answer_is_learned(self):
        msgs, label = fixture_messages()
        ids, lab = tq.encode(self.tok, msgs, 4096)
        n_prompt = sum(x == -100 for x in lab)
        # 앞부분 = 추론 때 모델이 받는 프롬프트(eval/infer.py generate와 같은 호출)
        prompt = self.tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True,
                                              **tq.CHAT_TEMPLATE_KWARGS)
        self.assertEqual(self.tok.decode(ids[:n_prompt]), prompt)
        # 뒷부분 = 정답 JSON + <|im_end|>, 여기에만 loss
        self.assertEqual(lab[n_prompt:], ids[n_prompt:])
        answer = self.tok.decode(ids[n_prompt:])
        self.assertTrue(answer.endswith("<|im_end|>"))
        self.assertEqual(json.loads(answer[: -len("<|im_end|>")]), label)
        self.assertNotIn("<think>", answer)                 # enable_thinking=False

    def test_over_max_length_is_excluded_not_truncated(self):
        msgs, _ = fixture_messages()
        n = len(tq.encode(self.tok, msgs, 4096)[0])
        self.assertIsNone(tq.encode(self.tok, msgs, n - 1))
        self.assertIsNotNone(tq.encode(self.tok, msgs, n))


class SmokeNameTest(unittest.TestCase):
    def test_smoke_cannot_use_r1_name(self):
        r = subprocess.run([sys.executable, str(ROOT / "pipeline" / "train_qlora.py"), "--config",
                            str(tq.BASE_CONFIG), "--smoke", "1", "--name", "r1"], capture_output=True, text=True, cwd=ROOT)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("스모크", r.stderr)


class BuildReportTest(unittest.TestCase):
    def test_report_matches_current_train_jsonl(self):
        if not tq.TRAIN_JSONL.exists():
            self.skipTest("data/train.jsonl 없음")
        s = tq.build_report_summary(tq.TRAIN_JSONL)
        self.assertIsNotNone(s)
        self.assertTrue(s["matches_train_jsonl"], "build_report.json이 지금의 train.jsonl로 만든 보고서가 아님")
        self.assertIn("labels_unchanged_since_build", s)


if __name__ == "__main__":
    unittest.main()

"""
[양세윤] 프롬프트 버전 회귀 테스트 — v1 문구가 r1 학습 · main val 결과 때와 같은지, v2가 v1 + 규칙 10~14인지

  python3 test/test_prompt.py -v
"""
import hashlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import prompt as P  # noqa: E402

# r1 학습(data/train.jsonl) · main의 outputs/*/val 결과를 만든 v1 시스템 프롬프트 문구의 해시(2026-09-29 main aeb24e6)
V1_TEXT_SHA256 = "4de0240565cb028469ef412b764f229e36c1802e7d7e1b5be48b26390e38285c"
# outputs/prompt_v2/(val Base 결과, 2026-09-29)를 만든 v2 문구의 해시. 고칠 일이 있으면 새 버전을 추가한다
V2_TEXT_SHA256 = "bedd542c10600353a17afb88f702a26535fde8b2362029ffd9b322afa97d5550"
# outputs/prompt_v2_1/(val Base 결과) · data/prompt_v2_1/(r2 학습셋, 2026-09-29)을 만든 v2_1 문구의 해시. 고칠 일이 있으면 새 버전을 추가한다
V2_1_TEXT_SHA256 = "940de9e65d6d6fcf2b735d62fada1f20f94300d9238098f49fdec3e034e6d66b"


class PromptVersionTest(unittest.TestCase):
    def test_v1_text_unchanged(self):
        self.assertEqual(hashlib.sha256(P.PROMPTS["v1"].encode("utf-8")).hexdigest(), V1_TEXT_SHA256)
        self.assertIs(P.PROMPTS["v1"], P.SYSTEM_PROMPT)

    def test_v2_text_unchanged(self):
        self.assertEqual(hashlib.sha256(P.PROMPTS["v2"].encode("utf-8")).hexdigest(), V2_TEXT_SHA256)

    def test_v2_1_text_unchanged(self):
        self.assertEqual(hashlib.sha256(P.PROMPTS["v2_1"].encode("utf-8")).hexdigest(), V2_1_TEXT_SHA256)

    def test_v2_1_changes_only_rules_12_and_13(self):
        v1, v2, v21 = P.PROMPTS["v1"], P.PROMPTS["v2"], P.PROMPTS["v2_1"]
        self.assertTrue(v21.startswith(v1 + "\n"))
        a, b = v2[len(v1) + 1:].splitlines(), v21[len(v1) + 1:].splitlines()
        self.assertEqual([x.split(".")[0] for x in b], ["10", "11", "12", "13", "14"])
        self.assertEqual([x.split(".")[0] for x, y in zip(a, b) if x != y], ["12", "13"])
        self.assertIn("원문에 없는 \"KE-\"를 붙이지 않는다", b[3])

    def test_v2_is_v1_plus_rules_10_to_14(self):
        v1, v2 = P.PROMPTS["v1"], P.PROMPTS["v2"]
        self.assertTrue(v2.startswith(v1 + "\n"))
        added = v2[len(v1) + 1:].splitlines()
        self.assertEqual([re.match(r"(\d+)\. ", line).group(1) for line in added], ["10", "11", "12", "13", "14"])

    def test_default_is_v1(self):
        self.assertEqual(P.DEFAULT_PROMPT, "v1")
        self.assertEqual(P.build_messages("본문")[0]["content"], P.PROMPTS["v1"])
        self.assertEqual(P.build_messages("본문", prompt="v2")[0]["content"], P.PROMPTS["v2"])
        with self.assertRaises(ValueError):
            P.build_messages("본문", prompt="v9")

    def test_subdir_keeps_v1_in_place(self):
        self.assertEqual(P.prompt_subdir("v1"), "")
        self.assertEqual(P.prompt_subdir("v2"), "prompt_v2")
        self.assertEqual(P.prompt_subdir("v2_1"), "prompt_v2_1")

    def test_recorded_version(self):
        self.assertEqual(P.recorded_prompt_version({"prompt_version": "v2"}), "v2")
        self.assertEqual(P.recorded_prompt_version({"prompt_sha256": P.LEGACY_V1_FILE_SHA256}), "v1")  # 09-29 이전 기록
        self.assertIsNone(P.recorded_prompt_version({"prompt_sha256": "0" * 64}))
        self.assertNotEqual(P.prompt_sha256("v1"), P.prompt_sha256("v2"))


if __name__ == "__main__":
    unittest.main()

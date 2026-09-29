"""
[어채은] app/web_results.py 회귀 테스트 — 저장된 val 결과 → 검토 화면용 JSON이 화면 명세(docs/frontend_api_spec.md)를 지키는지.

  python3 tests/test_web_results.py -v
val 결과(outputs/*/val)가 없으면 내보내기 테스트는 건너뛴다.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import web_results as wr  # noqa: E402

STATUSES = {"OK", "REVIEW_REQUIRED", "SOURCE_CHECK_REQUIRED"}
REASONS = {None, "FORMAT_ERROR", "INCONSISTENT", "NOT_FOUND"}


class RuleMappingTest(unittest.TestCase):
    def label(self):
        return json.loads((ROOT / "test" / "fixtures" / "labels" / "KR-KUMHO-002.json").read_text(encoding="utf-8"))

    def test_core_fields_have_screen_shape(self):
        text = (ROOT / "test" / "fixtures" / "text" / "KR-KUMHO-002.txt").read_text(encoding="utf-8")
        out = wr.field_rule_results(self.label(), text, "KR-KUMHO-002")
        self.assertEqual(set(out), set(wr.CORE_FIELDS))
        for r in out.values():
            self.assertIn(r["review_status"], STATUSES)
            self.assertIn(r["reason_code"], REASONS)
            self.assertIsNone(r["page"])  # 전처리 텍스트에 쪽 경계가 없음

    def test_cas_format_error_is_review_required(self):
        lab = self.label()
        lab["ingredients"][0]["cas_number"] = "12-34"  # CAS 형식 오류
        out = wr.field_rule_results(lab, None, "x")
        self.assertEqual((out["ingredients"]["review_status"], out["ingredients"]["reason_code"]),
                         ("REVIEW_REQUIRED", "FORMAT_ERROR"))


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any((ROOT / "outputs" / c / "val" / "_run.jsonl").exists() for c in wr.CONDITIONS):
            raise unittest.SkipTest("val 결과(outputs/*/val) 없음")

    def test_compare_has_required_numbers(self):
        comp = wr.build_compare()
        self.assertEqual(comp["split"], "val")
        self.assertTrue(comp["experiments"])
        self.assertEqual(comp["experiments"][0]["id"], "base_zs")  # 화면은 첫 항목을 기준 조건으로 씀
        for e in comp["experiments"]:
            for k in ("parsing", "schema", "cas", "pair", "hcode", "seconds", "tokens"):
                self.assertIsInstance(e[k], (int, float), (e["id"], k))

    def test_documents_are_complete_and_failures_listed(self):
        data = wr.build_documents()
        n_out = sum(1 for c in wr.CONDITIONS if (ROOT / "outputs" / c / "val" / "_run.jsonl").exists())
        self.assertEqual(len(data["documents"]) + len(data["skipped"]), n_out * data["n_val_docs"])  # 조용히 버리지 않음
        for d in data["documents"]:
            self.assertEqual(wr._missing_keys(d["extraction"]), [])
            self.assertEqual(set(d["rule_results"]), set(wr.CORE_FIELDS))
            self.assertTrue(d["split"].startswith("val"))
            # 원본 PDF는 파일명 대신 doc_id 주소로만 가리킨다(vite.config.js가 결과 목록에 있는 문서만 보냄)
            self.assertIn(d["pdf_url"], (None, f"./pdfs/{d['doc_id']}.pdf"))


if __name__ == "__main__":
    unittest.main()

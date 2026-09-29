"""PDF 추출 실패를 모델 입력으로 보내지 않는 경계를 GPU 없이 확인한다."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pipeline_run import get_text
from eval.infer import select_docs
from pipeline import extract_text


class ExtractTextTest(unittest.TestCase):
    def test_pdf_is_cut_and_upload_uses_same_extractor(self):
        class Page:
            def extract_text(self):
                return ("1. 화학제품과 회사에 관한 정보\n제품명 예시 제품\n" + "설명 " * 45 +
                        "\n2. 유해성 위험성\nH 412 유해 문구\n" +
                        "예방조치문구 - 예방\nP264 손을 씻으시오\n" +
                        "3. 구성성분의 명칭 및 함유량\nCAS 123-45-6\n" +
                        "4. 응급조치 요령\n4항 내용")

        class PDF:
            pages = [Page()]
            def __enter__(self): return self
            def __exit__(self, *_): pass

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(extract_text.pdfplumber, "open", return_value=PDF()):
            pdf = Path(tmp) / "sample.pdf"
            pdf.write_bytes(b"%PDF-test")
            result = extract_text.extract_pdf(pdf)
            self.assertEqual(result["status"], "SUCCESS")
            self.assertIn("H412", result["text"])
            self.assertNotIn("P264", result["text"])
            self.assertNotIn("4. 응급조치", result["text"])
            self.assertEqual(get_text(pdf, None), (result["text"], None))

    def test_batch_logs_failed_document_and_infer_counts_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, text = root / "raw", root / "text"
            raw.mkdir()
            for name in ("ok.pdf", "bad.pdf"):
                (raw / name).write_bytes(b"%PDF-test")
            manifest = root / "sources.csv"
            manifest.write_text("doc_id,source_file\nDOC-1,ok.pdf\nDOC-2,bad.pdf\n", encoding="utf-8")
            def fake_extract(path):
                if path.name == "bad.pdf":
                    return extract_text._failed("NOT_FOUND_SECTION4", "raw text")
                return {"status": "SUCCESS", "reason": "", "text": "valid text", "raw_text": "",
                        "section4_pattern": "KO_4", "p_block_pattern": None, "cut_page": 1,
                        "h_code_before": 0, "h_code_after": 0, "note": ""}
            with mock.patch.object(extract_text, "extract_pdf", side_effect=fake_extract):
                self.assertEqual(extract_text.extract_directory(raw, manifest, text, expected_count=2), (1, 1))
            with (text / "_cut_log.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([(r["doc_id"], r["status"], r["reason"]) for r in rows],
                             [("DOC-1", "SUCCESS", ""), ("DOC-2", "NOT_FOUND", "NOT_FOUND_SECTION4")])
            self.assertFalse((text / "DOC-2.txt").exists())
            self.assertTrue((text / "review_required" / "DOC-2.txt").exists())
            args = type("Args", (), {"split": "test"})()
            self.assertEqual(select_docs(args, {}, text), ["DOC-1", "DOC-2"])
            with self.assertRaises(FileExistsError):
                extract_text.extract_directory(raw, manifest, text, expected_count=2)


if __name__ == "__main__":
    unittest.main()

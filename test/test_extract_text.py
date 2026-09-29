"""PDF 추출 실패를 모델 입력으로 보내지 않는 경계를 GPU 없이 확인한다."""
import csv
import re
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

    def test_bold_repeat_factor_adapts_per_document(self):
        """KR-THERMO-001은 5회가 아니라 4회 겹쳐 뽑혔다 — 고정 배수 대신 문서별로 잰다."""
        base = "물질안전보건자료제품유해위험성분류신호어문구공급자정보긴급전화번호취급주의사항저장방법"
        for factor in (4, 5, 6):
            duplicated = "".join(ch * factor for ch in base)
            with self.subTest(factor=factor):
                self.assertEqual(extract_text.bold_repeat_factor(duplicated), factor)
                self.assertEqual(extract_text.undouble(duplicated), base)

    def test_undouble_keeps_genuine_double_letter_within_bold_run(self):
        """"구성성분"처럼 원래 두 번 연달아 나오는 글자는(배수 4 문서에서 8번 겹침) 1개가 아니라
        2개로 남아야 한다 — 5회 고정이 아니라 이 문서에서 잰 배수(4)로 접기 때문에 가능하다."""
        base = "물질안전보건자료제품유해위험성분류신호어문구공급자정보긴급전화번호취급주의사항저장"
        doubled_word = "구" + "성" * 2 + "분"  # 원문 "구성성분"
        text = "".join(ch * 4 for ch in base) + "".join(ch * 4 for ch in doubled_word)
        self.assertEqual(extract_text.bold_repeat_factor(text), 4)
        self.assertEqual(extract_text.undouble(text), base + doubled_word)

    def test_bold_repeat_factor_leaves_normal_text_untouched(self):
        """겹침이 거의 없는 정상 텍스트(스캔이 아님)는 배수를 매기지 않고 그대로 둔다."""
        normal = "제품명 예시 제품\n구성성분 표\n신호어 위험\n" * 5
        self.assertEqual(extract_text.bold_repeat_factor(normal), 1)
        self.assertEqual(extract_text.undouble(normal), normal)

    def test_extract_pdf_strips_p_block_with_non_standard_bold_factor(self):
        """4회 겹침 문서(KR-THERMO-001과 같은 배수)에서도 undouble이 먼저 되돌려야 P문구 라벨을
        인식해 블록을 제거한다 — 5회 고정이면 이 사례에서 P문구가 새어 들어갔었다."""
        base = ("물질안전보건자료제품유해위험성분류신호어문구공급자정보긴급전화번호취급주의사항저장"
                "방법폐기응급조치누출사고예방조치문구대응저장폐기")

        def dup4(word):
            # 실제 PDF도 한글·가운뎃점만 겹쳐 뽑고 숫자·구두점·공백은 그대로 둔다(항목 번호 "4."가
            # 안 겹쳐야 SECTION4_PATTERNS의 "4"가 그대로 걸림)
            return "".join(ch * 4 if re.fullmatch(r"[가-힣ㆍ․]", ch) else ch for ch in word)

        class Page:
            def extract_text(self):
                return (dup4("1. 화학제품과 회사에 관한 정보") + "\n" + dup4("제품명") + " 예시 제품\n" +
                        "설명 " * 45 + "\n" +
                        dup4(base) + "\n" + dup4("2. 유해성 위험성") + "\nH 412 유해 문구\n" +
                        dup4("예방조치문구 - 예방") + "\nP264 손을 씻으시오\n" +
                        dup4("3. 구성성분의 명칭 및 함유량") + "\nCAS 123-45-6\n" +
                        dup4("4. 응급조치 요령") + "\n4항 내용")

        class PDF:
            pages = [Page()]
            def __enter__(self): return self
            def __exit__(self, *_): pass

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(extract_text.pdfplumber, "open", return_value=PDF()):
            pdf = Path(tmp) / "sample.pdf"
            pdf.write_bytes(b"%PDF-test")
            result = extract_text.extract_pdf(pdf)
            self.assertEqual(result["status"], "SUCCESS")
            self.assertNotIn("물물물물", result["text"])  # 겹침이 되돌려짐
            self.assertIn("H412", result["text"])
            self.assertNotIn("P264", result["text"])       # P문구 블록 제거됨(5회 고정이면 실패했음)
            self.assertNotIn("4. 응급조치", result["text"])

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

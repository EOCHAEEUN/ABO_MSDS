"""MSDS 질의 API의 입력 검증과 응답 전달을 모델 없이 확인한다."""
from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402

from app.main import ask_msds  # noqa: E402
from app.rag.service import RagService, RagUnavailable  # noqa: E402


class FakeService:
    def ask(self, question: str) -> dict:
        return {
            "answer": f"답변: {question}",
            "path": ["classify", "retrieve", "grade", "generate"],
            "evidence": [{
                "doc_id": "KR-DEMO-001", "product_name": "예시 제품", "section": 8,
                "section_title": "노출방지 및 개인보호구", "content": "보호장갑을 착용한다.",
            }],
        }


class RagApiTest(unittest.TestCase):
    def test_blank_question_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            ask_msds({"question": "  "})
        self.assertEqual(caught.exception.status_code, 422)

    def test_long_question_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            ask_msds({"question": "가" * 1001})
        self.assertEqual(caught.exception.status_code, 422)

    @patch("app.rag.service.get_service", return_value=FakeService())
    def test_answer_includes_path_and_evidence(self, _service):
        result = ask_msds({"question": " 보호구는? "})
        self.assertEqual(result["answer"], "답변: 보호구는?")
        self.assertEqual(result["path"][-1], "generate")
        self.assertEqual(result["evidence"][0]["section"], 8)

    @patch("app.rag.service.get_service", side_effect=RagUnavailable("인덱스 없음"))
    def test_unavailable_service_is_503(self, _service):
        with self.assertRaises(HTTPException) as caught:
            ask_msds({"question": "보호구는?"})
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "인덱스 없음")

    @patch("app.rag.graph.run")
    def test_evidence_keeps_different_products_from_legacy_index(self, run):
        run.return_value = ("답변", ["generate"], [
            SimpleNamespace(page_content="[출처: A · 9. 물리]\n10 ℃", metadata={"product_name": "A", "section": 9, "section_title": "물리", "chunk": 0}),
            SimpleNamespace(page_content="[출처: B · 9. 물리]\n20 ℃", metadata={"product_name": "B", "section": 9, "section_title": "물리", "chunk": 0}),
        ])
        service = object.__new__(RagService)
        service.graph = object()
        service._lock = threading.Lock()
        result = service.ask("비교")
        self.assertEqual([item["product_name"] for item in result["evidence"]], ["A", "B"])


if __name__ == "__main__":
    unittest.main()

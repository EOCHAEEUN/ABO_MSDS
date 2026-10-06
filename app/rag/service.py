"""FastAPI가 호출하는 지연 로딩 RAG 서비스."""
from __future__ import annotations

import threading

from app.rag import settings


class RagUnavailable(RuntimeError):
    """인덱스나 Ollama가 준비되지 않아 질의할 수 없을 때."""


class RagService:
    def __init__(self):
        from app.rag.graph import build_graph, list_products

        if not settings.INDEX_DIR.is_dir():
            raise RagUnavailable(
                f"RAG 인덱스가 없습니다: {settings.INDEX_DIR}. "
                "python3 -m app.rag.index --overwrite 를 먼저 실행해 주세요."
            )
        try:
            vectorstore = settings.get_vectorstore()
            products = list_products(vectorstore)
        except Exception as issue:
            raise RagUnavailable(f"RAG 인덱스를 열지 못했습니다: {issue}") from issue
        if not products:
            raise RagUnavailable("RAG 인덱스가 비어 있습니다. python3 -m app.rag.index --overwrite 를 실행해 주세요.")
        try:
            self.graph = build_graph(settings.get_llm(), vectorstore, products)
        except Exception as issue:
            raise RagUnavailable(f"RAG 모델을 준비하지 못했습니다: {issue}") from issue
        self.products = products
        self._lock = threading.Lock()

    def ask(self, question: str) -> dict:
        from app.rag.graph import run

        try:
            with self._lock:
                answer, path, docs = run(self.graph, question)
        except Exception as issue:
            raise RagUnavailable(
                f"질의응답 모델을 실행하지 못했습니다. Ollama와 모델({settings.LLM_MODEL}, {settings.EMBED_MODEL}) 상태를 확인해 주세요: {issue}"
            ) from issue
        evidence = []
        seen = set()
        for doc in docs:
            meta = doc.metadata or {}
            key = (meta.get("doc_id"), meta.get("product_name"), meta.get("section"), meta.get("chunk"))
            if key in seen:
                continue
            seen.add(key)
            content = doc.page_content
            if content.startswith("[출처:") and "\n" in content:
                content = content.split("\n", 1)[1]
            evidence.append({
                "doc_id": meta.get("doc_id"),
                "product_name": meta.get("product_name") or "제품명 미확인",
                "section": meta.get("section"),
                "section_title": meta.get("section_title") or "항목 미확인",
                "content": content[:1200],
            })
        return {"answer": answer, "path": path, "evidence": evidence}


_service: RagService | None = None
_service_lock = threading.Lock()


def get_service() -> RagService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = RagService()
    return _service

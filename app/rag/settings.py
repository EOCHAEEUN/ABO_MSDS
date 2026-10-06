"""RAG 설정.

추출용 QLoRA와 별개로 Ollama를 사용한다. 환경변수로 모델과 인덱스 위치를
바꿀 수 있지만 기본값은 저장소 안의 git 제외 경로(data/rag/)다.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


INDEX_DIR = _path("MSDS_RAG_INDEX_DIR", ROOT / "data" / "rag" / "chroma")
COLLECTION_NAME = os.getenv("MSDS_RAG_COLLECTION", "msds")
LLM_MODEL = os.getenv("MSDS_RAG_LLM_MODEL", "qwen3.5:9b")
EMBED_MODEL = os.getenv("MSDS_RAG_EMBED_MODEL", "bge-m3")
NUM_CTX = int(os.getenv("MSDS_RAG_NUM_CTX", "8192"))

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
TOP_K = 4
TOP_K_COMPARE = 2
MAX_RETRIES = 1
TOKENS_PER_CHAR = 0.6
MAX_CONTEXT_CHARS = int((NUM_CTX - 2500) / TOKENS_PER_CHAR)

MSDS_SECTIONS = {
    1: "화학제품과 회사에 관한 정보",
    2: "유해성·위험성",
    3: "구성성분의 명칭 및 함유량",
    4: "응급조치 요령",
    5: "폭발·화재 시 대처방법",
    6: "누출 사고 시 대처방법",
    7: "취급 및 저장방법",
    8: "노출방지 및 개인보호구",
    9: "물리화학적 특성",
    10: "안정성 및 반응성",
    11: "독성에 관한 정보",
    12: "환경에 미치는 영향",
    13: "폐기 시 주의사항",
    14: "운송에 필요한 정보",
    15: "법적 규제현황",
    16: "그 밖의 참고사항",
}


def get_llm():
    from langchain_ollama import ChatOllama

    return ChatOllama(model=LLM_MODEL, temperature=0, reasoning=False, num_ctx=NUM_CTX)


def get_embeddings():
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=EMBED_MODEL)


def get_vectorstore():
    from langchain_chroma import Chroma

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(INDEX_DIR),
    )

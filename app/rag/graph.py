"""LangGraph 기반 MSDS 근거 검색·답변 흐름."""
from __future__ import annotations

import re
from typing import Literal, TypedDict

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.rag import settings


class State(TypedDict, total=False):
    question: str
    query: str
    q_type: str
    products: list[str]
    unregistered: list[str]
    sections: list[int]
    docs: list[Document]
    sufficient: bool
    retries: int
    answer: str


class Classification(BaseModel):
    q_type: Literal["single", "compare", "off_topic"] = Field(
        description="single: 제품 하나 또는 제품 미지정, compare: 제품 비교, off_topic: MSDS와 무관"
    )
    mentioned: list[str] = Field(default_factory=list, description="질문에 언급된 제품·물질 이름")
    products: list[str] = Field(default_factory=list, description="등록 목록과 정확히 일치하는 제품명")
    sections: list[int] = Field(default_factory=list, description="답이 있을 MSDS 항목 번호, 최대 3개")
    main_section: int | None = Field(default=None, description="가장 가능성 높은 MSDS 항목 번호")
    search_query: str = Field(default="", description="MSDS 문서 검색용 짧은 핵심어")


class Grade(BaseModel):
    sufficient: bool = Field(description="근거만으로 답할 수 있는지")
    reason: str = Field(description="판단 이유")


CLASSIFY_PROMPT = """너는 MSDS(물질안전보건자료) 질의응답 시스템의 질문 분류기다.

[등록된 제품 목록]
{products}

[MSDS 16개 항목]
{sections}

[질문]
{question}

- q_type: 제품 1개이거나 제품을 특정하지 않은 질문이면 single, 2개 이상 비교하거나 전체 중에서 고르는 질문이면 compare, MSDS와 무관하면 off_topic
- mentioned: 질문에 나온 제품·물질 이름을 그대로 모두 적는다. 일반 용어는 제품 이름으로 넣지 않는다.
- products: mentioned 중 등록 목록에 있는 제품만 목록의 이름 그대로 적는다. 전체 비교 질문이면 비운다.
- sections: 답이 있을 항목 번호를 최대 3개 고른다.
- main_section: 가장 가능성 높은 항목 하나를 고른다. 예: 인화점 9, 보호구 8, 눈 접촉 4
- search_query: MSDS에 실제로 쓰이는 짧은 검색어로 바꾼다."""

GRADE_PROMPT = """아래 [근거]만 보고 [질문]에 답할 수 있는지 판단해라.
근거에 답이 직접 적혀 있어야 true다. 일반 상식이나 다른 제품 정보로 추측해야 하면 false다.
여러 제품 비교에서는 해당 항목 근거가 있으면 일부 값이 자료없음이어도 true다.

[질문]
{question}

[근거]
{context}"""

REWRITE_PROMPT = """MSDS 문서 검색에서 답을 찾지 못했다. MSDS에 쓰이는 용어로 검색어를 다시 써라.
예: '장갑 뭐 껴?' → '개인보호구 손 보호 보호장갑 재질', '불 붙는 온도' → '인화점'

원래 질문: {question}
이전 검색어: {query}

새 검색어 한 줄만 출력해라."""

ANSWER_PROMPT = """너는 MSDS 검토를 돕는 어시스턴트다. 아래 [근거]에 있는 내용만 사용해 한국어로 답해라.

규칙
1. 근거에 없는 내용은 추측하지 말고 'MSDS에서 확인되지 않음'이라고 쓴다.
2. 문장마다 끝에 출처를 [제품명 · 항목번호] 형식으로 붙인다.
3. 여러 제품을 비교하면 마크다운 표로 정리한다. 자료가 없는 제품은 '자료없음'으로 표시하고 순위에서 뺀다.
4. 수치는 단위와 측정 조건까지 근거 그대로 옮긴다. 조건이 다른 값은 단순 비교할 수 없다고 밝힌다.

[질문]
{question}

[근거]
{context}"""


def list_products(vectorstore) -> list[str]:
    data = vectorstore.get(include=["metadatas"])
    return sorted({m["product_name"] for m in data["metadatas"] if m and m.get("product_name")})


def make_filter(product: str | None = None, sections: list[int] | None = None):
    conditions = []
    if product:
        conditions.append({"product_name": product})
    if sections:
        conditions.append({"section": {"$in": list(sections)}})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def is_registered(name: str, known: list[str]) -> bool:
    words = name.lower().split()
    return any(name in item or item in name or all(word in item.lower() for word in words) for item in known)


def find_unregistered(mentioned: list[str], known: list[str]) -> list[str]:
    return [name for name in mentioned if name and not is_registered(name, known)]


def format_docs(docs: list[Document]) -> str:
    context = "\n\n---\n\n".join(doc.page_content for doc in docs)
    if len(context) > settings.MAX_CONTEXT_CHARS:
        print(f"[RAG 경고] 근거 {len(context):,}자가 권장 상한 {settings.MAX_CONTEXT_CHARS:,}자를 넘습니다.")
    return context


def clean(value) -> str:
    text = value if isinstance(value, str) else str(value)
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def build_graph(llm, vectorstore, known: list[str] | None = None):
    known = known if known is not None else list_products(vectorstore)
    classifier = llm.with_structured_output(Classification)
    grader = llm.with_structured_output(Grade)
    section_guide = "\n".join(f"{number}. {title}" for number, title in settings.MSDS_SECTIONS.items())

    def classify(state: State):
        result = classifier.invoke(CLASSIFY_PROMPT.format(
            products=", ".join(known), sections=section_guide, question=state["question"]
        ))
        sections = [number for number in result.sections if 1 <= number <= 16][:3]
        main = result.main_section if result.main_section and 1 <= result.main_section <= 16 else None
        if result.q_type == "compare" and (main or sections):
            sections = [main or sections[0]]
        return {
            "q_type": result.q_type,
            "products": [product for product in result.products if product in known],
            "unregistered": find_unregistered(result.mentioned, known),
            "sections": sections,
            "query": result.search_query.strip() or state["question"],
            "retries": 0,
        }

    def retrieve(state: State):
        sections = [] if state.get("retries", 0) else state.get("sections", [])
        if state.get("products"):
            targets = state["products"]
        elif state.get("q_type") == "compare":
            targets = known
        else:
            targets = [None]
        wanted = settings.TOP_K_COMPARE if len(targets) > 1 else settings.TOP_K if targets[0] else settings.TOP_K * 2
        fit = settings.MAX_CONTEXT_CHARS // max(len(targets) * settings.CHUNK_SIZE, 1)
        count = max(1, min(wanted, fit))
        docs = []
        for product in targets:
            docs.extend(vectorstore.similarity_search(state["query"], k=count, filter=make_filter(product, sections)))
        return {"docs": docs}

    def grade(state: State):
        if not state.get("docs"):
            return {"sufficient": False}
        result = grader.invoke(GRADE_PROMPT.format(question=state["question"], context=format_docs(state["docs"])))
        return {"sufficient": result.sufficient}

    def rewrite(state: State):
        response = llm.invoke(REWRITE_PROMPT.format(question=state["question"], query=state["query"]))
        query = clean(response.content)
        return {"query": query or state["question"], "retries": state.get("retries", 0) + 1}

    def generate(state: State):
        response = llm.invoke(ANSWER_PROMPT.format(question=state["question"], context=format_docs(state["docs"])))
        answer = clean(response.content)
        if state.get("unregistered"):
            answer += f"\n\n※ 등록되지 않아 답에서 뺀 제품: {', '.join(state['unregistered'])}"
        return {"answer": answer}

    def fallback(state: State):
        if state.get("q_type") == "off_topic":
            message = f"MSDS에 관한 질문만 답할 수 있습니다.\n등록된 제품: {', '.join(known)}"
        elif state.get("unregistered") and not state.get("products"):
            message = f"등록되지 않은 제품이라 답할 수 없습니다: {', '.join(state['unregistered'])}\n등록된 제품: {', '.join(known)}"
        else:
            message = f"제공된 MSDS에서 근거를 찾지 못해 답할 수 없습니다. 추측해서 답하지 않습니다.\n(마지막 검색어: {state.get('query', state['question'])})"
        return {"answer": message}

    def after_classify(state: State):
        if state["q_type"] == "off_topic" or (state.get("unregistered") and not state.get("products")):
            return "fallback"
        return "retrieve"

    def after_grade(state: State):
        if state["sufficient"]:
            return "generate"
        return "rewrite" if state.get("retries", 0) < settings.MAX_RETRIES else "fallback"

    workflow = StateGraph(State)
    for name, node in (("classify", classify), ("retrieve", retrieve), ("grade", grade),
                       ("rewrite", rewrite), ("generate", generate), ("fallback", fallback)):
        workflow.add_node(name, node)
    workflow.add_edge(START, "classify")
    workflow.add_conditional_edges("classify", after_classify, ["retrieve", "fallback"])
    workflow.add_edge("retrieve", "grade")
    workflow.add_conditional_edges("grade", after_grade, ["generate", "rewrite", "fallback"])
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", END)
    workflow.add_edge("fallback", END)
    return workflow.compile()


def run(graph, question: str):
    path, final = [], {}
    for step in graph.stream({"question": question}, stream_mode="updates"):
        for node, update in step.items():
            path.append(node)
            final.update(update or {})
    return final.get("answer", ""), path, final.get("docs", [])

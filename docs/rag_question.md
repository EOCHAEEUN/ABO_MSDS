# MSDS 질의 화면

`workspace.html#question`은 등록된 MSDS의 1~16항을 검색해 근거 기반으로 답하는 화면이다. 기존 1~3항 고정 JSON 추출 모델과 스키마는 바꾸지 않으며, 질의응답은 `app/rag/`의 별도 인덱스와 로컬 Ollama 모델을 사용한다.

## 준비

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-rag.txt

ollama pull qwen3.5:9b
ollama pull bge-m3

# data/raw/에 팀 드라이브의 train·val 원본 PDF를 준비한 뒤 실행
python3 -m app.rag.index --overwrite

# 또는 별도 데이터 폴더의 PDF를 그대로 사용(파일명 = 제품명)
python3 -m app.rag.index --pdf-dir /home/ai_fish/msds_rag/data/pdf --overwrite
```

기본 인덱서는 `data/splits.csv`에서 `train`과 `val`인 문서만 선택한다. `--pdf-dir`을 주면 해당 폴더 바로 아래의 `*.pdf`를 읽고 파일명을 제품명으로 사용한다. 두 경로 모두 봉인 manifest와 PDF·추출 텍스트 해시를 대조하며, 일치하는 test 자료는 인덱싱하지 않는다. 생성물은 `data/rag/`에 저장되고 Git에는 커밋하지 않는다. PDF 텍스트가 200자보다 짧거나 판독되지 않는 문서는 건너뛴 이유를 출력한다.

## 실행

```bash
python3 -m app.main serve
npm --prefix web run dev
```

브라우저에서 `http://localhost:5173/workspace.html#question`을 연다. Vite는 `/ask` 요청을 FastAPI로 전달한다. 빌드된 화면을 사용할 때는 같은 origin에서 `/ask`를 제공해야 한다.

## API

`POST /ask`

```json
{"question": "이 제품을 취급할 때 필요한 개인보호구는?"}
```

```json
{
  "answer": "MSDS 근거만 사용한 답변",
  "path": ["classify", "retrieve", "grade", "generate"],
  "evidence": [
    {
      "doc_id": "KR-XXX-001",
      "product_name": "제품명",
      "section": 8,
      "section_title": "노출방지 및 개인보호구",
      "content": "검색된 원문 조각"
    }
  ]
}
```

질문은 1,000자까지 받는다. 인덱스가 없거나 Ollama가 실행되지 않으면 `503`과 사용자가 볼 수 있는 한국어 `detail`을 반환한다.

## 설정

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `MSDS_RAG_INDEX_DIR` | `data/rag/chroma` | 로컬 ChromaDB 경로 |
| `MSDS_RAG_COLLECTION` | `msds` | Chroma 컬렉션 이름 |
| `MSDS_RAG_LLM_MODEL` | `qwen3.5:9b` | 답변·분류용 Ollama 모델 |
| `MSDS_RAG_EMBED_MODEL` | `bge-m3` | 임베딩용 Ollama 모델 |
| `MSDS_RAG_NUM_CTX` | `8192` | LLM 컨텍스트 길이 |

추출용 Qwen3-4B QLoRA와 Ollama 모델을 동시에 GPU에 올리면 8GB 환경에서 메모리가 부족할 수 있다. 시연에서는 `serve --preload`를 사용하지 않거나, PDF 추출과 질의응답을 순차적으로 실행한다.

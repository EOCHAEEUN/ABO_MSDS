"""[김건하] data/labels(train·val 정답 라벨) + data/text(원문 1~3항 텍스트)로
web/src/workspace/demo-documents.json(프런트 예시 모드 데이터)을 만든다.

기존 data.js의 demoDocuments()는 완전히 지어낸 8건이었다. "2번으로 해줘"(예시 모드를
실제 데이터 기반으로 바꾼다) 결정에 따라 이 스크립트로 만든 실제 45건으로 교체했다.
data.js 맨 위 주석("Never read training labels...")과 충돌하는 걸 알고 진행한 결정이다.

rule_results는 app.web_results.field_rule_results()를 그대로 가져다 쓴다 — 즉
app/rules(Rule Engine)가 실제로 원문을 대조해서 만드는 값이다. 예시 모드 전용으로
근거 찾기 로직을 따로 만들면 나중에 둘이 어긋난다(실제로 한 번 어긋나서 신호어 근거가
엉뚱한 줄을 가리키는 버그가 있었다) — 그래서 따로 만들지 않고 재사용한다.

사용법 (저장소 루트에서): python3 scripts/build_demo_documents.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import pdfplumber

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.web_results import field_rule_results  # noqa: E402


def build(repo_root: str) -> list[dict]:
    label_files = sorted(glob.glob(os.path.join(repo_root, "data/labels/*.json")))
    docs = []
    for idx, lf in enumerate(label_files):
        doc_id = os.path.basename(lf)[:-5]
        extraction = json.loads(open(lf, encoding="utf-8").read())
        text_path = os.path.join(repo_root, f"data/text/{doc_id}.txt")
        text = open(text_path, encoding="utf-8").read()

        pdf_path = os.path.join(repo_root, f"data/raw/{doc_id}.pdf")
        page_count = None
        if os.path.exists(pdf_path):
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    page_count = len(pdf.pages)
            except Exception:
                page_count = None

        docs.append(
            {
                "id": doc_id,
                "number": idx + 1,
                "file_name": f"{doc_id}.pdf",
                "language": "한국어",
                "page_count": page_count,
                "submission_number": None,
                "revision_date": None,
                "extracted_at": None,
                "updated_at": None,
                "owner": "미지정",
                "split": "예시(정답 라벨)",
                "model_name": "정답 라벨",
                "generation_seconds": None,
                "output_tokens": None,
                "extraction": extraction,
                "source": None,  # 종이 모양 mock 재현 없음 — source_text(원문 전체)를 대신 씀
                "pdf_url": None,  # data/raw/*.pdf는 저작권 때문에 웹에 올리지 않음(.gitignore)
                "source_text": text,
                "reviews": {},
                "confirmed_fields": [],
                "rule_results": field_rule_results(extraction, text, doc_id),
            }
        )
    return docs


def main() -> int:
    docs = build(_REPO_ROOT)

    out_path = os.path.join(_REPO_ROOT, "web/src/workspace/demo-documents.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    n_total = sum(len(d["rule_results"]) for d in docs)
    n_ok = sum(1 for d in docs for r in d["rule_results"].values() if r["review_status"] == "OK")
    print(f"{len(docs)}개 문서 -> {out_path}")
    print(f"필드별 근거 매칭: {n_ok}/{n_total} OK")
    for d in docs:
        for field, r in d["rule_results"].items():
            if r["review_status"] != "OK":
                print(f"  {r['review_status']}: {d['id']} {field} ({r['reason_code']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

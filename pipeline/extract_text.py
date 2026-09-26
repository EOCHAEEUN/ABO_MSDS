"""
[강덕우] raw/ → text/ 일괄 변환, _cut_log.csv 기록
"""

# 저장 위치: <프로젝트 루트>/pipeline/extract_text.py
"""data/raw/*.pdf → data/text/{doc_id}.txt + data/text/_cut_log.csv

실행: python -m pipeline.extract_text
      python -m pipeline.extract_text --raw data/raw --out data/text --no-token

- 4항 경계를 못 찾으면(NOT_FOUND) data/text/에 쓰지 않고
  data/text/review_required/ 로 빼서 사람이 확인하게 한다. 자동 투입 금지.
- 토큰 수는 transformers가 있을 때만 센다(--no-token으로 끌 수 있음).
"""
import argparse
import csv
import glob
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.preprocess import SECTION4_PATTERNS, find_first, preprocess  # noqa: E402

MIN_CHARS = 200          # 이보다 짧으면 스캔 PDF로 보고 제외
LOG_COLUMNS = ["doc_id", "status", "section4_pattern", "p_block_pattern", "cut_page",
               "char_count", "token_count", "h_code_before", "h_code_after", "note"]


def load_tokenizer(model_id="Qwen/Qwen3-4B"):
    try:
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(model_id)
    except Exception as e:                                  # 오프라인·미설치 모두 여기로
        print(f"[알림] 토크나이저를 불러오지 못해 token_count를 비웁니다: {type(e).__name__}")
        return None


def read_pages(path):
    """페이지별 텍스트 목록을 반환한다. .txt는 1페이지로 취급(테스트용)."""
    if not path.lower().endswith(".pdf"):
        with open(path, encoding="utf-8") as f:
            return [f.read()]
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


def undouble(text):
    """굵은 글씨가 겹쳐 뽑힌 줄을 되돌린다.
    네 번: "안안안안전전전전" → "안전"
    두 번: "44.. 응응급급조조치치" → "4. 응급조치" — 한글 대부분이 짝으로 겹친 줄만 손댄다.
    """
    out = []
    for line in text.split("\n"):
        line = re.sub(r'([가-힣ㆍ·])\1{3}', r'\1', line)
        han = re.findall(r'[가-힣]', line)
        pairs = re.findall(r'([가-힣])\1', line)
        if len(han) >= 4 and 2 * len(pairs) >= 0.6 * len(han):
            line = re.sub(r'(\S)\1', r'\1', line)
        out.append(line)
    return "\n".join(out)


def find_cut_page(pages):
    """4항 제목이 처음 나온 페이지 번호(1부터). 못 찾으면 None."""
    for n, page_text in enumerate(pages, start=1):
        if find_first(SECTION4_PATTERNS, undouble(page_text).splitlines())[0] is not None:
            return n
    return None


def load_doc_ids(sources="data/sources.csv"):
    """원본 파일명 → doc_id. 출력 파일명을 라벨(data/labels/{doc_id}.json)과 맞춘다."""
    if not os.path.exists(sources):
        return {}
    with open(sources, encoding="utf-8-sig", newline="") as f:
        return {r["source_file"]: r["doc_id"] for r in csv.DictReader(f)}


def process(path, out_dir, tokenizer, doc_ids):
    stem = os.path.splitext(os.path.basename(path))[0]
    doc_id = doc_ids.get(os.path.basename(path), stem)
    try:
        pages = read_pages(path)
    except Exception as e:
        return dict(doc_id=doc_id, status="NOT_FOUND", section4_pattern=None, p_block_pattern=None,
                    cut_page=None, char_count=0, token_count=None, h_code_before=0, h_code_after=0,
                    note=f"파일 읽기 실패: {type(e).__name__}")

    raw = "\n".join(pages)
    if len(raw.strip()) < MIN_CHARS:
        _write(out_dir, "review_required", doc_id, raw)
        return dict(doc_id=doc_id, status="NOT_FOUND", section4_pattern=None, p_block_pattern=None,
                    cut_page=None, char_count=len(raw), token_count=None,
                    h_code_before=0, h_code_after=0, note="스캔 PDF 의심 (텍스트 부족)")

    raw = undouble(raw)
    r = preprocess(raw)
    cut_page = find_cut_page(pages)

    if r["status"] == "NOT_FOUND":
        _write(out_dir, "review_required", doc_id, raw)
        return dict(doc_id=doc_id, status="NOT_FOUND", section4_pattern=None, p_block_pattern=None,
                    cut_page=None, char_count=len(raw), token_count=None,
                    h_code_before=r["h_code_before"], h_code_after=0, note=r["note"])

    text = r["text"]
    _write(out_dir, None, doc_id, text)
    n_tok = len(tokenizer(text).input_ids) if tokenizer else None
    return dict(doc_id=doc_id, status="SUCCESS", section4_pattern=r["section4_pattern"],
                p_block_pattern=r["p_block_pattern"], cut_page=cut_page, char_count=len(text),
                token_count=n_tok, h_code_before=r["h_code_before"], h_code_after=r["h_code_after"],
                note=r["note"])


def _write(out_dir, sub, doc_id, text):
    target = os.path.join(out_dir, sub) if sub else out_dir
    os.makedirs(target, exist_ok=True)
    with open(os.path.join(target, f"{doc_id}.txt"), "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser(description="MSDS PDF 전처리")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/text")
    ap.add_argument("--sources", default="data/sources.csv", help="파일명 → doc_id 대응표")
    ap.add_argument("--ext", default=".pdf", help="입력 확장자 (.pdf 또는 .txt)")
    ap.add_argument("--no-token", action="store_true", help="토큰 수 측정 건너뛰기")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.raw, f"*{args.ext}")))
    if not paths:
        print(f"입력 파일이 없습니다: {args.raw}/*{args.ext}")
        return
    os.makedirs(args.out, exist_ok=True)
    tokenizer = None if args.no_token else load_tokenizer()

    doc_ids = load_doc_ids(args.sources)
    rows = [process(p, args.out, tokenizer, doc_ids) for p in paths]
    unmapped = [os.path.basename(p) for p in paths if os.path.basename(p) not in doc_ids]
    if unmapped:
        print(f"[경고] sources.csv에 없는 파일 {len(unmapped)}건은 파일명 그대로 저장: {unmapped}")
    log_path = os.path.join(args.out, "_cut_log.csv")
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:   # 엑셀 한글 대응
        w = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    counts = Counter(r["status"] for r in rows)
    print(f"\n총 {len(rows)}건 · " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"로그: {log_path}")

    warn = [r for r in rows if r["status"] != "SUCCESS"
            or r["note"]
            or r["h_code_before"] != r["h_code_after"]]
    if warn:
        print("\n확인이 필요한 문서")
        for r in warn:
            print(f"  {r['doc_id']:24s} {r['status']:10s} "
                  f"H {r['h_code_before']}→{r['h_code_after']}  {r['note']}")

    toks = [r["token_count"] for r in rows if r["token_count"]]
    if toks:
        toks.sort()
        pick = lambda p: toks[min(int(len(toks) * p / 100), len(toks) - 1)]  # noqa: E731
        print(f"\n토큰 길이  P50 {pick(50)} · P90 {pick(90)} · P95 {pick(95)} · MAX {toks[-1]}")
        print("→ 학습 max_length 결정에 사용 (출력 JSON 길이를 더해서 볼 것. 현재 configs: 4096)")


if __name__ == "__main__":
    main()
"""
[강덕우] P50/P90/P95/MAX → report/length_stats.md

  python pipeline/length_stats.py

train·val 문서만 잰다(test·test2 정답은 열지 않는다 — CLAUDE.md "Real Test 봉인").
실제 모델 입력과 같은 방식으로 센다: core/prompt.py의 build_messages()·format_target() + chat template(thinking 끔).

내는 것
  · 프롬프트(시스템+문서, few-shot 없음) · 정답 JSON · 합계 토큰의 P50/P90/P95/MAX와 최장 문서
  · base_fs 프롬프트(few-shot 2건 포함) 최장
  · 권장값: max_length ≥ 합계 MAX(학습 데이터 증강분은 build_jsonl 뒤 train_qlora가 따로 확인),
            max_new_tokens = 정답 MAX × 1.3 (plan.md 5장 디코딩 규칙)
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import CHAT_TEMPLATE_KWARGS, build_messages, format_target  # noqa: E402

SPLITS_CSV = ROOT / "data" / "splits.csv"
LABEL_DIR = ROOT / "data" / "labels"
TEXT_DIR = ROOT / "data" / "text"
FEWSHOT_JSON = ROOT / "eval" / "fewshot.json"
OUT = ROOT / "report" / "length_stats.md"
MEASURED_SPLITS = ("train", "val")  # 봉인 대상(test·test2)과 val_en은 재지 않는다


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p / 100))]


def main():
    import yaml
    from transformers import AutoTokenizer

    model = yaml.safe_load((ROOT / "pipeline" / "configs" / "r1.yaml").read_text(encoding="utf-8"))["model"]
    tok = AutoTokenizer.from_pretrained(model)
    n_tok = lambda msgs, gen: len(tok(tok.apply_chat_template(  # noqa: E731
        msgs, tokenize=False, add_generation_prompt=gen, **CHAT_TEMPLATE_KWARGS)).input_ids)

    with open(SPLITS_CSV, encoding="utf-8-sig", newline="") as f:
        docs = [(r["doc_id"], r["split"]) for r in csv.DictReader(f) if r["split"] in MEASURED_SPLITS]
    fs_ids = json.loads(FEWSHOT_JSON.read_text(encoding="utf-8")).get("fewshot_doc_ids", [])
    fewshot = [((TEXT_DIR / f"{d}.txt").read_text(encoding="utf-8"),
                json.loads((LABEL_DIR / f"{d}.json").read_text(encoding="utf-8"))) for d in fs_ids]

    rows, skipped = [], []
    for doc_id, split in sorted(docs):
        tp, lp = TEXT_DIR / f"{doc_id}.txt", LABEL_DIR / f"{doc_id}.json"
        if not tp.exists() or not lp.exists():
            skipped.append(f"{doc_id}({'텍스트' if not tp.exists() else '정답'} 없음)")
            continue
        text, label = tp.read_text(encoding="utf-8"), json.loads(lp.read_text(encoding="utf-8"))
        prompt = n_tok(build_messages(text), True)
        out = len(tok(format_target(label) + "<|im_end|>", add_special_tokens=False).input_ids)
        fs = n_tok(build_messages(text, fewshot), True)
        rows.append({"doc_id": doc_id, "split": split, "prompt": prompt, "output": out, "total": prompt + out, "fs": fs})

    if not rows:
        sys.exit("잴 문서가 없음")
    lines = ["# 입력+출력 토큰 분포  [강덕우]", "",
             f"`python pipeline/length_stats.py` · 토크나이저 {model} · train·val {len(rows)}건"
             f"(test·test2·val_en 제외) · 프롬프트는 시스템 프롬프트와 chat template 포함", "",
             "| 항목 | P50 | P90 | P95 | MAX | 최장 문서 |", "|---|---:|---:|---:|---:|---|"]
    for key, label in (("prompt", "프롬프트(zero-shot · QLoRA)"), ("output", "정답 JSON"),
                       ("total", "프롬프트 + 정답 (학습 1건)"), ("fs", "few-shot 프롬프트(base_fs)")):
        xs = [r[key] for r in rows]
        top = max(rows, key=lambda r: r[key])
        lines.append(f"| {label} | {pct(xs, 50)} | {pct(xs, 90)} | {pct(xs, 95)} | {max(xs)} | {top['doc_id']} |")

    max_out = max(r["output"] for r in rows)
    max_total = max(r["total"] for r in rows)
    rec_new = math.ceil(max_out * 1.3)
    rec_len = math.ceil(max_total * 1.1 / 256) * 256
    cfg_len = yaml.safe_load((ROOT / "pipeline" / "configs" / "r1.yaml").read_text(encoding="utf-8"))["max_length"]
    lines += ["", "## 권장값", "",
              f"- `max_new_tokens` = 정답 MAX {max_out} × 1.3 = **{rec_new}** (plan.md 5장 규칙). "
              f"`eval/infer.py` 기본값과 비교해 작으면 올린다.",
              f"- 학습 `max_length` ≥ 프롬프트 + 정답 MAX {max_total} (10% 여유 → {rec_len}). 현재 설정 {cfg_len}"
              f" → {'충분' if cfg_len >= max_total else '**부족 — 올리거나 초과 샘플을 목록화**'}. "
              "증강 뒤 길이는 `train_qlora.py`가 초과 샘플을 따로 알린다.",
              ""]
    if skipped:
        lines += [f"텍스트·정답이 없어 제외: {', '.join(skipped)}", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

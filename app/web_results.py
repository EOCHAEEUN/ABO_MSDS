"""
저장된 val 실험 결과 → 검토 화면(web/)용 JSON. docs/frontend_api_spec.md의 Document · CompareResult 모양을 따른다.

  python3 -m app.web_results                 # → web/public/results/documents.json · compare.json
  python3 -m app.web_results --root <폴더>   # 결과 파일을 다른 작업 폴더에서 읽을 때

- 입력: report/scores.csv, outputs/{조건}/val/({doc_id}.json · _log.jsonl · _run.jsonl), data/text/, data/splits.csv
- 모델 출력 원문을 파싱해 extraction으로 쓰고, Rule Engine(app/rules)을 돌려 핵심 5필드의 검토 상태를 붙인다.
- 파싱에 실패했거나 필수 키가 없는 출력은 목록에 넣지 않고 skipped에 사유와 함께 남긴다(조용히 버리지 않음).
- val만 다룬다. test는 저장소 밖이며 여기서 읽지 않는다.
나중에 app/main.py의 GET /documents · POST /compare가 같은 함수를 쓰면 된다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rules.engine import run_rules  # noqa: E402
from core.schema import extract_json  # noqa: E402

CONDITIONS = ("base_zs", "base_fs", "qlora_r1", "qlora_r2", "qlora_r3", "qlora_final")
LABEL = {"base_zs": ("Base Zero-shot", "Base ZS"), "base_fs": ("Base Few-shot (k=2)", "Base FS"),
         "qlora_r1": ("QLoRA r1", "QLoRA r1"), "qlora_r2": ("QLoRA r2", "QLoRA r2"),
         "qlora_r3": ("QLoRA r3", "QLoRA r3"),
         "qlora_final": ("QLoRA 최종", "QLoRA 최종")}
DOC_ORDER = ("qlora_final", "qlora_r3", "qlora_r2", "qlora_r1", "base_fs", "base_zs")  # 문서 목록 순서: 후보 모델 먼저
CORE_FIELDS = ("product_name", "ingredients", "ghs_classification", "signal_word", "hazard_statements")
SECTION = {"product_name": "1항 가.", "ingredients": "3항", "ghs_classification": "2항 가.",
           "signal_word": "2항 나.", "hazard_statements": "2항 나."}
REQUIRED_DICTS = ("product_name", "recommended_use", "use_restrictions", "supplier", "signal_word", "list_status")
REQUIRED_LISTS = ("ingredients", "ghs_classification", "hazard_statements")

# Rule Engine 검사 → plan 8절 · 화면 상태(OK · REVIEW_REQUIRED · SOURCE_CHECK_REQUIRED + 사유 코드)
FORMAT_CHECKS = {"schema", "cas", "hcode", "empty_value"}          # 검토 필요 · FORMAT_ERROR
CONSISTENCY_CHECKS = {"ghs_signal_hcode_consistency", "phrase_to_hcode"}  # 검토 필요 · INCONSISTENT
SOURCE_CHECKS = {"not_found", "content_sum"}                       # 원문 확인 필요
_TOP_FIELD = re.compile(r"^\$\.([a-z_]+)")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def _fmt_time(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    return datetime.fromisoformat(iso).strftime("%Y.%m.%d %H:%M")


def _top_field(path: Optional[str]) -> Optional[str]:
    m = _TOP_FIELD.match(path or "")
    return m.group(1) if m else None


def _lines_with(text: str, needles: list[str], prefer: Optional[str] = None) -> Optional[str]:
    """원문에서 값이 들어 있는 줄들(근거 표시용). prefer가 들어 있는 줄을 먼저 고른다."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    squash = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    picked: list[str] = []
    for n in needles:
        key = squash(n)
        if not key:
            continue
        hits = [l for l in lines if key in squash(l)]
        if prefer:
            hits.sort(key=lambda l: prefer not in l)
        if hits and hits[0] not in picked:
            picked.append(hits[0])
    return "\n".join(picked) or None


def field_rule_results(label: dict, source_text: Optional[str], doc_id: str) -> dict:
    """run_rules() 결과를 핵심 5필드별 {review_status, reason_code, page, section, source_text}로 바꾼다.
    page는 전처리 텍스트에 쪽 경계가 없어 null로 둔다."""
    rules = run_rules(label, source_text, doc_id)
    per: dict[str, list[dict]] = {f: [] for f in CORE_FIELDS}
    for f in rules["findings"]:
        top = _top_field(f.get("field"))
        if top in per and f["severity"] in ("error", "warning"):
            per[top].append(f)
    snippets: dict[str, list[str]] = {f: [] for f in CORE_FIELDS}
    for e in rules["evidence"]:
        top = _top_field(e["field"])
        if top in snippets and e["found"] and e.get("snippet") and e["snippet"] not in snippets[top]:
            snippets[top].append(e["snippet"].strip())

    out = {}
    for field in CORE_FIELDS:
        found = per[field]
        checks = {f["check"] for f in found}
        if checks & FORMAT_CHECKS:
            status, reason = "REVIEW_REQUIRED", "FORMAT_ERROR"
        elif checks & CONSISTENCY_CHECKS:
            status, reason = "REVIEW_REQUIRED", "INCONSISTENT"
        elif checks & SOURCE_CHECKS:
            status, reason = "SOURCE_CHECK_REQUIRED", None
        else:
            status, reason = "OK", None
        text = "\n".join(snippets[field][:4]) or None
        if text is None and source_text:  # 근거 대상이 아닌 필드(분류 · 신호어)는 값이 든 줄을 찾아 보여 준다
            if field == "ghs_classification":
                text = _lines_with(source_text, [c.get("hazard_class") or "" for c in label.get(field) or []][:6])
            elif field == "signal_word" and (label.get(field) or {}).get("value"):
                text = _lines_with(source_text, [label[field]["value"]], prefer="신호어")
        out[field] = {"review_status": status, "reason_code": reason, "page": None, "section": SECTION[field],
                      "source_text": text, "messages": [f["message"] for f in found][:5]}
    return out


def _missing_keys(obj: Any) -> list[str]:
    if not isinstance(obj, dict):
        return ["(JSON 객체 아님)"]
    return ([k for k in REQUIRED_DICTS if not isinstance(obj.get(k), dict)]
            + [k for k in REQUIRED_LISTS if not isinstance(obj.get(k), list)])


def build_documents(root: Path = ROOT) -> dict:
    splits = {r["doc_id"]: r for r in csv.DictReader(open(root / "data/splits.csv", encoding="utf-8-sig"))}
    sources = {}
    if (root / "data/sources.csv").exists():
        sources = {r["doc_id"]: r for r in csv.DictReader(open(root / "data/sources.csv", encoding="utf-8-sig"))}
    val_ids = sorted(d for d, r in splits.items() if r["split"] == "val")
    docs, skipped, n = [], [], 0
    for cond in DOC_ORDER:
        out_dir = root / "outputs" / cond / "val"
        if not (out_dir / "_run.jsonl").exists():
            continue
        name = LABEL[cond][0]
        log = {r["doc_id"]: r for r in _read_jsonl(out_dir / "_log.jsonl")}
        for doc_id in val_ids:
            rec = log.get(doc_id) or {}
            path = out_dir / f"{doc_id}.json"
            if rec.get("skipped") or not path.exists():
                skipped.append({"doc_id": doc_id, "condition": cond, "reason": rec.get("skipped") or "출력 파일 없음"})
                continue
            obj, err = extract_json(path.read_text(encoding="utf-8"))
            missing = _missing_keys(obj) if obj is not None else []
            if obj is None or missing:
                skipped.append({"doc_id": doc_id, "condition": cond,
                                "reason": str(err) if obj is None else f"필수 키 없음: {missing}"})
                continue
            text_path = root / "data" / "text" / f"{doc_id}.txt"
            text = text_path.read_text(encoding="utf-8") if text_path.exists() else None
            n += 1
            when = _fmt_time(rec.get("created_at"))
            docs.append({
                "id": f"{doc_id}__{cond}", "number": n, "doc_id": doc_id, "condition": cond,
                "file_name": sources.get(doc_id, {}).get("source_file") or f"{doc_id}.pdf",
                "language": "한국어" if splits[doc_id].get("lang") == "ko" else "영어",
                "page_count": None, "submission_number": doc_id, "revision_date": None,
                "extracted_at": when, "updated_at": when, "owner": "미지정",
                "split": f"val · {name}", "form": splits[doc_id].get("form"), "model_name": name,
                "generation_seconds": rec.get("gen_time_sec"), "output_tokens": rec.get("output_tokens"),
                "pdf_url": None, "source": None, "source_text": text,
                "extraction": obj, "reviews": {}, "confirmed_fields": [],
                "rule_results": field_rule_results(obj, text, doc_id),
            })
    stamp = hashlib.sha256(json.dumps(docs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return {"generated_from": "outputs/*/val · data/text · app/rules", "split": "val", "stamp": stamp,
            "n_val_docs": len(val_ids), "documents": docs, "skipped": skipped}


def _num(v: str) -> Optional[float]:
    return float(v) if v not in ("", None) else None


def build_compare(root: Path = ROOT) -> dict:
    scores: dict[str, dict[str, str]] = {}
    for r in csv.DictReader(open(root / "report/scores.csv", encoding="utf-8-sig")):
        if r["split"] == "val" and r["subset"] == "ko":
            scores.setdefault(r["condition"], {})[r["metric"]] = r["value"]
    runs = {c: _read_jsonl(root / "outputs" / c / "val" / "_run.jsonl")[:1] for c in CONDITIONS}
    exps, times = [], []
    for cond in CONDITIONS:
        s = scores.get(cond)
        if not s or not runs.get(cond):
            continue
        run = runs[cond][0]
        times.append(run.get("created_at"))
        if cond == "base_fs":
            condition = f"예시 2건(k=2): {' · '.join(run.get('fewshot_doc_ids') or [])}"
        elif cond.startswith("qlora"):
            cfg_path = root / Path(run.get("adapter") or "").parent / "config.json"
            c = json.loads(cfg_path.read_text(encoding="utf-8"))["config"] if cfg_path.exists() else {}
            condition = (f"LoRA r{c.get('lora_r', '?')} · lr {float(c.get('learning_rate', 0)):.0e} · {c.get('num_epochs', '?')} epoch".replace("e-0", "e-")
                         if c else "LoRA 어댑터")
        else:
            condition = "지시문 + 문서(예시 없음)"
        pct = lambda k: round(_num(s.get(k)) * 100, 1) if _num(s.get(k)) is not None else None  # noqa: E731
        exps.append({
            "id": cond, "name": LABEL[cond][0], "short": LABEL[cond][1], "condition": condition,
            "parsing": pct("parse_rate"), "schema": pct("schema_rate"), "cas": pct("cas_f1"), "pair": pct("pair_f1"),
            "hcode": pct("hcode_f1"), "seconds": round(_num(s["gen_time_mean_s"]), 1),
            "tokens": round(_num(s["output_tokens_mean"])),
            # 화면 명세의 7개 값 외 추가 지표(있을 때만 표시)
            "ghs": pct("ghs_f1"), "exact": pct("doc_exact_ext_rate"), "nocas": pct("nocas_f1"),
            "input_tokens": round(_num(s["input_tokens_mean"])), "n_docs": int(_num(s["n_docs"])),
            "base_revision": run.get("base_revision"), "max_new_tokens": run.get("max_new_tokens"),
        })
    return {"split": "val", "subset": "all", "executed_at": _fmt_time(max(t for t in times if t)) if times else None,
            "note": "val(조건 선택용) 결과이며 최종 보고 수치(test)가 아닙니다.", "experiments": exps}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(ROOT), help="결과 파일을 읽을 저장소 폴더(기본: 이 저장소)")
    ap.add_argument("--out", default=str(ROOT / "web" / "public" / "results"))
    args = ap.parse_args(argv)
    root, out = Path(args.root), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    docs, comp = build_documents(root), build_compare(root)
    (out / "documents.json").write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "compare.json").write_text(json.dumps(comp, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"documents {len(docs['documents'])}건 · 건너뜀 {len(docs['skipped'])}건 {docs['skipped']}")
    print(f"compare 실험 {[e['id'] for e in comp['experiments']]} · 실행 {comp['executed_at']} → {out}")


if __name__ == "__main__":
    main()

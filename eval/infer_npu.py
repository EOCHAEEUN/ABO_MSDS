"""
[NPU 트랙] OpenVINO IR 추론 (CPU · NPU · GPU 장치) — docs/npu_plan.md 4·6절

eval/infer.py(GPU, bitsandbytes NF4)의 짝이다. 입력 준비(split·전처리 텍스트·val 변형·few-shot)와
출력 형식은 eval/infer.py 것을 그대로 가져다 쓰고, 모델 로드·생성만 app/backends/ov_genai.py로 바꾼다.
채점은 기존 eval/score.py를 그대로 쓴다(--condition에 이 스크립트의 출력 폴더 이름).

  python eval/infer_npu.py --model runs/npu_r1/ov_int8   --device CPU --condition qlora_r1_ov_cpu_int8   --split val
  python eval/infer_npu.py --model runs/npu_r1/ov_int4cw --device NPU --condition qlora_r1_npu_int4cw --split val
  python eval/infer_npu.py --model runs/npu_r1/ov_int4cw --device NPU --condition qlora_r1_npu_int4cw --split val_var
  python eval/infer_npu.py --model runs/npu_base/ov_int4cw --device NPU --condition base_zs_npu_int4cw --split val
  → python eval/score.py --condition qlora_r1_npu_int4cw --split val
  → python eval/npu_compare.py --ref qlora_r1 --cand qlora_r1_npu_int4cw --split val

지키는 것
  - split은 val · val_var만. test · test2 · val_en · train은 거부한다(C안 게이트 밖이라 봉인 평가셋을 돌리지 않음)
  - 조건 이름은 base_zs_/base_fs_/qlora_<run>_ 로 시작하고 _ov_ 또는 _npu_ 를 포함해야 한다.
    eval/infer.py의 GPU 조건 이름(qlora_r1 등)과 같은 폴더를 쓰지 않는다
  - base_fs_*만 few-shot(eval/fewshot.json)을 넣는다. qlora_*는 export 기록이 qlora_merged인 모델만, base_*는 base 모델만
  - MAX_PROMPT_LEN을 넘는 문서는 자르지 않고 skipped="PROMPT_TOO_LONG"으로 남긴다(채점에서 실패로 셈)
  - 출력 폴더마다 첫 실행 설정을 _run.jsonl에 남기고, 이어 돌릴 때 설정이 다르면 거부(eval/gate.py check_resume)

출력: outputs/{condition}/{split}/{doc_id}.json — eval/infer.py와 같은 키 + device · ov_model · quant · ttft_sec ·
      throughput_tok_s · input_ids_sha256. 폴더에 _run.jsonl(실행 설정)과 _load.jsonl(로딩·컴파일 시간)
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import experiment, gate  # noqa: E402
from eval.infer import (  # noqa: E402
    CONDITIONS as GPU_CONDITIONS,
    base_doc,
    load_fewshot,
    read_cut_status,
    read_splits,
    text_path,
    variant_texts,
)
from core.prompt import build_messages  # noqa: E402

SPLITS = ("val", "val_var")
DEVICES = ("CPU", "NPU", "GPU")
DEFAULT_MAX_NEW_TOKENS = 1269  # report/length_stats.md 권장값, GPU val 8건 재평가와 같음
OUTPUT_ROOT = ROOT / "outputs"
COND_RE = re.compile(r"^(base_zs|base_fs|qlora_[a-z0-9]+)_[a-z0-9_]+$")


def check_condition(name, manifest):
    if name in GPU_CONDITIONS:
        sys.exit(f"[거부] {name}은 GPU 조건 이름 — NPU 출력은 다른 이름으로(예: {name}_npu_int4cw)")
    if not COND_RE.match(name) or not ("_ov_" in name or "_npu_" in name):
        sys.exit(f"[거부] 조건 이름 형식: base_zs_…/base_fs_…/qlora_<run>_… 에 _ov_ 또는 _npu_ 포함 (받음: {name})")
    kind = manifest["source"]["kind"]
    if name.startswith("qlora_") and kind != "qlora_merged":
        sys.exit(f"[거부] {name}은 QLoRA 조건인데 모델이 {kind}")
    if name.startswith("base_") and kind != "base":
        sys.exit(f"[거부] {name}은 Base 조건인데 모델이 {kind}")


def read_manifest(model_dir):
    """export_openvino.py가 남긴 {run}/export_{preset}.json"""
    model_dir = Path(model_dir)
    preset = model_dir.name.removeprefix("ov_")
    p = model_dir.parent / f"export_{preset}.json"
    if not p.exists():
        sys.exit(f"변환 기록 없음: {p} — pipeline/export_openvino.py로 만든 모델만 받는다")
    return json.loads(p.read_text(encoding="utf-8"))


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def run_record(args, manifest, fewshot_ids):
    """출력 폴더 하나를 만든 설정. 재개할 때 이 값이 같아야 한다(eval/gate.check_resume)"""
    src = manifest["source"]
    merge = src.get("merge", {})
    return {
        "condition": args.condition,
        "split": args.split,
        "device": args.device,
        "ov_model": manifest["ir_dir"],
        "ov_xml_sha256": manifest["ir_xml_sha256"],
        "ov_bin_sha256": manifest["ir_bin_sha256"],
        "quant": manifest["preset"],
        "source_kind": src["kind"],
        "base_model": src.get("base_model") or merge.get("base_model"),
        "adapter_sha256": merge.get("adapter_sha256"),
        "merge_mode": merge.get("mode"),
        "fewshot_doc_ids": list(fewshot_ids),
        "max_new_tokens": args.max_new_tokens,
        "max_prompt_len": args.max_prompt_len if args.device == "NPU" else None,
        "min_response_len": args.min_response_len if args.device == "NPU" else None,
        "prompt_sha256": experiment.sha(ROOT / gate.PROMPT_FILE),
        "ov_packages": manifest["packages"],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="OpenVINO IR 폴더 (runs/<run>/ov_<preset>)")
    ap.add_argument("--device", required=True, choices=DEVICES)
    ap.add_argument("--condition", required=True, help="출력 폴더 이름 (예: qlora_r1_npu_int4cw)")
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    ap.add_argument("--max-prompt-len", type=int, default=4096, help="NPU 정적 컴파일 입력 길이")
    ap.add_argument("--min-response-len", type=int, default=1280, help="NPU 정적 컴파일 출력 길이")
    ap.add_argument("--cache-dir", default=str(ROOT / "runs" / "_ov_cache"), help="NPU 컴파일 캐시")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--limit", type=int, help="앞에서 N건만(동작 점검용)")
    args = ap.parse_args()

    if args.device == "NPU" and args.min_response_len < args.max_new_tokens:
        sys.exit(f"--min-response-len({args.min_response_len})이 --max-new-tokens({args.max_new_tokens})보다 작음")
    manifest = read_manifest(args.model)
    check_condition(args.condition, manifest)

    splits = read_splits()
    var = variant_texts() if args.split == "val_var" else {}
    doc_ids = sorted(var) if var else sorted(d for d, r in splits.items() if r["split"] == args.split)
    if args.limit:
        doc_ids = doc_ids[: args.limit]
    cut = read_cut_status()
    fewshot_ids, fewshot = load_fewshot(splits) if args.condition.startswith("base_fs") else ([], [])
    out_dir = OUTPUT_ROOT / args.condition / args.split

    missing = [d for d in doc_ids if not var and cut.get(d) != "NOT_FOUND" and not text_path(d).exists()]
    if missing:
        sys.exit(f"전처리 텍스트 없음 {len(missing)}건: {missing}\n→ pipeline/extract_text.py를 먼저 돌릴 것")
    run = run_record(args, manifest, fewshot_ids)
    gate.check_resume(out_dir, run, doc_ids, args.overwrite, partial=bool(args.limit))
    todo = [d for d in doc_ids if args.overwrite or not (out_dir / f"{d}.json").exists()]
    if not todo:
        print(f"할 일 없음: {out_dir.relative_to(ROOT)}에 {len(doc_ids)}건 모두 있음(다시 돌리려면 --overwrite)")
        return

    from app.backends.ov_genai import OVGenAIRunner, PromptTooLong

    print(f"[{args.condition} / {args.split}] {len(todo)}/{len(doc_ids)}건, model={args.model}, device={args.device}")
    runner = OVGenAIRunner(args.model, args.device, args.max_prompt_len, args.min_response_len,
                           args.cache_dir if args.device == "NPU" else None)
    runner.generate([{"role": "user", "content": "warm-up"}], 8)  # 첫 문서 시간에 컴파일·초기화가 섞이지 않게
    with open(out_dir / "_load.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"load_sec": round(runner.load_sec, 1), "device": args.device, "props": runner.props,
                            "git_commit": git_commit(), "at": datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")

    for n, doc_id in enumerate(todo, 1):
        rec = {
            "doc_id": doc_id,
            "condition": args.condition,
            "split": args.split,
            "raw_output": None,
            "gen_time_sec": None,
            "input_tokens": None,
            "output_tokens": None,
            "hit_max_new_tokens": False,
            "skipped": None,
            "base_model": run["base_model"],
            "adapter": None,
            "fewshot_doc_ids": fewshot_ids,
            "max_new_tokens": args.max_new_tokens,
            "device": args.device,
            "ov_model": run["ov_model"],
            "quant": run["quant"],
            "ttft_sec": None,
            "throughput_tok_s": None,
            "input_ids_sha256": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        if cut.get(base_doc(doc_id)) == "NOT_FOUND":
            rec["skipped"] = "NOT_FOUND"
            print(f"  ({n}/{len(todo)}) {doc_id}  건너뜀: _cut_log NOT_FOUND")
        else:
            text = var[doc_id] if var else text_path(doc_id).read_text(encoding="utf-8")
            try:
                raw, sec, n_in, n_out = runner.generate(build_messages(text, fewshot), args.max_new_tokens)
            except PromptTooLong as e:
                rec["skipped"] = "PROMPT_TOO_LONG"
                rec["input_tokens"] = len(runner.encode(build_messages(text, fewshot)))
                print(f"  ({n}/{len(todo)}) {doc_id}  건너뜀: {e}")
            else:
                rec.update(raw_output=raw, gen_time_sec=round(sec, 3), input_tokens=n_in, output_tokens=n_out,
                           hit_max_new_tokens=n_out >= args.max_new_tokens, **runner.last)
                flag = "  ← max_new_tokens 도달(잘렸을 수 있음)" if rec["hit_max_new_tokens"] else ""
                print(f"  ({n}/{len(todo)}) {doc_id}  {sec:.1f}s  in={n_in} out={n_out}{flag}")
        (out_dir / f"{doc_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료 → {out_dir.relative_to(ROOT)}   다음: python eval/score.py --condition {args.condition} --split {args.split}")


if __name__ == "__main__":
    main()

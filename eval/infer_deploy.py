"""
배포 변형 추론 — 병합본 등 로컬 모델 폴더를 infer.py와 같은 조건(입력 · 프롬프트 · greedy · 생성 한도 ·
베이스 토크나이저)으로 val에 돌린다. docs/deploy_quant_plan.md 6절 · report/decisions.md 2026-09-30 병합본 항목.

본 비교군이 아니다. 조건 이름은 deploy_로 시작하고, test는 거부한다. 출력 형식은 infer.py와 같아 score.py가 그대로 채점한다.
  outputs/deploy/{condition}/val/{doc_id}.json   모델 출력 원문(파싱 실패도 그대로)
  outputs/deploy/{condition}/val/_log.jsonl      문서별 시간 · 토큰 · 최대 GPU 메모리
  outputs/deploy/{condition}/val/_run.jsonl      모델 폴더 · 가중치 해시 · 불러온 방식 · 프롬프트 · 입력 해시

  python3 eval/infer_deploy.py --condition deploy_r1_merged_nf4 --model-dir runs/deploy_r1/merged_nf4dq --load nf4 \
                               --text-dir runs/deploy/text_r1      # r1 val 기록과 같은 입력(inputs_sha256 6536e4c4…)
  python3 eval/score.py --condition deploy_r1_merged_nf4 --split val --out-root outputs/deploy \
                        --scores-csv report/deploy/scores_deploy.csv
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import DEFAULT_PROMPT, build_messages, prompt_sha256  # noqa: E402
from eval.infer import (  # noqa: E402
    DEFAULT_MAX_NEW_TOKENS,
    SPLITS_CSV,
    TEXT_DIR,
    append_log,
    base_model_spec,
    check_resume,
    generate,
    inputs_digest,
    now,
    read_cut_status,
    read_splits,
)

OUT_ROOT = ROOT / "outputs" / "deploy"


def sha256_file(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def load(model_dir, how):
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    kw = {"device_map": {"": 0}, "dtype": torch.bfloat16}
    if how == "nf4":  # infer.load_model과 같은 NF4 설정
        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                       bnb_4bit_use_double_quant=True,
                                                       bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(model_dir, **kw)
    model.eval()
    return model


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--condition", required=True, help="deploy_로 시작")
    ap.add_argument("--model-dir", required=True, help="로컬 모델 폴더(병합본 등)")
    ap.add_argument("--load", choices=("nf4", "bf16"), default="nf4", help="불러올 때 NF4로 양자화할지(8GB GPU는 nf4)")
    ap.add_argument("--split", choices=("val",), default="val", help="val만(test 거부)")
    ap.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    ap.add_argument("--text-dir", default=TEXT_DIR,
                    help="1~3항 텍스트 폴더. 기존 비교군과 비교할 때는 그 비교군의 입력(_run.jsonl inputs_sha256)과 같은 폴더를 준다")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--out-root", default=OUT_ROOT)
    args = ap.parse_args(argv)
    if not args.condition.startswith("deploy_"):
        sys.exit("[거부] 배포 변형의 조건 이름은 deploy_로 시작한다(본 비교군과 섞지 않게)")

    model_dir = Path(args.model_dir)
    weights = sorted(model_dir.glob("*.safetensors"))
    if not weights:
        sys.exit(f"가중치 파일 없음: {model_dir}")
    merge_info = next((json.loads(p.read_text(encoding="utf-8")) for p in model_dir.glob("merge_*.json")), None)

    splits = read_splits(SPLITS_CSV)
    all_ids = sorted(d for d, r in splits.items() if r["split"] == args.split)
    doc_ids = all_ids[: args.limit] if args.limit else all_ids
    text_dir = Path(args.text_dir)
    cut = read_cut_status(text_dir)
    out_dir = Path(args.out_root) / args.condition / args.split
    base_name, revision = base_model_spec(None, None)  # 토크나이저는 r1과 같은 베이스 스냅샷
    print(f"가중치 해시 계산 중: {[p.name for p in weights]}")
    run = {
        "condition": args.condition, "split": args.split, "model_dir": str(model_dir),
        "weights_sha256": {p.name: sha256_file(p) for p in weights}, "merge_info": merge_info,
        "load": args.load, "tokenizer": f"{base_name}@{revision}", "max_new_tokens": args.max_new_tokens,
        "fewshot_doc_ids": [], "prompt_version": DEFAULT_PROMPT, "prompt_text_sha256": prompt_sha256(DEFAULT_PROMPT),
        "text_dir": str(text_dir), "n_docs": len(all_ids), "inputs_sha256": inputs_digest(all_ids, text_dir, cut),
    }
    check_resume(out_dir, run)
    todo = [d for d in doc_ids if args.overwrite or not (out_dir / f"{d}.json").exists()]
    if not todo:
        print(f"할 일 없음: {out_dir}")
        return

    import torch
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(base_name, revision=revision)
    print(f"[{args.condition}] {model_dir} 불러오는 중(load={args.load})")
    model = load(model_dir, args.load)
    print(f"가중치 적재 후 GPU 메모리 {torch.cuda.memory_allocated() / 2**30:.2f} GiB")
    generate(tok, model, [{"role": "user", "content": "warm-up"}], 8)  # CUDA 초기화 시간이 첫 문서에 섞이지 않게

    for n, doc_id in enumerate(todo, 1):
        rec = {"doc_id": doc_id, "skipped": None, "gen_time_sec": None, "input_tokens": None, "output_tokens": None,
               "hit_max_new_tokens": False, "peak_gpu_gib": None, "created_at": now()}
        if cut.get(doc_id) == "NOT_FOUND":
            rec["skipped"] = "NOT_FOUND"
            (out_dir / f"{doc_id}.json").unlink(missing_ok=True)
        else:
            torch.cuda.reset_peak_memory_stats()
            text = (text_dir / f"{doc_id}.txt").read_text(encoding="utf-8")
            raw, sec, n_in, n_out = generate(tok, model, build_messages(text, prompt=DEFAULT_PROMPT), args.max_new_tokens)
            rec.update(gen_time_sec=round(sec, 3), input_tokens=n_in, output_tokens=n_out,
                       hit_max_new_tokens=n_out >= args.max_new_tokens,
                       peak_gpu_gib=round(torch.cuda.max_memory_allocated() / 2**30, 3))
            (out_dir / f"{doc_id}.json").write_text(raw, encoding="utf-8")
            print(f"  ({n}/{len(todo)}) {doc_id}  {sec:.1f}s  in={n_in} out={n_out}  "
                  f"{sec / max(n_out, 1) * 1000:.1f} ms/tok  peak {rec['peak_gpu_gib']} GiB", flush=True)
        append_log(out_dir, rec)
    print(f"완료 → {out_dir}\n다음: python3 eval/score.py --condition {args.condition} --split {args.split} "
          f"--out-root {args.out_root} --scores-csv report/deploy/scores_deploy.csv")


if __name__ == "__main__":
    main()

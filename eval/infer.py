
"""
[양세윤] 조건(base_zs/base_fs/qlora_*) × split(val/test/val_en) 추론
--split test는 명시 플래그 없이는 실행 거부

세 조건 모두 같은 런타임(Transformers, 4bit NF4)·같은 입력·thinking 끔·greedy로 돌린다.
파싱·스키마 검사·채점은 하지 않는다 → eval/score.py

출력: outputs/{condition}/{split}/{doc_id}.json
  {"doc_id", "condition", "split", "raw_output", "gen_time_sec", "input_tokens", "output_tokens",
   "hit_max_new_tokens", "skipped", "base_model", "adapter", "fewshot_doc_ids", "max_new_tokens", "created_at"}
  - raw_output: 모델이 낸 문자열 그대로(파싱 전)
  - skipped: _cut_log.csv에서 NOT_FOUND인 문서는 모델에 넣지 않고 "NOT_FOUND"로 기록(채점에선 실패로 셈)
  - 이미 출력 파일이 있으면 건너뛴다(중단 후 이어 돌리기). 다시 돌리려면 --overwrite(test는 불가)

  python eval/infer.py --condition base_zs --split val
  python eval/infer.py --condition base_fs --split val
  python eval/infer.py --condition qlora_r1 --split val --adapter runs/0924_r1/adapter
  python eval/infer.py --condition qlora_final --split test --adapter runs/0925_r2/adapter --allow-test

Test 규칙(README): 봉인(eval/seal.py --write) 뒤에만, base_zs / base_fs / qlora_final 각 1회.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import CHAT_TEMPLATE_KWARGS, build_messages  # noqa: E402
from eval.seal import verify as verify_seal  # noqa: E402

CONDITIONS = ("base_zs", "base_fs", "qlora_r1", "qlora_r2", "qlora_final")
TEST_CONDITIONS = ("base_zs", "base_fs", "qlora_final")
SPLITS = ("val", "test", "val_en", "train")  # train: Base 난이도 진단 전용(few-shot 예시 제외, 보고 금지)

TEXT_DIR = ROOT / "data" / "text"
CUT_LOG = TEXT_DIR / "_cut_log.csv"
SPLITS_CSV = ROOT / "data" / "splits.csv"
LABEL_DIR = ROOT / "data" / "labels"
FEWSHOT_JSON = ROOT / "eval" / "fewshot.json"
DEFAULT_CONFIG = ROOT / "pipeline" / "configs" / "r1.yaml"
OUTPUT_ROOT = ROOT / "outputs"


# ---------------------------------------------------------------- 입력 준비
def read_splits():
    with open(SPLITS_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r for r in csv.DictReader(f)}


def read_cut_status():
    if not CUT_LOG.exists():
        return {}
    with open(CUT_LOG, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r["status"] for r in csv.DictReader(f) if r.get("doc_id")}


def text_path(doc_id):
    return TEXT_DIR / f"{doc_id}.txt"


def load_fewshot(splits):
    """eval/fewshot.json의 train 문서 2건 → [(텍스트, 정답 dict), ...]"""
    ids = json.loads(FEWSHOT_JSON.read_text(encoding="utf-8")).get("fewshot_doc_ids", [])
    if len(ids) != 2:
        sys.exit(f"eval/fewshot.json의 fewshot_doc_ids는 2건이어야 함(현재 {ids}). 후보: KR-NOROO-004, KR-KUMHO-002")
    for doc_id in ids:
        if splits.get(doc_id, {}).get("split") != "train":
            sys.exit(f"few-shot 예시는 train 문서만 쓸 수 있음: {doc_id}")
        if not text_path(doc_id).exists():
            sys.exit(f"few-shot 예시 텍스트 없음: {text_path(doc_id)}")
    pairs = [
        (text_path(d).read_text(encoding="utf-8"), json.loads((LABEL_DIR / f"{d}.json").read_text(encoding="utf-8")))
        for d in ids
    ]
    return ids, pairs


def fewshot_ids_in_file():
    return set(json.loads(FEWSHOT_JSON.read_text(encoding="utf-8")).get("fewshot_doc_ids", []))


def base_model_name(arg):
    if arg:
        return arg
    import yaml

    return yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))["model"]


# ---------------------------------------------------------------- 모델
def load_model(base_name, adapter):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    tok = AutoTokenizer.from_pretrained(base_name)
    model = AutoModelForCausalLM.from_pretrained(
        base_name, quantization_config=bnb, device_map="auto", torch_dtype=torch.bfloat16
    )
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return tok, model


def generate(tok, model, messages, max_new_tokens):
    """→ (출력 문자열, 생성 시간 초, 입력 토큰 수, 출력 토큰 수)"""
    import torch

    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **CHAT_TEMPLATE_KWARGS)
    enc = tok(prompt, return_tensors="pt").to(model.device)
    n_in = int(enc["input_ids"].shape[1])
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id

    if torch.cuda.is_available():
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.inference_mode():
        out = model.generate(
            **enc,
            max_new_tokens=max_new_tokens,
            do_sample=False,  # greedy
            temperature=None,  # 모델 generation_config의 샘플링 값 무시
            top_p=None,
            top_k=None,
            pad_token_id=pad_id,
        )
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - t0

    new_tokens = out[0, n_in:]
    return tok.decode(new_tokens, skip_special_tokens=True), elapsed, n_in, int(new_tokens.shape[0])


# ---------------------------------------------------------------- 실행
def check_args(args):
    if args.condition.startswith("qlora") and not args.adapter:
        sys.exit(f"{args.condition}에는 --adapter(어댑터 폴더)가 필요함")
    if args.condition.startswith("base") and args.adapter:
        sys.exit(f"{args.condition}은 베이스 모델 조건이라 --adapter를 줄 수 없음")
    if args.adapter and not Path(args.adapter).exists():
        sys.exit(f"어댑터 폴더 없음: {args.adapter}")
    if args.split == "train" and not args.condition.startswith("base"):
        sys.exit("[거부] train은 Base 난이도 진단 전용. 학습한 모델을 학습 문서로 채점하는 건 의미가 없음")
    if args.split == "test":
        if not args.allow_test:
            sys.exit("[거부] Real Test는 모델 고정 전 사용 금지. 고정 후 최종 평가라면 --allow-test를 붙일 것")
        if args.condition not in TEST_CONDITIONS:
            sys.exit(f"[거부] Test는 {TEST_CONDITIONS}만 돌린다(1·2차 비교는 val로)")
        if args.overwrite:
            sys.exit("[거부] Test는 조건당 1회만 돈다. --overwrite 불가")
        ok, msg = verify_seal()
        if not ok:
            sys.exit(f"[거부] Test 봉인 대조 실패: {msg}")
        print(msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--condition", required=True, choices=CONDITIONS)
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--adapter", help="qlora_* 조건의 LoRA 어댑터 폴더")
    ap.add_argument("--base", help="베이스 모델 이름(기본: pipeline/configs/r1.yaml의 model)")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--allow-test", action="store_true", help="Real Test 추론 허용(모델 고정·봉인 후에만)")
    ap.add_argument("--overwrite", action="store_true", help="이미 있는 출력도 다시 생성(val·val_en만)")
    ap.add_argument("--limit", type=int, help="앞에서 N건만(동작 점검용)")
    args = ap.parse_args()
    check_args(args)

    splits = read_splits()
    doc_ids = sorted(d for d, r in splits.items() if r["split"] == args.split)
    if args.split == "train":  # few-shot 예시는 base_fs가 정답을 보고 푸는 셈이라 두 조건 모두에서 뺀다
        doc_ids = [d for d in doc_ids if d not in fewshot_ids_in_file()]
    if args.limit:
        doc_ids = doc_ids[: args.limit]
    cut = read_cut_status()

    # 모델을 올리기 전에 입력부터 전부 확인(모델 로딩에 1분 넘게 걸림)
    missing = [d for d in doc_ids if cut.get(d) != "NOT_FOUND" and not text_path(d).exists()]
    if missing:
        sys.exit(f"전처리 텍스트 없음 {len(missing)}건: {missing}\n→ pipeline/extract_text.py를 먼저 돌릴 것")
    fewshot_ids, fewshot = load_fewshot(splits) if args.condition == "base_fs" else ([], [])

    out_dir = OUTPUT_ROOT / args.condition / args.split
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [d for d in doc_ids if args.overwrite or not (out_dir / f"{d}.json").exists()]
    if not todo:
        print(f"할 일 없음: {out_dir.relative_to(ROOT)}에 {len(doc_ids)}건 모두 있음(다시 돌리려면 --overwrite)")
        return

    base_name = base_model_name(args.base)
    print(f"[{args.condition} / {args.split}] {len(todo)}/{len(doc_ids)}건, base={base_name}, adapter={args.adapter}")
    tok, model = load_model(base_name, args.adapter)
    generate(tok, model, [{"role": "user", "content": "warm-up"}], 8)  # CUDA 초기화 시간이 첫 문서 속도에 섞이지 않게

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
            "base_model": base_name,
            "adapter": args.adapter,
            "fewshot_doc_ids": fewshot_ids,
            "max_new_tokens": args.max_new_tokens,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        if cut.get(doc_id) == "NOT_FOUND":
            rec["skipped"] = "NOT_FOUND"
            print(f"  ({n}/{len(todo)}) {doc_id}  건너뜀: _cut_log NOT_FOUND")
        else:
            messages = build_messages(text_path(doc_id).read_text(encoding="utf-8"), fewshot)
            raw, sec, n_in, n_out = generate(tok, model, messages, args.max_new_tokens)
            rec.update(
                raw_output=raw,
                gen_time_sec=round(sec, 3),
                input_tokens=n_in,
                output_tokens=n_out,
                hit_max_new_tokens=n_out >= args.max_new_tokens,
            )
            flag = "  ← max_new_tokens 도달(잘렸을 수 있음)" if rec["hit_max_new_tokens"] else ""
            print(f"  ({n}/{len(todo)}) {doc_id}  {sec:.1f}s  in={n_in} out={n_out}{flag}")
        (out_dir / f"{doc_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료 → {out_dir.relative_to(ROOT)}   다음: python eval/score.py --condition {args.condition} --split {args.split}")


if __name__ == "__main__":
    main()
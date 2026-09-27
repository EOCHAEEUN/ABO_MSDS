
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
  - 출력 폴더마다 첫 실행 설정을 _run.jsonl에 남기고, 이어 돌릴 때 설정(어댑터 해시·Base 리비전·few-shot·
    생성 길이·프롬프트)이 다르면 거부한다(eval/gate.py)
  - test·test2는 eval/gate.py의 게이트를 통과해야 돈다: --allow-test · 봉인 대조 · eval/experiment.json 고정 ·
    비교군 4개 · 고정된 조건 정의와 같은 설정. --max-new-tokens를 생략하면 고정값을 쓴다

  python eval/infer.py --condition base_zs --split val
  python eval/infer.py --condition base_fs --split val
  python eval/infer.py --condition qlora_r1 --split val --adapter runs/0924_r1/adapter
  python eval/infer.py --condition qlora_final --split test2 --adapter runs/MMDD_c1/adapter --allow-test

Test 규칙: 봉인(eval/seal.py) · 실험 고정(eval/experiment.py --freeze) 뒤에만, 비교군 4개 각 1회.
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
from eval import experiment, gate  # noqa: E402

CONDITIONS = ("base_zs", "base_fs", "qlora_r1", "qlora_r2", "qlora_c1", "qlora_c2", "qlora_final",
              "qlora_cv_r1", "qlora_cv_r2")
# test·test2 비교군은 eval/experiment.json의 conditions(C안 6절: base_zs · base_fs · qlora_r1 · qlora_final)
SPLITS = ("val", "test", "val_en", "train", "val_var", "test2")  # test2: C안 새 독립 test(eval/test2/, 봉인)
# train: Base 난이도 진단·교차검증 전용(few-shot 예시 제외, 보고 금지)
# val_var: data/val.jsonl의 형식 변형(원본 제외). 출력 이름 {doc_id}__{변형}. 독립 문서 성능으로 보고하지 않는다

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


VAL_JSONL = ROOT / "data" / "val.jsonl"


def variant_texts():
    """data/val.jsonl의 형식 변형 입력 → {"{doc_id}__{변형}": 1~3항 텍스트}. 원본(orig)은 val split에서 이미 돈다."""
    out = {}
    for line in VAL_JSONL.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["variant"] == "orig":
            continue
        user = r["messages"][-2]["content"]
        out[f"{r['doc_id']}__{r['variant']}"] = user.split("<MSDS>\n", 1)[1].rsplit("\n</MSDS>", 1)[0]
    return out


def base_doc(key):
    return key.split("__", 1)[0]


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
    if args.split == "train" and not (args.condition.startswith("base") or args.condition.startswith("qlora_cv")):
        sys.exit("[거부] train은 Base 진단·교차검증 전용. 학습한 모델을 학습 문서로 채점하는 건 의미가 없음")
    if args.condition.startswith("qlora_cv"):
        if args.split != "train" or not args.holdout:
            sys.exit("[거부] qlora_cv*는 --split train --holdout 그룹 으로만 돈다(그 그룹을 빼고 학습한 어댑터로 그 그룹만 추론)")
        cfg = json.loads((Path(args.adapter).parent / "config.json").read_text(encoding="utf-8"))
        if cfg.get("holdout_group") != args.holdout:
            sys.exit(f"[거부] 어댑터가 뺀 그룹({cfg.get('holdout_group')})과 --holdout({args.holdout})이 다름 — 학습에 쓴 문서를 평가하게 됨")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--condition", required=True, choices=CONDITIONS)
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--adapter", help="qlora_* 조건의 LoRA 어댑터 폴더")
    ap.add_argument("--base", help="베이스 모델 이름(기본: pipeline/configs/r1.yaml의 model)")
    ap.add_argument("--max-new-tokens", type=int, help="기본: test·test2는 eval/experiment.json 고정값, 그 밖은 1024")
    ap.add_argument("--allow-test", action="store_true", help="Real Test 추론 허용(모델 고정·봉인 후에만)")
    ap.add_argument("--overwrite", action="store_true", help="이미 있는 출력도 다시 생성(val·val_en만)")
    ap.add_argument("--limit", type=int, help="앞에서 N건만(동작 점검용)")
    ap.add_argument("--holdout", help="qlora_cv*: 어댑터가 학습에서 뺀 split_group(여러 개는 +로). 그 그룹 문서만 추론")
    args = ap.parse_args()
    check_args(args)
    if args.max_new_tokens is None:
        args.max_new_tokens = experiment.load()["common"]["max_new_tokens"] if gate.sealed(args.split) else 1024

    splits = read_splits()
    doc_ids = sorted(d for d, r in splits.items() if r["split"] == args.split)
    var = variant_texts() if args.split == "val_var" else {}
    if var:
        doc_ids = sorted(var)
    if args.split == "train":  # few-shot 예시는 base_fs가 정답을 보고 푸는 셈이라 두 조건 모두에서 뺀다
        doc_ids = [d for d in doc_ids if d not in fewshot_ids_in_file()]
    if args.holdout:
        doc_ids = [d for d in doc_ids if splits[d]["split_group"] in args.holdout.split("+")]
    if args.limit:
        doc_ids = doc_ids[: args.limit]
    cut = read_cut_status()
    fewshot_ids, fewshot = load_fewshot(splits) if args.condition == "base_fs" else ([], [])
    base_name = base_model_name(args.base)
    out_dir = OUTPUT_ROOT / args.condition / args.split

    # test·test2는 다른 무엇보다 먼저 게이트(eval/gate.py). 그 밖의 split은 검사 없이 통과
    run = gate.run_record(args.condition, args.split, base_name, args.adapter, fewshot_ids, args.max_new_tokens)
    gate.gate_generate(args.split, args.condition, run, args.allow_test, args.overwrite, args.limit)

    # 모델을 올리기 전에 입력부터 전부 확인(모델 로딩에 1분 넘게 걸림)
    missing = [d for d in doc_ids if not var and cut.get(d) != "NOT_FOUND" and not text_path(d).exists()]
    if missing:
        sys.exit(f"전처리 텍스트 없음 {len(missing)}건: {missing}\n→ pipeline/extract_text.py를 먼저 돌릴 것")
    # 이어 돌리기: 앞선 실행과 설정(어댑터 해시·리비전·few-shot·생성 길이·프롬프트)이 같아야 함
    gate.check_resume(out_dir, run, doc_ids, args.overwrite, partial=bool(args.limit))
    todo = [d for d in doc_ids if args.overwrite or not (out_dir / f"{d}.json").exists()]
    if not todo:
        print(f"할 일 없음: {out_dir.relative_to(ROOT)}에 {len(doc_ids)}건 모두 있음(다시 돌리려면 --overwrite)")
        return

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
        if cut.get(base_doc(doc_id)) == "NOT_FOUND":
            rec["skipped"] = "NOT_FOUND"
            print(f"  ({n}/{len(todo)}) {doc_id}  건너뜀: _cut_log NOT_FOUND")
        else:
            text = var[doc_id] if var else text_path(doc_id).read_text(encoding="utf-8")
            messages = build_messages(text, fewshot)
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
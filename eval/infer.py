"""
[양세윤] 조건(base_zs/base_fs/qlora_*) × split(val/test) 추론
--split test는 명시 플래그 없이는 실행 거부

세 조건 모두 같은 런타임(Transformers, 4bit NF4)·같은 입력·thinking 끔·greedy로 돌린다.
파싱·스키마 검사·채점은 하지 않는다 → eval/score.py

출력 (CLAUDE.md 규약)
  outputs/{condition}/{split}/{doc_id}.json   모델이 낸 문자열 그대로. 파싱에 실패해도 그대로 저장해 실패로 센다
  outputs/{condition}/{split}/_log.jsonl      문서별 시간·입출력 토큰·max_new_tokens 도달 여부·건너뛴 사유
  outputs/{condition}/{split}/_run.jsonl      첫 실행 설정(베이스·어댑터·few-shot·생성 길이·프롬프트 해시)
  - _cut_log.csv에서 NOT_FOUND인 문서는 모델에 넣지 않고 _log.jsonl에 skipped로 남긴다(채점에선 실패로 셈)
  - 이미 출력 파일이 있으면 건너뛴다(중단 후 이어 돌리기). 다시 돌리려면 --overwrite(test는 불가)
  - 이어 돌릴 때 설정이 _run.jsonl과 다르면 거부한다(한 폴더에 두 모델의 출력이 섞이지 않게)

  python3 eval/infer.py --condition base_zs --split val
  python3 eval/infer.py --condition base_fs --split val
  python3 eval/infer.py --condition qlora_r1 --split val --adapter runs/MMDD_r1/adapter
  # 코드 점검(fixture, 옛 라벨): --splits test/fixtures/splits.csv --text-dir test/fixtures/text --out-root /tmp/x

test 규칙 (docs/plan.md 3.3 · 9절 단계 7~8)
  test 문서·텍스트는 저장소 밖(test 담당)에 있다. --allow-test + 실험 고정(eval/experiment.json) +
  저장소 밖 --text-dir이 모두 있어야 돈다. 비교군마다 1회, --overwrite · --limit 불가.
"""
import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import CHAT_TEMPLATE_KWARGS, build_messages  # noqa: E402

CONDITIONS = ("base_zs", "base_fs", "qlora_r1", "qlora_r2", "qlora_final")
SPLITS = ("val", "train", "val_en", "test")  # train: Base 난이도 진단 전용(few-shot 예시 제외, 보고 금지)

SPLITS_CSV = ROOT / "data" / "splits.csv"
TEXT_DIR = ROOT / "data" / "text"
LABEL_DIR = ROOT / "data" / "labels"
FEWSHOT_JSON = ROOT / "eval" / "fewshot.json"
EXPERIMENT_JSON = ROOT / "eval" / "experiment.json"  # 단계 7(모델·실험 고정)에서 PM이 커밋
DEFAULT_CONFIG = ROOT / "pipeline" / "configs" / "r1.yaml"
OUTPUT_ROOT = ROOT / "outputs"
PROMPT_FILE = ROOT / "core" / "prompt.py"
DEFAULT_MAX_NEW_TOKENS = 2048
# 실험 고정 전 임시값(2026-09-28, docs/plan.md 6절 "생성 길이 부족" 참고).
# - 진짜 고정값은 train·val 정답 최장 토큰 × 1.3이다. 새 라벨이 나오면 pipeline/length_stats.py로 재서
#   eval/experiment.json에 채우고 실험을 고정한다(단계 7). 그 전까지 이 상수는 val·train 진단에만 쓰인다
#   (test는 이 상수를 쓰지 않는다 — 위 264행).
# - 1024는 부족했다: fixture 문서(KR-HENKEL-001, 입력 2,141토큰)가 1024에서 잘려 JSON이 깨졌다. 옛 라벨
#   기준 정답 최장이 약 975토큰이라 × 1.3 ≈ 1,268이었는데도 1024로는 못 미친 사례라, 여유를 더 둔다.
# - 4096(=r1.yaml의 max_length)을 그대로 쓰지 않는다. max_length는 학습 때 입력+정답 합계 길이의 상한이고,
#   max_new_tokens는 추론 때 새로 생성하는 토큰 수만의 상한이라 용도가 다르다. EOS 없이 도는 실패 사례가
#   나오면 이 값까지 다 채우고서야 멈추므로, 진단 단계(실패가 잦을 수 있는 구간)에서 4096은 문서당 생성
#   시간을 크게 늘릴 위험이 있다. 2048은 1024보다 넉넉하면서 그 위험을 줄인 절충값이다.

LOG_FILE = "_log.jsonl"
RUN_FILE = "_run.jsonl"


# ---------------------------------------------------------------- 입력 준비
def read_splits(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r for r in csv.DictReader(f)}


def read_cut_status(text_dir):
    cut_log = Path(text_dir) / "_cut_log.csv"
    if not cut_log.exists():
        return {}
    with open(cut_log, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r["status"] for r in csv.DictReader(f) if r.get("doc_id")}


def fewshot_ids_in_file():
    return json.loads(FEWSHOT_JSON.read_text(encoding="utf-8")).get("fewshot_doc_ids", [])


def load_fewshot(splits, text_dir, label_dir):
    """eval/fewshot.json의 train 문서 2건 → (ids, [(텍스트, 정답 dict), ...])"""
    ids = fewshot_ids_in_file()
    if len(ids) != 2:
        sys.exit(f"eval/fewshot.json의 fewshot_doc_ids는 2건이어야 함(현재 {ids}). train에서 골라 PM 승인 후 고정")
    for doc_id in ids:
        if splits.get(doc_id, {}).get("split") != "train":
            sys.exit(f"few-shot 예시는 train 문서만 쓸 수 있음: {doc_id}")
        for p in (Path(text_dir) / f"{doc_id}.txt", Path(label_dir) / f"{doc_id}.json"):
            if not p.exists():
                sys.exit(f"few-shot 예시 파일 없음: {p}")
    pairs = [
        ((Path(text_dir) / f"{d}.txt").read_text(encoding="utf-8"),
         json.loads((Path(label_dir) / f"{d}.json").read_text(encoding="utf-8")))
        for d in ids
    ]
    return ids, pairs


def base_model_name(arg):
    if arg:
        return arg
    import yaml

    return yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))["model"]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_dir(path):
    """어댑터 폴더의 파일 이름·내용 해시(같은 조건 이름에 다른 어댑터가 섞이는 것을 막는 용도)"""
    h = hashlib.sha256()
    for p in sorted(Path(path).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(path).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def run_record(args, base_name, fewshot_ids, fewshot_pairs):
    """출력 폴더 하나를 만든 설정(시간 제외). 이어 돌릴 때 이 값이 같아야 한다."""
    return {
        "condition": args.condition,
        "split": args.split,
        "base_model": base_name,
        "adapter": args.adapter,
        "adapter_sha256": sha256_dir(args.adapter) if args.adapter else None,
        "fewshot_doc_ids": fewshot_ids,
        "fewshot_sha256": hashlib.sha256(json.dumps(fewshot_pairs, ensure_ascii=False).encode()).hexdigest()
        if fewshot_pairs else None,
        "max_new_tokens": args.max_new_tokens,
        "prompt_sha256": sha256_file(PROMPT_FILE),
    }


def check_resume(out_dir, run):
    """폴더에 첫 실행 설정이 있으면 지금 설정과 같아야 한다. 없으면 새로 남긴다."""
    run_path = out_dir / RUN_FILE
    if run_path.exists():
        first = json.loads(run_path.read_text(encoding="utf-8").splitlines()[0])
        first.pop("created_at", None)
        diff = sorted(k for k in run if first.get(k) != run[k])
        if diff:
            sys.exit(f"[거부] {out_dir}의 첫 실행과 설정이 다름: {diff}\n"
                     f"  → 같은 설정으로 이어 돌리거나, 다른 조건 이름/폴더를 쓸 것")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps({**run, "created_at": now()}, ensure_ascii=False) + "\n", encoding="utf-8")


def now():
    return datetime.now().isoformat(timespec="seconds")


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
        base_name, quantization_config=bnb, device_map="auto", dtype=torch.bfloat16
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
def outside_repo(path):
    try:
        Path(path).resolve().relative_to(ROOT)
        return False
    except ValueError:
        return True


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
            sys.exit("[거부] test 추론은 --allow-test가 있어야 한다(모델·실험 고정 뒤, 비교군마다 1회)")
        if not EXPERIMENT_JSON.exists():
            sys.exit("[거부] eval/experiment.json(실험 고정)이 없다. 단계 7(PM 고정 커밋) 뒤에만 test를 돌린다")
        if not args.text_dir or not outside_repo(args.text_dir):
            sys.exit("[거부] test 텍스트는 저장소 밖에 있어야 한다: --text-dir <test 담당이 넘긴 폴더>")
        if args.overwrite or args.limit:
            sys.exit("[거부] test에는 --overwrite · --limit을 쓰지 않는다(비교군마다 전체 문서 1회)")


def select_docs(args, splits, text_dir):
    if args.split == "test":  # test 문서는 splits.csv에 없다. 넘겨받은 폴더의 텍스트 전체가 대상
        return sorted(p.stem for p in Path(text_dir).glob("*.txt"))
    doc_ids = sorted(d for d, r in splits.items() if r["split"] == args.split)
    if args.split == "train":  # few-shot 예시는 base_fs가 정답을 보고 푸는 셈이라 두 조건 모두에서 뺀다
        doc_ids = [d for d in doc_ids if d not in set(fewshot_ids_in_file())]
    if args.limit:
        doc_ids = doc_ids[: args.limit]
    return doc_ids


def append_log(out_dir, rec):
    with open(out_dir / LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--condition", required=True, choices=CONDITIONS)
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--adapter", help="qlora_* 조건의 LoRA 어댑터 폴더")
    ap.add_argument("--base", help="베이스 모델 이름(기본: pipeline/configs/r1.yaml의 model)")
    ap.add_argument("--max-new-tokens", type=int, help=f"기본: test는 eval/experiment.json 고정값, 그 밖은 {DEFAULT_MAX_NEW_TOKENS}")
    ap.add_argument("--allow-test", action="store_true", help="test 추론 허용(실험 고정 뒤에만)")
    ap.add_argument("--overwrite", action="store_true", help="이미 있는 출력도 다시 생성(test 불가)")
    ap.add_argument("--limit", type=int, help="앞에서 N건만(동작 점검용)")
    ap.add_argument("--splits", default=SPLITS_CSV, help="분할표(코드 점검 때 test/fixtures/splits.csv)")
    ap.add_argument("--text-dir", help="1~3항 텍스트 폴더(기본 data/text, test는 저장소 밖 폴더 필수)")
    ap.add_argument("--label-dir", default=LABEL_DIR, help="few-shot 예시 정답 폴더(base_fs만 씀)")
    ap.add_argument("--out-root", default=OUTPUT_ROOT, help="출력 루트(기본 outputs/)")
    args = ap.parse_args(argv)
    check_args(args)
    if args.max_new_tokens is None:
        args.max_new_tokens = (json.loads(EXPERIMENT_JSON.read_text(encoding="utf-8"))["max_new_tokens"]
                               if args.split == "test" else DEFAULT_MAX_NEW_TOKENS)

    text_dir = Path(args.text_dir or TEXT_DIR)
    splits = {} if args.split == "test" else read_splits(args.splits)
    doc_ids = select_docs(args, splits, text_dir)
    if not doc_ids:
        sys.exit(f"{args.split} 문서가 0건({args.splits})")
    cut = read_cut_status(text_dir)
    fewshot_ids, fewshot = (load_fewshot(read_splits(args.splits), TEXT_DIR if args.split == "test" else text_dir,
                                         args.label_dir)
                            if args.condition == "base_fs" else ([], []))
    base_name = base_model_name(args.base)
    out_dir = Path(args.out_root) / args.condition / args.split

    # 모델을 올리기 전에 입력부터 전부 확인(모델 로딩에 1분 넘게 걸림)
    missing = [d for d in doc_ids if cut.get(d) != "NOT_FOUND" and not (text_dir / f"{d}.txt").exists()]
    if missing:
        sys.exit(f"전처리 텍스트 없음 {len(missing)}건: {missing}\n→ pipeline/extract_text.py를 먼저 돌릴 것")
    check_resume(out_dir, run_record(args, base_name, fewshot_ids, fewshot))
    if args.split == "test" and any(out_dir.glob("*.json")):
        sys.exit(f"[거부] {out_dir}에 이미 출력이 있다. test는 비교군마다 1회만 생성한다")
    todo = [d for d in doc_ids if args.overwrite or not (out_dir / f"{d}.json").exists()]
    if not todo:
        print(f"할 일 없음: {out_dir}에 {len(doc_ids)}건 모두 있음(다시 돌리려면 --overwrite)")
        return

    print(f"[{args.condition} / {args.split}] {len(todo)}/{len(doc_ids)}건, base={base_name}, adapter={args.adapter}")
    tok, model = load_model(base_name, args.adapter)
    generate(tok, model, [{"role": "user", "content": "warm-up"}], 8)  # CUDA 초기화 시간이 첫 문서 속도에 섞이지 않게

    for n, doc_id in enumerate(todo, 1):
        rec = {"doc_id": doc_id, "skipped": None, "gen_time_sec": None, "input_tokens": None,
               "output_tokens": None, "hit_max_new_tokens": False, "created_at": now()}
        if cut.get(doc_id) == "NOT_FOUND":
            rec["skipped"] = "NOT_FOUND"
            (out_dir / f"{doc_id}.json").unlink(missing_ok=True)  # --overwrite 때 이전 출력이 남지 않게
            print(f"  ({n}/{len(todo)}) {doc_id}  건너뜀: _cut_log NOT_FOUND")
        else:
            text = (text_dir / f"{doc_id}.txt").read_text(encoding="utf-8")
            raw, sec, n_in, n_out = generate(tok, model, build_messages(text, fewshot), args.max_new_tokens)
            rec.update(gen_time_sec=round(sec, 3), input_tokens=n_in, output_tokens=n_out,
                       hit_max_new_tokens=n_out >= args.max_new_tokens)
            (out_dir / f"{doc_id}.json").write_text(raw, encoding="utf-8")
            flag = "  ← max_new_tokens 도달(잘렸을 수 있음)" if rec["hit_max_new_tokens"] else ""
            print(f"  ({n}/{len(todo)}) {doc_id}  {sec:.1f}s  in={n_in} out={n_out}{flag}")
        append_log(out_dir, rec)

    print(f"완료 → {out_dir}   다음: python3 eval/score.py --condition {args.condition} --split {args.split}")


if __name__ == "__main__":
    main()

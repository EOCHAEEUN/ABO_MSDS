"""
[강덕우] + 양세윤 — QLoRA 학습, runs/{날짜}_{r1|r2}/에 config.json·loss 기록

  python pipeline/train_qlora.py --config pipeline/configs/r1.yaml --memcheck   # 가장 긴 예시로 1 step, 최대 메모리만 확인
  python pipeline/train_qlora.py --config pipeline/configs/r1.yaml              # 학습
  python pipeline/train_qlora.py --config pipeline/configs/r2.yaml              # r1.yaml 위에 r2.yaml 값만 덮어씀
  python pipeline/train_qlora.py --config pipeline/configs/r1.yaml --holdout HANIL   # 교차검증: 그 제조사 그룹을 빼고 학습

입력: data/train.jsonl, data/val.jsonl (pipeline/build_jsonl.py 결과, 한 줄 = {"messages": [system, user, assistant]})
출력: runs/{MMDD}_{이름}/
  adapter/       LoRA 어댑터 (eval/infer.py --adapter 로 넘긴다, 가중치는 gitignore)
  config.json    실제로 쓴 설정 + 데이터 해시 + git 커밋
  loss.csv       step별 train loss, epoch별 val loss

추론과 한 글자도 다르지 않게:
  프롬프트 = tok.apply_chat_template(system+user, add_generation_prompt=True, enable_thinking=False)  ← eval/infer.py와 같은 호출
  정답     = format_target(label) + "<|im_end|>"
  loss는 정답 토큰에만 건다(프롬프트는 -100).
"""
import argparse
import csv
import hashlib
import json
import math
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import CHAT_TEMPLATE_KWARGS  # noqa: E402

BASE_CONFIG = ROOT / "pipeline" / "configs" / "r1.yaml"
TRAIN_JSONL = ROOT / "data" / "train.jsonl"   # 설정의 train_jsonl로 바꿀 수 있다(r2: 증강 배수 축소)
VAL_JSONL = ROOT / "data" / "val.jsonl"
DEFAULTS = {"warmup_ratio": 0.03, "weight_decay": 0.0, "seed": 42, "gradient_checkpointing": True}


# ---------------------------------------------------------------- 설정
def load_config(path):
    """r1.yaml을 바탕으로 두고 주어진 설정을 덮어쓴다(r2는 바뀐 값만 적는다)."""
    cfg = dict(DEFAULTS)
    cfg.update(yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8")) or {})
    if Path(path).resolve() != BASE_CONFIG.resolve():
        cfg.update(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    return cfg


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


# ---------------------------------------------------------------- 데이터
def encode(tok, messages, max_length):
    """→ (input_ids, labels) 또는 max_length를 넘으면 None. 정답 끝을 자르면 닫히지 않은 JSON을 배우므로 자르지 않고 뺀다."""
    assert messages[-1]["role"] == "assistant"
    prompt = tok.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True, **CHAT_TEMPLATE_KWARGS)
    target = messages[-1]["content"] + "<|im_end|>"
    p_ids = tok(prompt, add_special_tokens=False).input_ids
    t_ids = tok(target, add_special_tokens=False).input_ids
    ids = p_ids + t_ids
    if len(ids) > max_length:
        return None
    return ids, [-100] * len(p_ids) + t_ids


def load_split(tok, path, max_length, skip_docs=()):
    rows, dropped = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["doc_id"] in skip_docs:
            continue
        enc = encode(tok, r["messages"], max_length)
        if enc is None:
            dropped.append(f"{r['doc_id']}/{r['variant']}")
        else:
            rows.append(enc)
    if dropped:
        print(f"[경고] {Path(path).name}: max_length({max_length}) 초과로 {len(dropped)}건 제외 {dropped[:5]}")
    return rows


def batches(rows, size, pad_id):
    import torch

    for i in range(0, len(rows), size):
        chunk = rows[i:i + size]
        n = max(len(ids) for ids, _ in chunk)
        ids = torch.full((len(chunk), n), pad_id, dtype=torch.long)
        lab = torch.full((len(chunk), n), -100, dtype=torch.long)
        att = torch.zeros((len(chunk), n), dtype=torch.long)
        for j, (a, b) in enumerate(chunk):
            ids[j, :len(a)] = torch.tensor(a)
            lab[j, :len(b)] = torch.tensor(b)
            att[j, :len(a)] = 1
        yield ids, lab, att


# ---------------------------------------------------------------- 모델
def load_model(cfg):
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(cfg["model"])
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.bfloat16)  # eval/infer.py와 같은 양자화
    model = AutoModelForCausalLM.from_pretrained(cfg["model"], quantization_config=bnb, device_map={"": 0},
                                                 dtype=torch.bfloat16)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=cfg["gradient_checkpointing"])
    model = get_peft_model(model, LoraConfig(
        r=cfg["lora_r"], lora_alpha=cfg["lora_alpha"], lora_dropout=cfg["lora_dropout"],
        target_modules=cfg["target_modules"], bias="none", task_type="CAUSAL_LM"))
    model.config.use_cache = False
    model.train()  # from_pretrained 직후는 eval 모드 — gradient checkpointing은 train 모드에서만 켜진다
    return tok, model


def make_optimizer(model, cfg):
    import bitsandbytes as bnb

    params = [p for p in model.parameters() if p.requires_grad]
    return bnb.optim.PagedAdamW8bit(params, lr=cfg["learning_rate"], weight_decay=cfg["weight_decay"])


def lr_at(step, total, cfg):
    """선형 warmup → cosine 감쇠"""
    warm = max(1, int(total * cfg["warmup_ratio"]))
    if step < warm:
        return cfg["learning_rate"] * (step + 1) / warm
    prog = (step - warm) / max(1, total - warm)
    return cfg["learning_rate"] * 0.5 * (1 + math.cos(math.pi * prog))


def forward_loss(model, ids, lab, att):
    """정답 구간의 logits만 계산해 loss를 낸다(값은 labels=로 넘길 때와 같음).

    3.8K 토큰 × 어휘 15만의 logits 전체는 fp32로 2GB가 넘고 기울기까지 두 배라 8GB GPU에서 OOM이 난다.
    loss는 정답 토큰에만 걸리므로, 첫 정답 토큰 바로 앞 위치부터만 logits를 뽑는다(logits_to_keep).
    """
    import torch.nn.functional as F

    ids, lab, att = ids.to(0), lab.to(0), att.to(0)
    first = int((lab != -100).int().argmax(dim=1).min())  # 배치에서 가장 앞선 정답 시작 위치
    keep = ids.shape[1] - first + 1
    logits = model(input_ids=ids, attention_mask=att, logits_to_keep=keep).logits[:, :-1, :]
    target = lab[:, first:]
    return F.cross_entropy(logits.float().reshape(-1, logits.shape[-1]), target.reshape(-1), ignore_index=-100)


# ---------------------------------------------------------------- 실행
def memcheck(cfg):
    """가장 긴 train 예시 1건으로 forward+backward+optimizer step 1회 → 최대 GPU 메모리."""
    import torch

    tok, model = load_model(cfg)
    rows = load_split(tok, TRAIN_JSONL, cfg["max_length"])
    longest = max(rows, key=lambda r: len(r[0]))
    print(f"가장 긴 예시: {len(longest[0])} 토큰 (정답 {sum(x != -100 for x in longest[1])} 토큰), "
          f"max_length {cfg['max_length']}, gradient_checkpointing {cfg['gradient_checkpointing']}")
    opt = make_optimizer(model, cfg)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    ids, lab, att = next(batches([longest] * cfg["per_device_batch_size"], cfg["per_device_batch_size"], tok.pad_token_id))
    loss = forward_loss(model, ids, lab, att)
    loss.backward()
    opt.step()
    opt.zero_grad(set_to_none=True)
    torch.cuda.synchronize()
    peak = torch.cuda.max_memory_allocated() / 2**30
    reserved = torch.cuda.max_memory_reserved() / 2**30
    total = torch.cuda.get_device_properties(0).total_memory / 2**30
    print(f"loss {loss.item():.4f} · 1 step {time.perf_counter() - t0:.1f}s")
    print(f"최대 메모리 allocated {peak:.2f} GiB / reserved {reserved:.2f} GiB / GPU {total:.2f} GiB "
          f"→ {'통과' if reserved < total * 0.95 else '위험: 여유 5% 미만'}")


def evaluate(model, rows, pad_id):
    import torch

    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for ids, lab, att in batches(rows, 1, pad_id):
            tot += forward_loss(model, ids, lab, att).item()
            n += 1
    model.train()
    return tot / max(n, 1)


def holdout_docs(group):
    """split_group이 group인 train 문서 목록(교차검증에서 학습에서 빼고 평가에 쓴다)."""
    with open(ROOT / "data" / "splits.csv", encoding="utf-8-sig", newline="") as f:
        docs = [r["doc_id"] for r in csv.DictReader(f) if r["split"] == "train" and r["split_group"] in group.split("+")]
    if not docs:
        sys.exit(f"train에 그룹 {group} 문서가 없음")
    return docs


def train(cfg, name, max_steps=None, holdout=None):
    import torch

    random.seed(cfg["seed"])
    torch.manual_seed(cfg["seed"])
    run_dir = ROOT / "runs" / f"{datetime.now():%m%d}_{name}"
    if (run_dir / "adapter").exists():
        sys.exit(f"이미 있음: {run_dir.relative_to(ROOT)} — 지우거나 이름을 바꿀 것(--name)")
    run_dir.mkdir(parents=True, exist_ok=True)

    tok, model = load_model(cfg)
    train_path = ROOT / cfg.get("train_jsonl", TRAIN_JSONL)
    skip = holdout_docs(holdout) if holdout else []
    train_rows = load_split(tok, train_path, cfg["max_length"], skip)
    val_path = ROOT / cfg.get("val_jsonl", VAL_JSONL)
    val_rows = load_split(tok, val_path, cfg["max_length"])
    bs, accum = cfg["per_device_batch_size"], cfg["grad_accum"]
    steps_per_epoch = len(train_rows) // (bs * accum)  # 꼬리 micro-batch는 버리므로 내림(스케줄 끝이 실제 마지막 step과 맞게)
    total = steps_per_epoch * cfg["num_epochs"]
    if max_steps:
        total = min(total, max_steps)

    meta = {"config": cfg, "name": name, "git_commit": git_commit(), "created_at": datetime.now().isoformat(timespec="seconds"),
            "train_jsonl": str(train_path.relative_to(ROOT)), "train_jsonl_sha256": sha256(train_path), "val_jsonl": str(val_path.relative_to(ROOT)), "val_jsonl_sha256": sha256(val_path),
            "holdout_group": holdout, "holdout_docs": skip, "n_train": len(train_rows), "n_val": len(val_rows), "optimizer_steps": total,
            "chat_template_kwargs": CHAT_TEMPLATE_KWARGS}
    (run_dir / "config.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{name}] train {len(train_rows)} · val {len(val_rows)} · batch {bs}×accum {accum} · "
          f"{cfg['num_epochs']} epoch = optimizer step {total} → {run_dir.relative_to(ROOT)}")

    opt = make_optimizer(model, cfg)
    model.train()
    log = open(run_dir / "loss.csv", "w", encoding="utf-8", newline="")
    w = csv.writer(log)
    w.writerow(["epoch", "step", "lr", "train_loss", "val_loss", "elapsed_s"])
    step, t0 = 0, time.perf_counter()
    for epoch in range(1, cfg["num_epochs"] + 1):
        random.shuffle(train_rows)
        acc_loss, micro = 0.0, 0
        for ids, lab, att in batches(train_rows, bs, tok.pad_token_id):
            loss = forward_loss(model, ids, lab, att) / accum
            loss.backward()
            acc_loss += loss.item()
            micro += 1
            if micro % accum:
                continue
            lr = lr_at(step, total, cfg)
            for g in opt.param_groups:
                g["lr"] = lr
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            w.writerow([epoch, step, f"{lr:.2e}", f"{acc_loss:.4f}", "", f"{time.perf_counter() - t0:.0f}"])
            log.flush()
            print(f"  epoch {epoch} step {step}/{total}  loss {acc_loss:.4f}  lr {lr:.2e}  {time.perf_counter() - t0:.0f}s")
            acc_loss = 0.0
            if step >= total:
                break
        # 남은 micro-batch(accum으로 나누어떨어지지 않는 꼬리)는 버린다 — epoch마다 최대 accum-1건
        opt.zero_grad(set_to_none=True)
        vl = evaluate(model, val_rows, tok.pad_token_id)
        w.writerow([epoch, step, "", "", f"{vl:.4f}", f"{time.perf_counter() - t0:.0f}"])
        log.flush()
        print(f"  epoch {epoch} 끝 — val loss {vl:.4f}")
        if step >= total:
            break
    log.close()
    model.save_pretrained(run_dir / "adapter")
    print(f"완료 → {run_dir.relative_to(ROOT)}/adapter   다음: python eval/infer.py --condition qlora_{name} "
          f"--split val --adapter {(run_dir / 'adapter').relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--name", help="실행 이름(기본: 설정 파일 이름, 예 r1)")
    ap.add_argument("--memcheck", action="store_true", help="가장 긴 예시로 1 step만 돌려 최대 메모리 확인")
    ap.add_argument("--max-steps", type=int, help="optimizer step 상한(동작 점검용)")
    ap.add_argument("--holdout", help="교차검증: 이 split_group(여러 개는 +로)의 train 문서를 학습에서 뺀다")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.memcheck:
        memcheck(cfg)
        return
    name = args.name or (f"cv{Path(args.config).stem}_{args.holdout}" if args.holdout else Path(args.config).stem)
    train(cfg, name, args.max_steps, args.holdout)


if __name__ == "__main__":
    main()

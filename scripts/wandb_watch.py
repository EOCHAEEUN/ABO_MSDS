"""학습 기록(runs/{MMDD}_{이름}/)을 W&B로 올려 본다. pipeline/train_qlora.py는 고치지 않고 옆에서 붙인다.

학습이 step마다 flush하는 loss.csv와, 끝나면 result를 채우는 config.json만 읽는다. GPU를 쓰지 않는다.
학습 venv의 고정 버전을 건드리지 않도록 wandb는 별도 venv에 설치한다.

  python3 -m venv ~/wandb-venv && ~/wandb-venv/bin/pip install wandb && ~/wandb-venv/bin/wandb login
  ~/wandb-venv/bin/python scripts/wandb_watch.py runs/0929_r2       # 학습과 함께 켜 둔다(학습이 끝나면 스스로 종료)
  ~/wandb-venv/bin/python scripts/wandb_watch.py runs/0928_r1       # 끝난 run은 한 번에 올리고 종료(r2와 겹쳐 보기)
  ~/wandb-venv/bin/python scripts/wandb_watch.py /tmp/msds_smoke/0929_1300_smoke   # 스모크도 같은 방식

올리는 것: step별 train loss · lr · 경과 시간, epoch별 val loss, config.json의 설정 · 데이터 해시 · 결과(최대 메모리 등).
학습 중에 켜 두면 그 기기의 GPU 사용량(W&B 시스템 지표)도 함께 올라간다. 끝난 run을 올릴 때는 시스템 지표를 끈다.
원문 · 정답 · 모델 출력은 올리지 않는다. W&B 프로젝트는 비공개로 둔다.
감시를 중간에 다시 켜면 새 W&B run으로 처음부터 다시 올린다(학습에는 영향 없음).
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import wandb

SUMMARY_KEYS = ("optimizer_steps_done", "train_seconds", "seconds_per_step")


def read_json(path):
    """→ dict 또는 None(아직 없거나 학습 쪽이 쓰는 중)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def new_rows(path, done):
    """loss.csv에서 아직 안 올린 완성된 행. 쓰는 중인 마지막 줄(개행 없음)은 다음 주기로 미룬다."""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines(keepends=True) if l.endswith("\n")]
    return list(csv.DictReader(lines))[done:]


def log_row(r):
    step, epoch = int(r["step"]), int(r["epoch"])
    if r["val_loss"]:
        wandb.log({"step": step, "epoch": epoch, "val/loss": float(r["val_loss"])})
    else:
        wandb.log({"step": step, "epoch": epoch, "train/loss": float(r["train_loss"]), "train/lr": float(r["lr"]),
                   "train/elapsed_s": float(r["elapsed_s"])})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="runs/{MMDD}_{이름} 또는 스모크 폴더")
    ap.add_argument("--project", default="abo-msds")
    ap.add_argument("--entity", help="W&B 팀 이름(없으면 개인 계정)")
    ap.add_argument("--interval", type=float, default=10, help="loss.csv 확인 주기(초)")
    ap.add_argument("--idle-min", type=float, default=30,
                    help="새 행도 종료 기록도 없이 이 시간(분)이 지나면 학습이 멈춘 것으로 보고 실패로 끝낸다")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    loss_csv, cfg_json = run_dir / "loss.csv", run_dir / "config.json"
    print(f"기다리는 중: {loss_csv}")
    while (meta := read_json(cfg_json)) is None or not loss_csv.exists():
        time.sleep(args.interval)

    backfill = "result" in meta   # 이미 끝난 run
    wandb.init(project=args.project, entity=args.entity, name=run_dir.name, job_type="smoke" if meta.get("smoke") else "train",
               tags=[meta.get("name", "")], config={k: v for k, v in meta.items() if k != "result"},
               settings=wandb.Settings(x_disable_stats=backfill))
    wandb.define_metric("step")
    wandb.define_metric("train/*", step_metric="step")
    wandb.define_metric("val/*", step_metric="step")

    done, last_new, exit_code = 0, time.time(), 0
    while True:
        finished = "result" in (read_json(cfg_json) or {})   # 먼저 확인: result는 loss.csv를 닫은 뒤에 쓰인다
        rows = new_rows(loss_csv, done)
        for r in rows:
            log_row(r)
        if rows:
            done += len(rows)
            last_new = time.time()
            print(f"  {done}행 올림 (step {rows[-1]['step']})")
        if finished:
            break
        if time.time() - last_new > args.idle_min * 60:
            print(f"[경고] {args.idle_min:g}분 동안 새 기록도 종료 기록도 없음 — 학습이 멈췄는지 확인할 것", file=sys.stderr)
            exit_code = 1
            break
        time.sleep(args.interval)

    res = (read_json(cfg_json) or {}).get("result")
    if res:
        mem = res.get("peak_gpu_memory") or {}
        wandb.summary.update({**{k: res.get(k) for k in SUMMARY_KEYS},
                              "peak_allocated_gib": mem.get("allocated_gib"), "peak_reserved_gib": mem.get("reserved_gib"),
                              "gpu_mem_gib": (meta.get("env") or {}).get("gpu_mem_gib")})
    wandb.finish(exit_code=exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

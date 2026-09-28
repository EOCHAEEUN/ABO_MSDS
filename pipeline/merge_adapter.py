"""
[NPU 트랙] LoRA 어댑터를 베이스에 합쳐 하나의 bf16 체크포인트로 저장 (docs/npu_plan.md 5절)

OpenVINO 변환(pipeline/export_openvino.py)은 어댑터가 합쳐진 일반 체크포인트를 입력으로 받는다.

  python pipeline/merge_adapter.py --adapter runs/0926_r1/adapter --out runs/npu_r1                # 기본 nf4dq
  python pipeline/merge_adapter.py --adapter runs/0926_r1/adapter --out runs/npu_r1_bf16 --mode bf16

합치는 방식 (--mode)
  nf4dq  (기본) 베이스를 학습·GPU 추론 때와 같은 NF4로 올린 뒤 bf16으로 풀어 그 위에 어댑터를 합친다.
         어댑터가 학습 때 본 베이스 가중치(NF4 반올림값)를 그대로 쓰므로 GPU 결과와 가장 가깝다.
         bitsandbytes(CUDA)가 필요하다 → WSL2 + RTX 4060에서 실행.
  bf16   원본 bf16 베이스에 합친다. GPU가 없어도 되지만 학습 때와 베이스 가중치가 다르다.
두 방식의 차이 자체가 확인 대상이다(docs/npu_plan.md 11절). 비교할 때만 bf16을 쓴다.

출력: {out}/merged/        합친 체크포인트 + 토크나이저 (gitignore)
      {out}/merge.json     베이스 리비전 · 어댑터 해시 · 방식 · 누락 키 · git 커밋 (커밋 대상)

메모리: 4B bf16 한 벌이 약 8GB라 RTX 4060(8GB)에는 올리지 않는다. 합치기는 CPU 메모리에서 하며
        nf4dq는 GPU에 NF4(약 2.5GB)만 올리고 푼 가중치를 곧바로 CPU로 옮긴다. 시스템 메모리 16GB 이상 권장.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import experiment  # noqa: E402  어댑터 해시·베이스 리비전 계산을 평가 게이트와 같은 함수로

MODES = ("nf4dq", "bf16")


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def adapter_base(adapter):
    cfg = json.loads((Path(adapter) / "adapter_config.json").read_text(encoding="utf-8"))
    return cfg["base_model_name_or_path"]


def load_base(base, mode):
    """→ (CPU bf16 베이스 모델, NF4에서 풀어 덮어쓴 Linear 수)

    bf16:  원본 bf16 가중치 그대로.
    nf4dq: 원본 bf16 모델을 CPU에 올린 뒤, eval/infer.py·train_qlora.py와 같은 NF4 설정으로 GPU에 올린 모델에서
           양자화된 Linear를 한 개씩 bf16으로 풀어 같은 이름의 CPU 가중치에 덮어쓴다(메모리에 두 벌을 두지 않음).
           양자화되지 않는 부분(임베딩·norm·lm_head)은 NF4 모델에서도 원본 bf16 그대로라 건드리지 않는다.
    """
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16, device_map={"": "cpu"})
    if mode == "bf16":
        return model, 0

    import bitsandbytes as bnb

    q = AutoModelForCausalLM.from_pretrained(
        base,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                               bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16),
        device_map={"": 0},
        dtype=torch.bfloat16,
    )
    cpu_modules = dict(model.named_modules())
    n_dq = 0
    with torch.no_grad():
        for name, mod in q.named_modules():
            if not isinstance(mod, bnb.nn.Linear4bit):
                continue
            target = cpu_modules.get(name)
            w = bnb.functional.dequantize_4bit(mod.weight.data, mod.weight.quant_state).to("cpu", torch.bfloat16)
            if target is None or tuple(target.weight.shape) != tuple(w.shape):
                sys.exit(f"[중단] NF4 모듈과 bf16 모듈이 맞지 않음: {name}")
            target.weight.copy_(w)
            n_dq += 1
    del q
    torch.cuda.empty_cache()
    if n_dq == 0:
        sys.exit("[중단] NF4로 양자화된 Linear가 0개 — bitsandbytes 설정 확인")
    return model, n_dq


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", required=True, help="LoRA 어댑터 폴더 (예: runs/0926_r1/adapter)")
    ap.add_argument("--out", required=True, help="출력 run 폴더 (예: runs/npu_r1)")
    ap.add_argument("--mode", choices=MODES, default="nf4dq")
    ap.add_argument("--base", help="베이스 모델(기본: adapter_config.json의 base_model_name_or_path)")
    args = ap.parse_args()

    adapter = Path(args.adapter)
    if not (adapter / "adapter_model.safetensors").exists():
        sys.exit(f"어댑터 가중치 없음: {adapter}/adapter_model.safetensors — 학습 담당에게 받아 둘 것(저장소에 없음)")
    base = args.base or adapter_base(adapter)
    out = Path(args.out)
    merged_dir = out / "merged"
    if merged_dir.exists() and any(merged_dir.iterdir()):
        sys.exit(f"이미 있음: {merged_dir} — 지우고 다시 돌릴 것")

    from peft import PeftModel
    from transformers import AutoTokenizer

    print(f"[merge] base={base} adapter={adapter} mode={args.mode}")
    model, n_dq = load_base(base, args.mode)
    model = PeftModel.from_pretrained(model, str(adapter)).merge_and_unload()
    model.eval()
    merged_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(merged_dir, safe_serialization=True)
    AutoTokenizer.from_pretrained(base).save_pretrained(merged_dir)  # chat template 포함, GPU 추론과 같은 토크나이저

    rel_adapter = str(adapter.resolve().relative_to(ROOT)) if adapter.resolve().is_relative_to(ROOT) else str(adapter)
    manifest = {
        "kind": "qlora_merged",
        "base_model": base,
        "model_revision": experiment.model_revision(base),
        "adapter": rel_adapter,
        "adapter_sha256": experiment.adapter_sha(rel_adapter),
        "mode": args.mode,
        "dequantized_linear": n_dq,
        "packages": experiment.package_versions(["torch", "transformers", "peft", "bitsandbytes"]),
        "git_commit": git_commit(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out / "merge.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"완료 → {merged_dir}   다음: python pipeline/export_openvino.py --src {out} --preset int8")


if __name__ == "__main__":
    main()

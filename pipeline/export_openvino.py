"""
[NPU 트랙] 체크포인트 → OpenVINO IR (가중치 양자화 포함) (docs/npu_plan.md 5절)

optimum-cli export openvino를 정해 둔 설정(preset)으로만 부른다. 설정을 손으로 바꿔 돌리지 않는다.

  python pipeline/export_openvino.py --src runs/npu_r1 --preset int8          # merge_adapter.py 결과(QLoRA)
  python pipeline/export_openvino.py --src runs/npu_r1 --preset int4cw
  python pipeline/export_openvino.py --base Qwen/Qwen3-4B --out runs/npu_base --preset int4cw   # Base 모델

preset (한 번에 하나씩 비교, 결과를 보기 전에 목록을 정해 둠)
  int8      INT8 가중치 대칭                      OV CPU 기준선(품질 상한 확인용)
  int4cw    INT4 대칭 · 채널 단위 · 전체 레이어    NPU 기본 후보
  int4g128  INT4 대칭 · 그룹 128 · 전체 레이어     NPU 4(Lunar Lake 등)에서만 후보 — 장비에서 확인
데이터 기반 보정(AWQ·scale estimation)은 쓰지 않는다. 쓰게 되면 보정 데이터는 train 텍스트만 쓴다.

출력: {out}/ov_{preset}/             IR(openvino_model.xml/.bin) + HF 토크나이저 + OV 토크나이저 (gitignore)
      {out}/export_{preset}.json     원본 · preset 인자 · 패키지 버전 · IR 해시 (커밋 대상)

실행 환경: requirements-npu.txt를 설치한 venv(optimum-intel이 transformers 버전을 따로 고정한다).
메모리: 4B 변환은 시스템 메모리를 많이 쓴다(원본 8GB + 변환 중 사본). 16GB 장비에서 부족하면 NPU 노트북에서 돌린다.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PRESETS = {
    "int8": ["--weight-format", "int8", "--sym"],
    "int4cw": ["--weight-format", "int4", "--sym", "--ratio", "1.0", "--group-size", "-1"],
    "int4g128": ["--weight-format", "int4", "--sym", "--ratio", "1.0", "--group-size", "128"],
}
PACKAGES = ["openvino", "openvino-genai", "openvino-tokenizers", "optimum-intel", "optimum", "nncf", "transformers"]


def versions():
    out = {}
    for n in PACKAGES:
        try:
            out[n] = version(n)
        except PackageNotFoundError:
            out[n] = None
    return out


def file_sha(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--src", help="merge_adapter.py 출력 run 폴더 (merged/·merge.json이 있는 곳)")
    src.add_argument("--base", help="어댑터 없이 변환할 HF 모델 이름 (Base 조건용)")
    ap.add_argument("--out", help="출력 run 폴더 (--base일 때 필수, --src면 기본값 = --src)")
    ap.add_argument("--preset", required=True, choices=sorted(PRESETS))
    args = ap.parse_args()

    if args.src:
        run = Path(args.src)
        model_in = run / "merged"
        merge = json.loads((run / "merge.json").read_text(encoding="utf-8"))
        out = Path(args.out) if args.out else run
        source = {"kind": "qlora_merged", "merge": merge}
    else:
        if not args.out:
            sys.exit("--base에는 --out이 필요함 (예: runs/npu_base)")
        model_in, out = args.base, Path(args.out)
        source = {"kind": "base", "base_model": args.base}

    ir_dir = out / f"ov_{args.preset}"
    if ir_dir.exists():
        sys.exit(f"이미 있음: {ir_dir} — 지우고 다시 돌릴 것")
    cli = shutil.which("optimum-cli")
    if not cli:
        sys.exit("optimum-cli 없음 — requirements-npu.txt를 설치한 venv에서 실행할 것")

    cmd = [cli, "export", "openvino", "--model", str(model_in), "--task", "text-generation-with-past",
           *PRESETS[args.preset], str(ir_dir)]
    print("[export]", " ".join(cmd))
    t0 = datetime.now()
    subprocess.run(cmd, check=True)

    xml = ir_dir / "openvino_model.xml"
    if not xml.exists():
        sys.exit(f"변환 결과에 {xml.name} 없음 — optimum-cli 출력 확인")
    if not (ir_dir / "openvino_tokenizer.xml").exists():
        print("[경고] openvino_tokenizer.xml 없음. eval/infer_npu.py는 HF 토크나이저로 토큰을 넣으므로 동작하지만, "
              "LLMPipeline 생성이 실패하면 openvino-tokenizers 설치를 확인할 것")

    manifest = {
        "source": source,
        "preset": args.preset,
        "cli_args": PRESETS[args.preset],
        "ir_dir": str(ir_dir.resolve().relative_to(ROOT)) if ir_dir.resolve().is_relative_to(ROOT) else str(ir_dir),
        "ir_xml_sha256": file_sha(xml),
        "ir_bin_sha256": file_sha(ir_dir / "openvino_model.bin"),
        "packages": versions(),
        "export_seconds": round((datetime.now() - t0).total_seconds(), 1),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out / f"export_{args.preset}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                   encoding="utf-8")
    print(f"완료 → {ir_dir}   다음: python eval/infer_npu.py --model {ir_dir} --device CPU --condition <이름> --split val")


if __name__ == "__main__":
    main()

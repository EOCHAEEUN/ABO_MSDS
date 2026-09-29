"""
[양세윤] 베이스 + 어댑터 동시 로드, 모델 전환 — 서빙(app/main.py · app/pipeline_run.py)용 실제 추론.

- 베이스(Qwen3-4B, 4bit)를 한 번만 올리고 r1 어댑터를 붙여 둔다. "qlora"는 어댑터를 켠 채로,
  "base"는 어댑터를 끈 채로(PeftModel.disable_adapter) 같은 모델로 생성한다 — 8GB GPU에 모델 두 벌을 올리지 않는다.
- 설정은 모두 eval/experiment.json(단계 7 고정값)을 따른다: 어댑터 · 프롬프트 버전 · max_new_tokens.
  어댑터 폴더 해시가 고정값과 다르면 올리지 않는다.
- "base"는 Base few-shot(k=2, eval/fewshot.json의 train 문서)이다. val · test의 대조군(base_fs)과 같은 조건.
- 로딩 · 생성 · 프롬프트는 eval/infer.py와 같은 함수를 쓴다(학습 · 평가 · 서빙이 한 경로).
- 처음 부를 때 올린다(수십 초). 생성은 한 번에 하나씩(잠금) — GPU 하나에서 두 요청을 겹쳐 돌리지 않는다.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.prompt import build_messages  # noqa: E402
from eval import infer  # noqa: E402

MODELS = ("qlora", "base")
_lock = threading.Lock()
_state: dict[str, Any] = {}


def experiment() -> dict:
    """eval/experiment.json(단계 7 고정값). 없거나 필수 키가 없으면 SystemExit → 서버에서 오류로 돌려준다."""
    return infer.load_experiment()


def _load() -> dict:
    if _state:
        return _state
    exp = experiment()
    adapter = ROOT / exp["adapter"]
    if not adapter.exists():
        raise RuntimeError(f"어댑터 폴더가 이 컴퓨터에 없다: {exp['adapter']} (가중치는 git에 없음 — 팀 드라이브에서 받을 것)")
    if infer.sha256_dir(adapter) != exp["adapter_sha256"]:
        raise RuntimeError(f"{exp['adapter']}의 해시가 eval/experiment.json의 adapter_sha256과 다르다")
    base_name, revision = infer.base_model_spec(None, None)
    tok, model = infer.load_model(base_name, str(adapter), revision)
    commit = infer.verify_commit(model, revision)
    splits = infer.read_splits(infer.SPLITS_CSV)
    fewshot_ids, fewshot = infer.load_fewshot(splits, infer.TEXT_DIR, infer.LABEL_DIR)
    _state.update(tok=tok, model=model, exp=exp, base=f"{base_name}@{commit}", fewshot_ids=fewshot_ids, fewshot=fewshot)
    return _state


def predict_detail(text: str, model_name: str) -> dict:
    """1~3항 텍스트 → {raw, model_name, seconds, input_tokens, output_tokens, hit_max_new_tokens, ...}."""
    if model_name not in MODELS:
        raise ValueError(f"model은 {MODELS} 중 하나: {model_name}")
    with _lock:
        s = _load()
        exp = s["exp"]
        fewshot = s["fewshot"] if model_name == "base" else ()
        messages = build_messages(text, fewshot, prompt=exp["prompt_version"])
        t0 = time.perf_counter()
        if model_name == "base":
            with s["model"].disable_adapter():
                raw, sec, n_in, n_out = infer.generate(s["tok"], s["model"], messages, exp["max_new_tokens"])
        else:
            raw, sec, n_in, n_out = infer.generate(s["tok"], s["model"], messages, exp["max_new_tokens"])
    return {"raw": raw, "model_name": model_name, "seconds": round(sec, 1), "input_tokens": n_in, "output_tokens": n_out,
            "hit_max_new_tokens": n_out >= exp["max_new_tokens"], "wall_seconds": round(time.perf_counter() - t0, 1),
            "base": s["base"], "adapter": exp["adapter"] if model_name == "qlora" else None,
            "prompt_version": exp["prompt_version"], "fewshot_doc_ids": s["fewshot_ids"] if model_name == "base" else []}


def predict(text: str, model_name: str) -> str:
    """app/pipeline_run.py가 부르는 모양: 모델 출력 원문 문자열만."""
    return predict_detail(text, model_name)["raw"]


if __name__ == "__main__":  # 점검: python3 -m app.model data/text/KR-3DSYS-001.txt qlora
    out = predict_detail(Path(sys.argv[1]).read_text(encoding="utf-8"), sys.argv[2] if len(sys.argv) > 2 else "qlora")
    print(json.dumps({k: v for k, v in out.items() if k != "raw"}, ensure_ascii=False))
    print(out["raw"])

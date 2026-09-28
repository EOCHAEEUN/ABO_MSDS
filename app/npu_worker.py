r"""
[NPU 트랙] NPU 추론 워커 — Windows 네이티브 venv(requirements-npu.txt)에서 띄운다 (docs/npu_plan.md 3·4절 6단계)

  set MSDS_OV_BASE=runs\npu_base\ov_int4cw
  set MSDS_OV_QLORA=runs\npu_r1\ov_int4cw
  python -m uvicorn app.npu_worker:app --host 0.0.0.0 --port 8765

WSL 쪽 앱은 MSDS_BACKEND=ov_http, MSDS_NPU_URL=http://<Windows 호스트 IP>:8765 로 이 워커를 부른다.
두 모델(base, qlora)을 시작할 때 모두 NPU에 올린다(런타임 LoRA 전환은 쓰지 않음 — docs/npu_plan.md 5절).
생성은 한 번에 한 건씩(NPU 하나를 두 요청이 나눠 쓰면 시간 측정이 섞인다).
"""
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from app.backends.ov_genai import OVGenAIRunner, PromptTooLong

DEVICE = os.environ.get("MSDS_OV_DEVICE", "NPU")
MODEL_DIRS = {"base": os.environ.get("MSDS_OV_BASE"), "qlora": os.environ.get("MSDS_OV_QLORA")}

_runners, _lock = {}, threading.Lock()


class GenerateRequest(BaseModel):
    model: str
    messages: list[dict]
    max_new_tokens: int = 1269


@asynccontextmanager
async def lifespan(_app):
    for name, path in MODEL_DIRS.items():
        if path:
            _runners[name] = OVGenAIRunner(path, DEVICE, cache_dir=os.environ.get("MSDS_OV_CACHE", "runs/_ov_cache"))
    yield


app = FastAPI(title="MSDS NPU worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {"device": DEVICE, "models": {k: MODEL_DIRS[k] for k in _runners}}


@app.post("/generate")
def generate(req: GenerateRequest):
    runner = _runners.get(req.model)
    if runner is None:
        return {"error": f"모델 없음: {req.model} (MSDS_OV_BASE / MSDS_OV_QLORA 확인)"}
    with _lock:
        try:
            raw, sec, n_in, n_out = runner.generate(req.messages, req.max_new_tokens)
        except PromptTooLong as e:
            return {"error": f"PROMPT_TOO_LONG: {e}"}
    return {"raw_output": raw, "gen_time_sec": round(sec, 3), "input_tokens": n_in, "output_tokens": n_out,
            "device": DEVICE, "quant": os.path.basename(runner.model_dir), **runner.last}

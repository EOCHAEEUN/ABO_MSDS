"""
[NPU 트랙] Windows NPU 워커(app/npu_worker.py) 호출 — WSL2 안에서는 NPU 장치가 보이지 않아 추론만 Windows에서 돈다
표준 라이브러리만 쓴다(WSL 쪽 venv에 OpenVINO를 깔지 않아도 됨).
"""
import json
import urllib.request


class OVHttpBackend:
    def __init__(self, model, url, timeout=600):
        self.name, self.url, self.timeout = model, url.rstrip("/"), timeout
        self.last = {}

    def generate(self, messages, max_new_tokens):
        body = json.dumps({"model": self.name, "messages": messages, "max_new_tokens": max_new_tokens}).encode()
        req = urllib.request.Request(f"{self.url}/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        if r.get("error"):
            raise RuntimeError(f"NPU 워커 오류: {r['error']}")
        self.last = {k: r.get(k) for k in ("ttft_sec", "throughput_tok_s", "device", "quant")}
        return r["raw_output"], r["gen_time_sec"], r["input_tokens"], r["output_tokens"]

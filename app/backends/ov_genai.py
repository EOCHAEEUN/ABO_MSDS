"""
[NPU 트랙] OpenVINO GenAI 추론기 — eval/infer_npu.py(평가)와 app/npu_worker.py(서빙)가 같이 쓴다.

GPU 경로(eval/infer.py generate)와 입력이 한 토큰도 다르지 않게 한다.
  프롬프트: HF 토크나이저 apply_chat_template(add_generation_prompt=True, enable_thinking=False)로 문자열을 만들고
           같은 토크나이저로 토큰화한 ID를 TokenizedInputs로 넘긴다(OV 쪽 chat template·토크나이저를 거치지 않음)
  출력:     생성 토큰 ID를 같은 HF 토크나이저로 decode(skip_special_tokens=True)
  디코딩:   greedy(do_sample=False), 정지 토큰은 모델 generation_config.json의 eos_token_id
NPU는 정적 형태로 컴파일되므로 MAX_PROMPT_LEN을 넘는 입력은 자르지 않고 PromptTooLong으로 거부한다.
"""
import json
import time
from pathlib import Path

from core.prompt import CHAT_TEMPLATE_KWARGS

DEFAULT_MAX_PROMPT_LEN = 4096   # report/length_stats.md: zero-shot·QLoRA 프롬프트 MAX 2,949
DEFAULT_MIN_RESPONSE_LEN = 1280  # max_new_tokens 1269(정답 MAX 976 × 1.3)보다 크게


class PromptTooLong(Exception):
    pass


def stop_token_ids(model_dir, tok):
    p = Path(model_dir) / "generation_config.json"
    eos = json.loads(p.read_text(encoding="utf-8")).get("eos_token_id") if p.exists() else None
    if eos is None:
        eos = tok.eos_token_id
    return set(eos if isinstance(eos, list) else [eos])


class OVGenAIRunner:
    def __init__(self, model_dir, device="NPU", max_prompt_len=DEFAULT_MAX_PROMPT_LEN,
                 min_response_len=DEFAULT_MIN_RESPONSE_LEN, cache_dir=None):
        import openvino_genai as ov_genai
        from transformers import AutoTokenizer

        self.model_dir, self.device = str(model_dir), device.upper()
        self.max_prompt_len = max_prompt_len if self.device == "NPU" else None
        self.tok = AutoTokenizer.from_pretrained(self.model_dir)
        props = {}
        if self.device == "NPU":
            props = {"MAX_PROMPT_LEN": max_prompt_len, "MIN_RESPONSE_LEN": min_response_len}
        if cache_dir:  # NPU 컴파일 결과 캐시(두 번째 실행부터 로딩이 빨라짐)
            props["CACHE_DIR"] = str(cache_dir)
        self.props = props
        t0 = time.perf_counter()
        self.pipe = ov_genai.LLMPipeline(self.model_dir, self.device, **props)
        self.load_sec = time.perf_counter() - t0
        self.stop_ids = stop_token_ids(self.model_dir, self.tok)
        self.last = {}

    def encode(self, messages):
        """→ input_ids (list[int]). eval/infer.py generate()와 같은 호출"""
        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                              **CHAT_TEMPLATE_KWARGS)
        return self.tok(prompt)["input_ids"]

    def generate(self, messages, max_new_tokens):
        """→ (출력 문자열, 생성 시간 초, 입력 토큰 수, 출력 토큰 수). 부가 수치는 self.last"""
        import numpy as np
        import openvino as ov
        import openvino_genai as ov_genai

        ids = self.encode(messages)
        n_in = len(ids)
        if self.max_prompt_len and n_in > self.max_prompt_len:
            raise PromptTooLong(f"입력 {n_in}토큰 > MAX_PROMPT_LEN {self.max_prompt_len}")

        cfg = self.pipe.get_generation_config()
        cfg.max_new_tokens = max_new_tokens
        cfg.do_sample = False
        cfg.stop_token_ids = self.stop_ids
        arr = np.asarray([ids], dtype=np.int64)
        inputs = ov_genai.TokenizedInputs(ov.Tensor(arr), ov.Tensor(np.ones_like(arr)))

        t0 = time.perf_counter()
        res = self.pipe.generate(inputs, cfg)
        elapsed = time.perf_counter() - t0

        out = list(res.tokens[0])
        if out and out[:n_in] == ids:  # 버전에 따라 입력이 앞에 붙어 오면 떼어 낸다
            out = out[n_in:]
        self.last = {"ttft_sec": None, "throughput_tok_s": None}
        try:
            pm = res.perf_metrics
            self.last = {"ttft_sec": round(pm.get_ttft().mean / 1000, 3),
                         "throughput_tok_s": round(pm.get_throughput().mean, 2)}
        except Exception:
            pass
        self.last["input_ids_sha256"] = _ids_sha(ids)
        return self.tok.decode(out, skip_special_tokens=True), elapsed, n_in, len(out)


def _ids_sha(ids):
    import hashlib

    return hashlib.sha256(",".join(map(str, ids)).encode()).hexdigest()[:16]

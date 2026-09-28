"""
[NPU 트랙] GPU(bitsandbytes NF4) 추론 — eval/infer.py의 load_model·generate를 그대로 부른다

  MSDS_BASE_MODEL     기본 pipeline/configs/r1.yaml의 model
  MSDS_QLORA_ADAPTER  기본 runs/0926_r1/adapter (qlora_final이 정해지면 그 폴더로)
"""
import os

from eval.infer import base_model_name, generate, load_model


class TorchNF4Backend:
    def __init__(self, model):
        adapter = os.environ.get("MSDS_QLORA_ADAPTER", "runs/0926_r1/adapter") if model == "qlora" else None
        self.name = model
        self.tok, self.model = load_model(base_model_name(os.environ.get("MSDS_BASE_MODEL")), adapter)

    def generate(self, messages, max_new_tokens):
        return generate(self.tok, self.model, messages, max_new_tokens)

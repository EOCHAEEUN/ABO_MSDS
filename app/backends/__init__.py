"""
[NPU 트랙] 추론 방식 선택 — 서빙(app/)이 모델을 부르는 단일 입구

공통 인터페이스: backend.generate(messages, max_new_tokens) → (출력 문자열, 생성 시간 초, 입력 토큰 수, 출력 토큰 수)
  messages는 core/prompt.build_messages()로 만든다(학습·평가와 같은 프롬프트).

  MSDS_BACKEND=torch_nf4  (기본) GPU, eval/infer.py와 같은 로드·생성 — 평가 결과와 같은 모델
  MSDS_BACKEND=ov_http    Windows에서 띄운 NPU 워커(app/npu_worker.py)에 HTTP로 요청
                          MSDS_NPU_URL (기본 http://localhost:8765)

사용 예 (app/model.py에서):
  from app.backends import get_backend
  qlora = get_backend("qlora")   # 또는 "base"
  raw, sec, n_in, n_out = qlora.generate(build_messages(text), 1269)
"""
import os

MODELS = ("base", "qlora")


def get_backend(model, kind=None):
    if model not in MODELS:
        raise ValueError(f"model은 {MODELS} 중 하나: {model}")
    kind = kind or os.environ.get("MSDS_BACKEND", "torch_nf4")
    if kind == "torch_nf4":
        from app.backends.torch_nf4 import TorchNF4Backend

        return TorchNF4Backend(model)
    if kind == "ov_http":
        from app.backends.ov_http import OVHttpBackend

        return OVHttpBackend(model, os.environ.get("MSDS_NPU_URL", "http://localhost:8765"))
    raise ValueError(f"알 수 없는 MSDS_BACKEND: {kind}")

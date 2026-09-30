import json, time, torch, bitsandbytes as bnb
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
from bitsandbytes.functional import dequantize_4bit
from eval.infer import base_model_spec, sha256_dir

ADAPTER, OUT = "runs/0928_r1/adapter", "runs/deploy_r1/merged_nf4dq"
t0 = time.time()
base, rev = base_model_spec(None, None)
ah = sha256_dir(ADAPTER)
print("base", base, rev, "adapter", ah[:8])
assert ah.startswith("a9a32341"), "adapter hash mismatch"

bnbc = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                          bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
q = AutoModelForCausalLM.from_pretrained(base, revision=rev, quantization_config=bnbc, device_map={"": 0})
deq = {n: dequantize_4bit(m.weight.data, m.weight.quant_state).to(torch.bfloat16).cpu()
       for n, m in q.named_modules() if isinstance(m, bnb.nn.Linear4bit)}
n_deq = len(deq)
del q; torch.cuda.empty_cache()
print("dequantized Linear:", n_deq)

model = AutoModelForCausalLM.from_pretrained(base, revision=rev, dtype=torch.bfloat16, device_map={"": "cpu"})
with torch.no_grad():
    for n, w in deq.items():
        p = model.get_submodule(n).weight
        assert p.shape == w.shape, (n, p.shape, w.shape)
        p.copy_(w)
del deq
model = PeftModel.from_pretrained(model, ADAPTER).merge_and_unload()
model.save_pretrained(OUT, safe_serialization=True)
AutoTokenizer.from_pretrained(base, revision=rev).save_pretrained(OUT)
json.dump({"method": "nf4dq", "base": base, "revision": rev, "adapter_sha256": ah,
           "n_dequantized_linear": n_deq, "torch": torch.__version__,
           "bitsandbytes": bnb.__version__, "seconds": round(time.time() - t0)},
          open(f"{OUT}/merge_nf4dq.json", "w"), indent=1)
print("done", OUT, round(time.time() - t0), "s")

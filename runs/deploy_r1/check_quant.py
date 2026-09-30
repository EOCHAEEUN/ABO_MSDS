import json, sys, time, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
M = "runs/deploy_r1/quark_awq_w4g128"
doc = sys.argv[1] if len(sys.argv) > 1 else "KR-KCCSIL-001"
ids = json.load(open(f"runs/deploy_r1/demo/{doc}.json"))
tok = AutoTokenizer.from_pretrained(M)
model = AutoModelForCausalLM.from_pretrained(M, dtype=torch.bfloat16, device_map={"": 0})
x = torch.tensor([ids], device=model.device)
t0 = time.time()
out = model.generate(x, max_new_tokens=2048, do_sample=False)
text = tok.decode(out[0][len(ids):], skip_special_tokens=True)
print(text)
print(f"\n{len(out[0]) - len(ids)} tokens, {time.time() - t0:.0f}s")
open(f"runs/deploy_r1/demo/{doc}.quant.txt", "w").write(text)

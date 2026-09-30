import json
from pathlib import Path
from types import SimpleNamespace
from transformers import AutoTokenizer
from eval.infer import read_splits, select_docs, SPLITS_CSV, build_messages, CHAT_TEMPLATE_KWARGS

td = Path("runs/deploy/text_r1")
val = select_docs(SimpleNamespace(split="val", splits=SPLITS_CSV, limit=None), read_splits(SPLITS_CSV), td)
tok = AutoTokenizer.from_pretrained("runs/deploy_r1/merged_nf4dq")
out = Path("runs/deploy_r1/demo")
for d in val:
    p = td / f"{d}.txt"
    if not p.exists():
        print(d, "텍스트 없음"); continue
    msgs = build_messages(p.read_text(encoding="utf-8"), [], prompt="v1")
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, **CHAT_TEMPLATE_KWARGS)
    ids = tok(prompt, add_special_tokens=False)["input_ids"]
    json.dump(ids, open(out / f"{d}.json", "w"))
    print(d, len(ids))

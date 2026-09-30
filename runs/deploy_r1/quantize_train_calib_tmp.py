import json, os, random, runpy, sys
import torch
from torch.utils.data import DataLoader
import quark.torch.utils.llm as L

R = os.path.expanduser("~/abo_msds/ABO_MSDS")
TRAIN = f"{R}/data/train.jsonl"
LOG = f"{R}/runs/deploy_r1/calib_samples.json"
SEED = 42

def train_calib(tokenizer=None, batch_size=1, num_calib_data=64, seqlen=1024, device="cuda", **kw):
    rows = [json.loads(l) for l in open(TRAIN, encoding="utf-8")]
    assert all(r["split"] == "train" for r in rows), "train 외 데이터가 섞임"
    random.Random(SEED).shuffle(rows)
    ids, used = [], []
    for r in rows:
        t = list(tokenizer.apply_chat_template(r["messages"], tokenize=True, enable_thinking=False))
        if len(t) < seqlen:
            continue
        ids.append(torch.tensor(t[:seqlen]))
        used.append(f'{r["doc_id"]}/{r.get("variant")}')
        if len(ids) == num_calib_data:
            break
    assert len(ids) == num_calib_data, f"{seqlen}토큰 이상 표본이 {len(ids)}개뿐"
    json.dump({"n": num_calib_data, "seqlen": seqlen, "seed": SEED, "source": TRAIN, "samples": used},
              open(LOG, "w"), ensure_ascii=False, indent=1)
    print(f"[train-calib] {num_calib_data} x {seqlen} tokens from train.jsonl")
    return DataLoader(torch.stack(ids).to(device), batch_size=batch_size, shuffle=False, drop_last=True)

L.get_calib_dataloader = train_calib
script = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.dirname(script))
sys.argv = [script] + sys.argv[2:]
runpy.run_path(script, run_name="__main__")

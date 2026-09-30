import sys, json, time, pathlib, onnxruntime_genai as og

model_dir, ids_dir, out_dir = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
docs = sys.argv[4:]
out_dir.mkdir(exist_ok=True)
m = og.Model(model_dir)
tok = og.Tokenizer(m)
files = [ids_dir / f"{d}.json" for d in docs] if docs else sorted(ids_dir.glob("*.json"))
for f in files:
    ids = json.load(open(f))
    p = og.GeneratorParams(m)
    p.set_search_options(max_length=min(len(ids) + 2048, 40960), do_sample=False)
    g = og.Generator(m, p)
    t0 = time.time()
    g.append_tokens(ids)
    t1 = time.time()
    out = []
    while not g.is_done():
        g.generate_next_token()
        out.append(g.get_next_tokens()[0])
    t2 = time.time()
    text = tok.decode(out)
    (out_dir / f"{f.stem}.txt").write_text(text, encoding="utf-8")
    print(f"== {f.stem}: in {len(ids)} / out {len(out)} tok, prefill {t1-t0:.1f}s, total {t2-t0:.1f}s")
    if docs:
        print(text)
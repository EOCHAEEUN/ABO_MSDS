"""
[강덕우] train.jsonl / val.jsonl 생성

  python pipeline/build_jsonl.py               # data/train.jsonl, data/val.jsonl
  python pipeline/build_jsonl.py --dry-run     # 건수·거부 사유만 출력
  python pipeline/build_jsonl.py --renderers 2 --train-out train_r2.jsonl   # r2: 렌더러를 문서당 2종만(증강 배수 축소)
  python pipeline/build_jsonl.py --train-out train_c1.jsonl --val-out val_c1.jsonl  # C1: 보강 문서 포함(docs/plan_c.md 7절)

한 줄 = 한 학습 예시: {"doc_id", "variant", "messages": [system, user, assistant]}
메시지는 core/prompt.py의 build_messages()·format_target()으로만 만든다 — 추론과 한 글자도 다르면 안 된다.

train (문서마다)
  orig          원본 그대로
  <렌더러> ×N   겉모양만 바꾼 변형 (pipeline/augment/renderers.py), 라벨 동일. N=5(기본), 줄이면 문서마다 무작위 N종
  secret ×k     성분 하나를 영업비밀로 가림, 라벨도 같이 바꿈 (mutators.py)
  nohcode ×1    H코드를 지움, 라벨 code → null
  ecnum ×1      CAS 뒤에 EC 번호 칸을 끼움, 라벨 동일 (train에 EC 표기 문서가 없어 r1이 EC를 KE로 넣었음)
val (문서마다)
  orig + 렌더러 5종 (README: 원본 + 건당 변형 5개). 내용 변형은 넣지 않는다 — val은 실제 분포를 봐야 한다.

모든 변형은 check_forbidden.check()를 통과해야 들어간다. 원본 텍스트가 NOT_FOUND인 문서는 뺀다.
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import build_messages, format_target  # noqa: E402
from core.schema import check_schema  # noqa: E402
from pipeline.augment.check_forbidden import check  # noqa: E402
from pipeline.augment.mutators import MUTATORS  # noqa: E402
from pipeline.augment.renderers import RENDERERS  # noqa: E402

TEXT_DIR = ROOT / "data" / "text"
LABEL_DIR = ROOT / "data" / "labels"
SPLITS_CSV = ROOT / "data" / "splits.csv"
TRIES = 6


def example(doc_id, variant, text, label):
    msgs = build_messages(text) + [{"role": "assistant", "content": format_target(label)}]
    return {"doc_id": doc_id, "variant": variant, "messages": msgs}


def variants_for(doc_id, text, label, rng, split, n_secret, n_renderers):
    """→ (예시 목록, 거부 목록)"""
    out, rejected = [example(doc_id, "orig", text, label)], []
    seen = {text}

    def problems(new_text, new_label, gone):
        probs = check(text, new_text, new_label, gone)
        probs += [f"스키마: {e}" for e in check_schema(new_label)[1]]
        if new_text in seen:
            probs.append("원본·다른 변형과 텍스트가 같음")
        return probs

    def add(name, make):
        """make() → (text, label, gone) | None. 난수가 원본과 같은 표기를 고를 수 있어 몇 번 다시 뽑는다."""
        probs = ["적용할 곳 없음"]
        for _ in range(TRIES):
            r = make()
            if r is None:
                return
            probs = problems(*r)
            if not probs:
                seen.add(r[0])
                out.append(example(doc_id, name, r[0], r[1]))
                return
        rejected.append((doc_id, name, probs))

    for name, fn in RENDERERS.items():
        add(name, lambda fn=fn: (fn(text, rng), label, ()))
    if split != "train":
        return out, rejected
    for k in range(n_secret):
        add(f"secret{k + 1}", lambda: MUTATORS["secret"](text, label, rng))
    add("nohcode", lambda: MUTATORS["nohcode"](text, label, rng))
    add("ecnum", lambda: MUTATORS["ecnum"](text, label, rng))
    if n_renderers < len(RENDERERS):
        # 렌더러 변형만 덜어낸다. 난수를 따로 써서, 나머지 예시(orig·secret·nohcode·ecnum)는 기본 세트와 글자까지 같게
        keep = set(random.Random(f"renderers-{doc_id}").sample(list(RENDERERS), n_renderers))
        out = [e for e in out if e["variant"] not in RENDERERS or e["variant"] in keep]
    return out, rejected


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--secret", type=int, default=2, help="문서당 영업비밀 변형 수")
    ap.add_argument("--renderers", type=int, default=len(RENDERERS), help="train 문서당 렌더러 변형 수(val은 늘 5종)")
    ap.add_argument("--train-out", default="train.jsonl", help="train 출력 파일 이름")
    ap.add_argument("--val-out", default="val.jsonl", help="val 출력 파일 이름(C안: val_c1.jsonl — r1의 val.jsonl을 덮어쓰지 않게)")
    ap.add_argument("--out-dir", default=str(ROOT / "data"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(SPLITS_CSV, encoding="utf-8-sig", newline="") as f:
        splits = {r["doc_id"]: r["split"] for r in csv.DictReader(f)}
    for split in ("train", "val"):
        # split마다 난수를 따로 둔다 — train 옵션을 바꿔도 val.jsonl은 한 글자도 바뀌지 않게(r1·r2 val loss 비교)
        rng = random.Random(f"{args.seed}-{split}")
        rows, rejected, skipped = [], [], []
        for doc_id in sorted(d for d, s in splits.items() if s == split):
            tp = TEXT_DIR / f"{doc_id}.txt"
            if not tp.exists():
                skipped.append(doc_id)
                continue
            text = tp.read_text(encoding="utf-8")
            label = json.loads((LABEL_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
            ex, rej = variants_for(doc_id, text, label, rng, split, args.secret, args.renderers)
            rows += ex
            rejected += rej
        rng.shuffle(rows)

        kinds = Counter(r["variant"].rstrip("0123456789") for r in rows)
        docs = {r["doc_id"] for r in rows}
        sec_docs = sum(any(c["is_substitute_data"] for c in json.loads(r["messages"][-1]["content"])["ingredients"])
                       for r in rows)
        null_docs = sum(any(h["code"] is None for h in json.loads(r["messages"][-1]["content"])["hazard_statements"])
                        for r in rows)
        print(f"\n[{split}] 문서 {len(docs)}건 → 예시 {len(rows)}건 ({len(rows) / max(len(docs), 1):.1f}배)")
        print("  " + " · ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
        print(f"  영업비밀 성분이 있는 예시 {sec_docs}건 · H코드 없는 문구가 있는 예시 {null_docs}건")
        if skipped:
            print(f"  텍스트 없음(제외): {skipped}")
        for doc_id, name, probs in rejected:
            print(f"  [거부] {doc_id} {name}: {probs[0]}" + (f" 외 {len(probs) - 1}건" if len(probs) > 1 else ""))

        if not args.dry_run:
            path = Path(args.out_dir) / (args.train_out if split == "train" else args.val_out)
            with open(path, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  → {path}")


if __name__ == "__main__":
    main()

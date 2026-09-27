"""
두 조건의 문서 단위 짝 비교 — docs/plan_c.md 6절 "승·패·무 + 부트스트랩 신뢰구간"

  python eval/paired.py base_fs qlora_final --split test2
  python eval/paired.py base_fs qlora_r1 --split val --out report/paired_val.md

- 같은 문서에서 A와 B를 비교한다(짝 비교). 문서 완전 정답 두 기준(확장=주지표, 기존)의 승·패·무,
  정답률 차이(B − A)의 95% 부트스트랩 신뢰구간, 승·패만 센 양측 부호 검정 p값을 낸다.
- 부트스트랩은 split_group 단위로 복원추출한다(뽑힌 그룹의 문서를 통째로 넣음). 같은 제조사·같은 양식 문서
  (예: DAIKIN 3건)는 결과가 함께 움직이므로 문서 단위로 뽑으면 신뢰구간이 실제보다 좁아진다.
  그룹이 1개뿐인 구간은 신뢰구간을 내지 않는다. 부호 검정은 문서 독립을 가정하므로 참고로만 본다.
- 필드 지표(GHS·H코드·CAS·pair·nocas F1, 스키마·제품명)도 같은 방식으로 micro F1 차이의 신뢰구간을 낸다.
- 서식(현행·수입품 국문판·구서식·영문)별로 나눠 보고한다. 합산 결과는 "전체" 행으로 따로 둔다.
- test·test2는 봉인 대조를 통과해야 돈다. 채점 규칙은 eval/score.py 그대로다(같은 함수를 쓴다).
"""
import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.infer import base_doc, variant_texts  # noqa: E402
from eval.score import (FEWSHOT_JSON, GOLD_DIRS, OUTPUT_ROOT, SPLITS, TEXT_DIR, Acc,  # noqa: E402
                        doc_exact, load_prediction, read_splits, score_doc)
from eval.gate import gate_score  # noqa: E402
from core.schema import check_schema  # noqa: E402

PRF = ("ghs", "hcode", "cas", "pair", "nocas")
B = 10000
SEED = 20260927


def doc_ids_for(split, splits):
    if split == "val_var":
        return sorted(variant_texts())
    ids = sorted(d for d, r in splits.items() if r["split"] == split)
    if split == "train":
        fs = set(json.loads(FEWSHOT_JSON.read_text(encoding="utf-8")).get("fewshot_doc_ids", []))
        ids = [d for d in ids if d not in fs]
    return ids


def per_doc(cond, split, ids):
    """{doc_id: 문서 1건의 채점 결과(완전 정답 두 기준, PRF별 tp/fp/fn, 스키마, 제품명)}"""
    var = variant_texts() if split == "val_var" else {}
    out = {}
    for d in ids:
        gold = json.loads((GOLD_DIRS[split] / f"{base_doc(d)}.json").read_text(encoding="utf-8"))
        pred, _, _ = load_prediction(OUTPUT_ROOT / cond / split / f"{d}.json")
        tp = TEXT_DIR / f"{d}.txt"
        source = var[d] if var else (tp.read_text(encoding="utf-8") if tp.exists() else None)
        acc = Acc()
        det = score_doc(gold, pred or {}, acc, False, defaultdict(set), source)
        exact, ext = doc_exact(det, pred)
        out[d] = {"exact": exact, "ext": ext,
                  "schema": bool(pred) and check_schema(pred)[0],
                  "product": det["product_name"]["ok"],
                  **{k: (acc.prf[k].tp, acc.prf[k].fp, acc.prf[k].fn) for k in PRF}}
    return out


def f1(counts):
    tp = sum(c[0] for c in counts)
    fp = sum(c[1] for c in counts)
    fn = sum(c[2] for c in counts)
    return None if tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)


def metric(rows, name):
    if name in PRF:
        return f1([r[name] for r in rows])
    return sum(r[name] for r in rows) / len(rows)


def clusters(docs, group_of):
    """split_group → 그 그룹의 문서 목록 (docs 안에서만)"""
    g = defaultdict(list)
    for d in docs:
        g[group_of[d]].append(d)
    return list(g.values())


def resample(groups, rng):
    """그룹을 복원추출해 뽑힌 그룹의 문서를 모두 이어 붙인다"""
    return [d for _ in groups for d in rng.choice(groups)]


def bootstrap(a, b, docs, name, rng, group_of):
    """B − A 차이의 (점추정, 2.5%, 97.5%). split_group 단위로 복원추출한다.
    채점 대상이 없으면 None, 그룹이 1개면 (점추정, None, None)."""
    ma, mb = metric([a[d] for d in docs], name), metric([b[d] for d in docs], name)
    if ma is None or mb is None:
        return None
    groups = clusters(docs, group_of)
    if len(groups) < 2:
        return mb - ma, None, None
    diffs = []
    for _ in range(B):
        s = resample(groups, rng)
        xa, xb = metric([a[d] for d in s], name), metric([b[d] for d in s], name)
        if xa is not None and xb is not None:
            diffs.append(xb - xa)
    diffs.sort()
    return mb - ma, diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]


def sign_test(w, l):
    """승·패만 센 양측 정확 부호 검정 p값(무승부 제외)"""
    n = w + l
    if n == 0:
        return None
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def fmt_ci(bs):
    if bs is None:
        return "채점 대상 없음"
    if bs[1] is None:
        return f"{bs[0]:+.3f} [그룹 1개 — 계산 안 함]"
    return f"{bs[0]:+.3f} [{bs[1]:+.3f}, {bs[2]:+.3f}]"


def section(title, a, b, docs, na, nb, rng, group_of):
    n_grp = len(clusters(docs, group_of))
    lines = [f"### {title} ({len(docs)}건 · split_group {n_grp}개)", ""]
    lines.append(f"| 문서 완전 정답 | {na} | {nb} | {nb} 승 · 패 · 무 | 차이 {nb}−{na} [95% CI] | 부호 검정 p(참고) |")
    lines.append("|---|---:|---:|---|---|---:|")
    for key, label in (("ext", "확장 기준 (주지표)"), ("exact", "기존 기준")):
        w = sum(b[d][key] and not a[d][key] for d in docs)
        l = sum(a[d][key] and not b[d][key] for d in docs)
        t = len(docs) - w - l
        bs = bootstrap(a, b, docs, key, rng, group_of)
        p = sign_test(w, l)
        lines.append(f"| {label} | {sum(a[d][key] for d in docs)}/{len(docs)} | {sum(b[d][key] for d in docs)}/{len(docs)} "
                     f"| {w} · {l} · {t} | {fmt_ci(bs)} | {'' if p is None else f'{p:.3f}'} |")
    lines += ["", f"| 필드 | {na} | {nb} | 차이 [95% CI] |", "|---|---:|---:|---|"]
    for name, label in (("schema", "스키마 준수율"), ("product", "제품명"), ("ghs", "GHS F1"), ("hcode", "H코드 F1"),
                        ("cas", "CAS F1"), ("pair", "pair F1"), ("nocas", "nocas F1")):
        ma, mb = metric([a[d] for d in docs], name), metric([b[d] for d in docs], name)
        bs = bootstrap(a, b, docs, name, rng, group_of)
        fmt = lambda x: "—" if x is None else f"{x:.3f}"  # noqa: E731
        lines.append(f"| {label} | {fmt(ma)} | {fmt(mb)} | {fmt_ci(bs)} |")
    return lines + [""]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cond_a", help="기준 조건(예: base_fs)")
    ap.add_argument("cond_b", help="비교 조건(예: qlora_final)")
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--out", help="마크다운 저장 경로")
    ap.add_argument("--allow-test", action="store_true", help="test·test2 허용(두 조건 모두 추론이 끝나고 eval/gate.py 검사 통과 시)")
    args = ap.parse_args()

    splits = read_splits()
    ids = doc_ids_for(args.split, splits)
    # test·test2: 정답을 읽기 전에 게이트(두 조건 모두 허용 조건 · 추론 완료 · 실행 기록 · 봉인 · 실험 고정)
    tag = gate_score(args.split, [args.cond_a, args.cond_b], args.allow_test, ids)
    a, b = per_doc(args.cond_a, args.split, ids), per_doc(args.cond_b, args.split, ids)
    rng = random.Random(SEED)
    group_of = {d: splits[base_doc(d)]["split_group"] for d in ids}

    lines = [f"## 짝 비교: {args.cond_a} → {args.cond_b} ({args.split}){' ' + tag if tag else ''}", "",
             f"부트스트랩 {B}회(seed {SEED}), split_group 단위 복원추출"
             f"{'(같은 문서의 표기 변형도 한 그룹으로 함께 뽑힌다)' if args.split == 'val_var' else ''}. "
             "차이는 뒤 조건 − 앞 조건. 부호 검정은 문서 독립을 가정하므로 참고용. "
             "그룹이 적으면 신뢰구간 추정 자체가 불안정하다(문서 수와 그룹 수를 함께 볼 것).", ""]
    lines += section("전체", a, b, ids, args.cond_a, args.cond_b, rng, group_of)
    by_form = defaultdict(list)
    for d in ids:
        by_form[splits[base_doc(d)]["form"]].append(d)
    if len(by_form) > 1:
        for form in sorted(by_form):
            lines += section(f"서식: {form}", a, b, by_form[form], args.cond_a, args.cond_b, rng, group_of)
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"→ {args.out}")


if __name__ == "__main__":
    main()

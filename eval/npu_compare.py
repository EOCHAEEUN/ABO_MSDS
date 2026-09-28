"""
[NPU 트랙] 동등성 비교 — 같은 split에서 기준 조건(GPU)과 후보 조건(OV CPU·NPU) 출력을 문서별로 맞대 본다
(docs/npu_plan.md 4절 "동등성 지표" · 7절 판정)

먼저 돌려 둘 것: 두 조건 모두 eval/score.py --condition X --split S (문서별 _score_detail.json · report/scores.csv)

  python eval/npu_compare.py --ref qlora_r1 --cand qlora_r1_npu_int4cw --split val
  python eval/npu_compare.py --ref qlora_r1 --cand qlora_r1_npu_int4cw --split val_var --write

보는 것
  1. 출력 글자 단위 일치율, 입력 토큰 수 불일치(프롬프트가 달라졌다는 신호 → 1건이라도 있으면 비교 중단 권고)
  2. 문서 완전 정답(확장 기준) 뒤집힘: 기준 정답→후보 오답 / 기준 오답→후보 정답, 문서별로 달라진 필드
  3. scores.csv 지표 나란히(ko subset): 형식 · 핵심 필드 · 무근거 생성 · 다른 칸 오입력 · 시간
  4. 7절 판정(유지 / 부분 유지 / 미달) — 규칙은 아래 verdict()에 고정. 결과를 보고 바꾸지 않는다
정답 파일은 읽지 않는다(채점 결과 파일만 읽음).
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "outputs"
SCORES_CSV = ROOT / "report" / "scores.csv"
SPLITS = ("val", "val_var")
FIELDS = ("product_name", "signal_word", "ghs", "hcode", "htext", "cas", "pair", "nocas")
METRICS = ("parse_rate", "schema_rate", "product_name_acc", "signal_word_acc", "ghs_f1", "hcode_f1", "htext_f1",
           "cas_f1", "pair_f1", "nocas_f1", "doc_exact_rate", "doc_exact_ext_rate", "fab_any_docs",
           "misplace_ke_n", "misplace_content_n", "n_hit_max_new_tokens", "gen_time_mean_s", "input_tokens_mean")
KEY_METRICS = ("product_name_acc", "signal_word_acc", "ghs_f1", "hcode_f1", "cas_f1", "pair_f1", "nocas_f1",
               "doc_exact_ext_rate")


def load_outputs(cond, split):
    d = OUTPUT_ROOT / cond / split
    if not d.is_dir():
        sys.exit(f"출력 폴더 없음: {d.relative_to(ROOT)}")
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))
            if not p.name.startswith("_")}


def load_detail(cond, split):
    p = OUTPUT_ROOT / cond / split / "_score_detail.json"
    if not p.exists():
        sys.exit(f"채점 상세 없음: {p.relative_to(ROOT)} — 먼저 python eval/score.py --condition {cond} --split {split}")
    return json.loads(p.read_text(encoding="utf-8"))["docs"]


def load_scores(cond, split):
    out = {}
    with open(SCORES_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["condition"] == cond and r["split"] == split and r["subset"] == "ko":
                out[r["metric"]] = float(r["value"]) if r["value"] not in ("", None) else None
    return out


def field_ok(detail, field):
    v = detail.get(field)
    return v.get("ok") if isinstance(v, dict) else v == "ok"


def verdict(ref, cand, n_docs):
    """docs/npu_plan.md 7절. 문서 1건 = 1/n_docs"""
    one = 1 / n_docs + 1e-9
    if (cand.get("parse_rate") or 0) < (ref.get("parse_rate") or 0) \
            or (cand.get("schema_rate") or 0) < (ref.get("schema_rate") or 0) \
            or (cand.get("fab_any_docs") or 0) > 0:
        return "미달"
    worse = [m for m in KEY_METRICS
             if ref.get(m) is not None and cand.get(m) is not None and ref[m] - cand[m] > one]
    return f"부분 유지 (문서 2건 이상 하락: {', '.join(worse)})" if worse else "유지"


def judge(rs, cs, n, only):
    if only:
        return "판정 불가 — 두 조건의 문서 구성이 다름"
    if not rs or not cs:
        return "판정 불가 — scores.csv에 두 조건 행이 없음"
    return verdict(rs, cs, n)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", required=True, help="기준 조건 (GPU, 예: qlora_r1)")
    ap.add_argument("--cand", required=True, help="후보 조건 (예: qlora_r1_npu_int4cw)")
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--write", action="store_true", help="report/npu/{cand}_{split}.md로 저장")
    args = ap.parse_args()

    ro, co = load_outputs(args.ref, args.split), load_outputs(args.cand, args.split)
    rd, cd = load_detail(args.ref, args.split), load_detail(args.cand, args.split)
    docs = sorted(set(ro) | set(co))
    only = sorted(set(ro) ^ set(co))

    lines = [f"# NPU 동등성 비교 — {args.cand} vs {args.ref} ({args.split})", ""]
    if only:
        lines += [f"**문서 구성이 다름** (한쪽에만 있음): {', '.join(only)} — 같은 문서로 다시 돌린 뒤 비교할 것", ""]

    same_raw = [d for d in docs if d in ro and d in co and ro[d].get("raw_output") == co[d].get("raw_output")]
    tok_diff = [d for d in docs if d in ro and d in co and not co[d].get("skipped")
                and ro[d].get("input_tokens") != co[d].get("input_tokens")]
    skipped = {d: co[d]["skipped"] for d in docs if d in co and co[d].get("skipped")}
    lost = [d for d in docs if rd.get(d, {}).get("exact_ext") and not cd.get(d, {}).get("exact_ext")]
    gained = [d for d in docs if cd.get(d, {}).get("exact_ext") and not rd.get(d, {}).get("exact_ext")]

    lines += ["## 1. 출력 일치", "",
              f"- 문서 {len(docs)}건 중 출력 글자 단위 일치 {len(same_raw)}건 ({len(same_raw) / max(len(docs), 1):.0%})",
              f"- 입력 토큰 수 불일치 {len(tok_diff)}건" + (f": {', '.join(tok_diff)} — **프롬프트가 다름. 비교 중단 권고**"
                                                     if tok_diff else ""),
              f"- 후보에서 건너뜀 {len(skipped)}건" + (f": {skipped}" if skipped else ""), ""]

    lines += ["## 2. 문서 완전 정답(확장) 뒤집힘", "",
              f"- 기준 정답 → 후보 오답 {len(lost)}건 / 기준 오답 → 후보 정답 {len(gained)}건", "",
              "| 문서 | 기준 | 후보 | 달라진 필드 |", "|---|---|---|---|"]
    for d in docs:
        r, c = rd.get(d, {}), cd.get(d, {})
        changed = [f for f in FIELDS if field_ok(r, f) != field_ok(c, f)]
        if r.get("misplaced") != c.get("misplaced"):
            changed.append(f"misplaced {r.get('misplaced')}→{c.get('misplaced')}")
        if bool(r.get("schema_errors")) != bool(c.get("schema_errors")):
            changed.append("schema")
        if changed or r.get("exact_ext") != c.get("exact_ext"):
            lines.append(f"| {d} | {'O' if r.get('exact_ext') else 'X'} | {'O' if c.get('exact_ext') else 'X'} "
                         f"| {', '.join(changed) or '-'} |")
    lines.append("")

    rs, cs = load_scores(args.ref, args.split), load_scores(args.cand, args.split)
    lines += ["## 3. 지표 (scores.csv, ko)", "", f"| 지표 | {args.ref} | {args.cand} |", "|---|---:|---:|"]
    fmt = lambda v: "-" if v is None else (f"{v:.4f}" if isinstance(v, float) and not v.is_integer() else f"{v:g}")
    lines += [f"| {m} | {fmt(rs.get(m))} | {fmt(cs.get(m))} |" for m in METRICS]
    ttft = [co[d]["ttft_sec"] for d in docs if d in co and co[d].get("ttft_sec") is not None]
    tput = [co[d]["throughput_tok_s"] for d in docs if d in co and co[d].get("throughput_tok_s") is not None]
    if ttft:
        lines.append(f"| ttft_mean_s | - | {mean(ttft):.2f} |")
    if tput:
        lines.append(f"| throughput_tok_s_mean | - | {mean(tput):.1f} |")
    lines.append("")

    n = int(rs.get("n_docs") or len(docs))
    lines += ["## 4. 판정 (docs/npu_plan.md 7절)", "",
              f"**{judge(rs, cs, n, only)}**", "",
              f"val {n}건 규모의 pilot 판정이다." + (" val_var는 같은 문서의 표기 변형이라 독립 건수가 아니다."
                                                if args.split == "val_var" else "")]

    text = "\n".join(lines) + "\n"
    print(text)
    if args.write:
        out = ROOT / "report" / "npu" / f"{args.cand}_{args.split}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"기록: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

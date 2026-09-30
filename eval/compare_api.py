"""
외부 API 비교군(eval/infer_openai.py) ↔ 본 비교군(base_zs · base_fs · qlora_r1) val 비교표 + 짝 비교.

점수: 본 비교군은 report/scores.csv, API 비교군은 report/api/scores_openai.csv(score.py --scores-csv).
짝 비교: 두 조건의 _score_detail.jsonl을 eval/paired.py와 같은 방식(문서별 맞음/틀림, 제조사 그룹 부트스트랩)으로.
결과는 report/api/openai_val.md 한 곳에만 쓴다(report/paired.csv에는 쓰지 않음). val은 조건 선택용이며 최종 수치가 아니다.

  python3 eval/compare_api.py                        # outputs/api/ 아래 채점된 조건 모두
  python3 eval/compare_api.py --api gpt-5-mini_zs --ref qlora_r1
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.paired import DETAIL_FILE, NO_WORSE, compare, doc_outcomes, read_detail, read_splits  # noqa: E402
from eval.score import SPLITS_CSV  # noqa: E402

API_ROOT = ROOT / "outputs" / "api"
API_SCORES = ROOT / "report" / "api" / "scores_openai.csv"
MAIN_SCORES = ROOT / "report" / "scores.csv"
REPORT = ROOT / "report" / "api" / "openai_val.md"
REFS = ("base_zs", "base_fs", "qlora_r1")
SHOW = [("parse_rate", "파싱률"), ("schema_rate", "스키마"), ("product_name_acc", "제품명"), ("signal_word_acc", "신호어"),
        ("ghs_f1", "GHS F1"), ("hcode_f1", "H코드 F1"), ("cas_f1", "CAS F1"), ("pair_f1", "pair F1"),
        ("nocas_f1", "CAS 없는 성분 F1"), ("doc_exact_rate", "문서 완전 정답"), ("doc_exact_ext_rate", "문서 완전 정답(확장)"),
        ("fab_any_docs", "무근거 생성 문서"), ("misplace_ke_n", "KE 칸 오입력"), ("n_hit_max_new_tokens", "생성 한도 도달"),
        ("gen_time_mean_s", "문서당 시간(초)"), ("input_tokens_mean", "입력 토큰*"), ("output_tokens_mean", "출력 토큰*")]
PAIRED = ["parse_rate", "schema_rate", "product_name_acc", "signal_word_acc", "ghs_classification", "hazard_statements",
          "cas", "pair", "nocas", "doc_exact_ext"]


def read_scores(path, split="val", subset="ko"):
    out = {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r["split"] == split and r["subset"] == subset and r["value"] != "":
                    out.setdefault(r["condition"], {})[r["metric"]] = float(r["value"])
    return out


def fmt(v, metric):
    if v is None:
        return "—"
    if metric.endswith(("_n", "_docs")) or metric.startswith("n_") or "tokens" in metric:
        return f"{v:,.0f}"
    if metric.endswith("_s") or metric.endswith("_mean"):
        return f"{v:.1f}"
    return f"{v:.3f}".rstrip("0").rstrip(".") if v not in (0, 1) else f"{v:.1f}"


def run_info(cond):
    p = API_ROOT / cond / "val" / "_run.jsonl"
    run = json.loads(p.read_text(encoding="utf-8").splitlines()[0]) if p.exists() else {}
    logs = [json.loads(x) for x in (API_ROOT / cond / "val" / "_log.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()] if (API_ROOT / cond / "val" / "_log.jsonl").exists() else []
    last = {r["doc_id"]: r for r in logs}
    reasoning = [r["reasoning_tokens"] for r in last.values() if r.get("reasoning_tokens") is not None]
    return run, last, (mean(reasoning) if reasoning else None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", nargs="*", help="API 조건 이름(기본: report/api/scores_openai.csv의 val 조건 전부)")
    ap.add_argument("--ref", default="qlora_r1", help="짝 비교 기준(기본 qlora_r1)")
    ap.add_argument("--out", default=REPORT)
    args = ap.parse_args(argv)

    api_scores, main_scores = read_scores(API_SCORES), read_scores(MAIN_SCORES)
    apis = args.api or sorted(api_scores)
    if not apis:
        sys.exit(f"API 점수가 없다: {API_SCORES}. eval/score.py --scores-csv로 먼저 채점할 것")
    missing = [c for c in apis if c not in api_scores]
    if missing:
        sys.exit(f"점수 없는 API 조건: {missing}")
    cols = [(c, main_scores.get(c, {})) for c in REFS] + [(c, api_scores[c]) for c in apis]

    lines = ["# 외부 API 비교군 — val (조건 선택용, 최종 수치 아님)", "",
             "본 비교군(base_zs · base_fs · qlora_r1)과 같은 입력 · 프롬프트(v1) · 채점기(eval/score.py)로 비교했다. "
             "API 비교군은 런타임 · 토크나이저 · 디코딩이 달라 report/scores.csv에 넣지 않는다.", "",
             "## 실행 조건", "", "| 조건 | 모델(응답) | 추론 강도 | 생성 한도 | few-shot | 평균 추론 토큰 | API 실패 |", "|---|---|---|---|---|---|---|"]
    for c in apis:
        run, last, reasoning = run_info(c)
        models = sorted({r["response_model"] for r in last.values() if r.get("response_model")})
        fails = sum(1 for r in last.values() if str(r.get("skipped") or "").startswith("API_ERROR"))
        lines.append(f"| {c} | {', '.join(models) or run.get('model', '—')} | {run.get('reasoning_effort') or '—'} | "
                     f"{run.get('max_new_tokens', '—')} | {' · '.join(run.get('fewshot_doc_ids') or []) or '없음'} | "
                     f"{fmt(reasoning, 'x_tokens') if reasoning is not None else '—'} | {fails} |")

    lines += ["", "## 지표", "", "| 지표 | " + " | ".join(c for c, _ in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for metric, name in SHOW:
        lines.append(f"| {name} | " + " | ".join(fmt(s.get(metric), metric) for _, s in cols) + " |")
    lines += ["", "\\* 토큰 수는 토크나이저가 달라(Qwen ↔ OpenAI) 조건 사이에 직접 비교하지 않는다. "
              "gpt-5 계열의 출력 토큰에는 추론 토큰이 들어 있다. 시간은 로컬 GPU ↔ 원격 API라 속도 우열 근거가 아니다.", ""]

    group_of = {d: r["split_group"] for d, r in read_splits(SPLITS_CSV).items()}
    ref_head, ref_det = read_detail(ROOT / "outputs" / args.ref / "val" / DETAIL_FILE)
    lines += [f"## 짝 비교 (API − {args.ref}, 문서별 맞음/틀림, 제조사 그룹 부트스트랩 95% 구간)", ""]
    for c in apis:
        head, det = read_detail(API_ROOT / c / "val" / DETAIL_FILE)
        if set(det) != set(ref_det) or head.get("include_non_ghs") != ref_head.get("include_non_ghs"):
            sys.exit(f"[거부] {c}와 {args.ref}의 채점 문서 · 설정이 다르다")
        ids = sorted(det)
        rows = {r["metric"]: r for r in compare({d: doc_outcomes(det[d]) for d in ids},
                                                 {d: doc_outcomes(ref_det[d]) for d in ids}, group_of, ids)}
        lines += [f"### {c} − {args.ref}  (문서 {len(ids)}건 · 그룹 {len({group_of[d] for d in ids})}개)", "",
                  "| 지표 | 이김 | 짐 | 같음 | 평균 차이 | 95% 구간 |", "|---|---|---|---|---|---|"]
        for m in PAIRED:
            r = rows[m]
            ci = f"[{r['ci_low']:+.2f}, {r['ci_high']:+.2f}]" if r["ci_low"] is not None else "—"
            lines.append(f"| {m} | {r['win']} | {r['loss']} | {r['tie']} | {r['mean_diff']:+.2f} | {ci} |")
        worse = [m for m in NO_WORSE if api_scores[c].get(m) is not None and main_scores.get(args.ref, {}).get(m) is not None
                 and api_scores[c][m] < main_scores[args.ref][m]]
        changed = [(d, m) for d in ids for m in ("doc_exact_ext",) if doc_outcomes(det[d])[m] != doc_outcomes(ref_det[d])[m]]
        lines += ["", f"- {args.ref}보다 낮은 악화 불허 필드: {', '.join(worse) or '없음'}",
                  "- 문서 완전 정답(확장)이 갈린 문서: "
                  + (", ".join(f"{d}({'API만 정답' if doc_outcomes(det[d])[m] else args.ref + '만 정답'})" for d, m in changed)
                     or "없음"), ""]
    lines += ["val 10건 · 8그룹이라 문서 1건 차이가 0.1이다. 구간이 0을 포함하면 차이를 확인하지 못한 것이다(동등하다는 뜻이 아니다)."]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()

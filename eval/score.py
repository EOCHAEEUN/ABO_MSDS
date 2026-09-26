"""
평가 채점기
"""
"""
[양세윤] 파싱률·스키마·필드별·CAS F1·pair F1·H코드 F1

outputs/{condition}/{split}/{doc_id}.json(infer.py 결과)을 정답과 비교해
report/scores.csv에 (condition, split, subset, metric, value)로 기록한다.
subset은 ko / en으로 나눠 쓰고 합산하지 않는다(기획서 보고 원칙).

  python eval/score.py --condition base_zs --split val
  python eval/score.py --condition qlora_final --split test      # 봉인 대조 통과해야 실행
  python eval/score.py --split val --self-check                  # 정답을 예측으로 넣어 1.0이 나오는지 점검

채점 규칙 (data/README.md "채점기 구현 메모")
- 파싱률·스키마 준수율: 전체 문서 기준. 출력 파일이 없거나 NOT_FOUND로 건너뛴 문서도 실패로 센다.
- 파싱에 실패한 문서는 "빈 예측"으로 보고 모든 필드를 채점한다(정답 항목은 전부 FN).
- 제품명: 공백 제거 후 (상태, 값) 완전 일치.
- 신호어: 위험/경고 정규화 후 (상태, 값) 완전 일치.
- GHS 분류: hazard_class_alias.csv로 정규 분류명으로 바꾼 뒤 (정규 분류명, 구분 N) 집합 비교 → micro P/R/F1.
  별칭표 밖의 분류명은 공백만 무시하고 비교하며, 목록을 따로 출력한다(별칭표 보강용).
  "(GHS 외 ...)"로 정규화되는 항목은 기본 제외(--include-non-ghs로 포함, A16 PM 판정 대기).
- 분류·문구 목록 상태(기재/자료없음/해당없음): 문서별 일치율. 해당없음 문서는 여기서 채점된다.
- H코드: code가 있는 문구만, "H302+H332"는 개별 코드로 쪼개 집합 비교 → micro P/R/F1.
- H코드 없는 문구: code가 null인 문구끼리 문구(NFKC·공백 제거·끝 마침표 제거) 집합 비교 → 별도 P/R/F1.
- CAS: 문서별 CAS 집합(중복 1건) → micro P/R/F1. cas_number가 null인 성분은 제외.
- pair: CAS로 짝짓고, 같은 CAS 안에서 함유량 min/max가 같은 것끼리 1:1 매칭(중복 CAS는 각각 셈).
  content_acc = CAS로 짝지어진 성분 중 함유량까지 맞은 비율(pair 오류가 CAS 탓인지 함유량 탓인지 구분용).
- ke_number·chemical_name·is_substitute_data·supplier 등 참고 필드는 채점하지 않는다.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.normalize import (  # noqa: E402
    canon_hazard_class,
    class_key,
    content_equal,
    is_non_ghs,
    norm_cas,
    norm_category,
    norm_product_name,
    norm_signal_word,
    norm_statement_text,
    split_hcodes,
)
from core.schema import check_schema, extract_json  # noqa: E402
from eval.seal import verify as verify_seal  # noqa: E402

SPLITS_CSV = ROOT / "data" / "splits.csv"
SCORES_CSV = ROOT / "report" / "scores.csv"
OUTPUT_ROOT = ROOT / "outputs"
GOLD_DIRS = {"val": ROOT / "data" / "labels", "test": ROOT / "eval" / "test", "val_en": ROOT / "eval" / "val_en",
             "train": ROOT / "data" / "labels"}  # train: Base 난이도 진단 전용 — scores.csv에 쓰지 않는다
FEWSHOT_JSON = ROOT / "eval" / "fewshot.json"
SPLITS = tuple(GOLD_DIRS)


# ---------------------------------------------------------------- 모델 출력은 스키마를 어길 수 있으니 방어적으로 꺼낸다
def _dict(x):
    return x if isinstance(x, dict) else {}


def _items(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def _str(x):
    if x is None or isinstance(x, str):
        return x
    return str(x)


def value_field(obj, key):
    f = _dict(obj.get(key))
    return _str(f.get("source_status")), _str(f.get("value"))


def list_status(obj, key):
    return _str(_dict(obj.get("list_status")).get(key))


# ---------------------------------------------------------------- 항목 → 비교 키
def ghs_keys(obj, include_non_ghs, unknown, who):
    keys = set()
    for it in _items(obj.get("ghs_classification")):
        raw = _str(it.get("hazard_class"))
        if not raw:
            continue
        canon, known = canon_hazard_class(raw)
        if not known:
            unknown[raw].add(who)
        if is_non_ghs(canon) and not include_non_ghs:
            continue
        keys.add((class_key(canon), norm_category(_str(it.get("category")))))
    return keys


def hcode_set(obj):
    codes = set()
    for it in _items(obj.get("hazard_statements")):
        codes.update(split_hcodes(_str(it.get("code"))))
    return codes


def htext_set(obj):
    return {
        norm_statement_text(_str(it.get("text")))
        for it in _items(obj.get("hazard_statements"))
        if not _str(it.get("code")) and _str(it.get("text"))
    }


def ingredients(obj):
    """[(정규화 CAS | None, 함유량 원문), ...]"""
    return [(norm_cas(_str(it.get("cas_number"))), it.get("content")) for it in _items(obj.get("ingredients"))]


def pair_match(gold_ings, pred_ings):
    """CAS로 짝짓고 같은 CAS 안에서 함유량이 같은 것끼리 1:1 매칭.
    반환: tp, fp, fn, CAS로 짝지어진 수, 상세(함유량 불일치 목록)"""
    g_by, p_by = defaultdict(list), defaultdict(list)
    for cas, content in gold_ings:
        if cas:
            g_by[cas].append(content)
    for cas, content in pred_ings:
        if cas:
            p_by[cas].append(content)
    tp = cas_paired = 0
    mismatch = []
    for cas in sorted(set(g_by) & set(p_by)):
        g_left = list(g_by[cas])
        matched = 0
        for pv in p_by[cas]:
            for i, gv in enumerate(g_left):
                if content_equal(gv, pv):
                    g_left.pop(i)
                    matched += 1
                    break
        n_pair = min(len(g_by[cas]), len(p_by[cas]))
        cas_paired += n_pair
        tp += matched
        if matched < n_pair or len(g_by[cas]) != len(p_by[cas]):
            mismatch.append({"cas": cas, "gold_content": g_by[cas], "pred_content": p_by[cas]})
    n_gold = sum(map(len, g_by.values()))
    n_pred = sum(map(len, p_by.values()))
    return tp, n_pred - tp, n_gold - tp, cas_paired, mismatch


# ---------------------------------------------------------------- 집계
class PRF:
    def __init__(self):
        self.tp = self.fp = self.fn = 0

    def add(self, tp, fp, fn):
        self.tp += tp
        self.fp += fp
        self.fn += fn

    def add_sets(self, gold, pred):
        tp, fp, fn = gold & pred, pred - gold, gold - pred
        self.add(len(tp), len(fp), len(fn))
        s = lambda x: sorted(x, key=str)  # noqa: E731  (None이 섞인 튜플 정렬용)
        return {"tp": s(tp), "fp": s(fp), "fn": s(fn)}

    def result(self):
        """(P, R, F1). 정답·예측이 모두 0건이면 채점 대상 없음 → None."""
        if self.tp + self.fp + self.fn == 0:
            return None, None, None
        p = self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0
        r = self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0
        f1 = 2 * self.tp / (2 * self.tp + self.fp + self.fn)
        return p, r, f1


class Acc:
    PRF_NAMES = ("ghs", "hcode", "htext", "cas", "pair")
    HIT_NAMES = ("product_name", "signal_word", "ghs_status", "hazard_status")

    def __init__(self):
        self.n = self.parsed = self.schema_ok = self.missing = self.hit_max = 0
        self.hits = defaultdict(int)
        self.prf = defaultdict(PRF)
        self.cas_paired = 0
        self.gen_time, self.in_tok, self.out_tok = [], [], []

    def rows(self):
        n = self.n or 1
        out = [
            ("n_docs", self.n),
            ("n_missing_output", self.missing),
            ("parse_rate", self.parsed / n),
            ("schema_rate", self.schema_ok / n),
        ]
        out += [(f"{k}_acc", self.hits[k] / n) for k in self.HIT_NAMES]
        for name in self.PRF_NAMES:
            p, r, f1 = self.prf[name].result()
            out += [(f"{name}_p", p), (f"{name}_r", r), (f"{name}_f1", f1)]
        out.append(("content_acc", self.prf["pair"].tp / self.cas_paired if self.cas_paired else None))
        out += [
            ("gen_time_mean_s", mean(self.gen_time) if self.gen_time else None),
            ("input_tokens_mean", mean(self.in_tok) if self.in_tok else None),
            ("output_tokens_mean", mean(self.out_tok) if self.out_tok else None),
            ("n_hit_max_new_tokens", self.hit_max),
        ]
        return out


# ---------------------------------------------------------------- 문서 1건 채점
def score_doc(gold, pred, acc, include_non_ghs, unknown):
    detail = {}

    gs, gv = value_field(gold, "product_name")
    ps, pv = value_field(pred, "product_name")
    ok = gs == ps and norm_product_name(gv) == norm_product_name(pv)
    acc.hits["product_name"] += ok
    detail["product_name"] = {"ok": ok, "gold": [gs, gv], "pred": [ps, pv]}

    gs, gv = value_field(gold, "signal_word")
    ps, pv = value_field(pred, "signal_word")
    ok = gs == ps and norm_signal_word(gv) == norm_signal_word(pv)
    acc.hits["signal_word"] += ok
    detail["signal_word"] = {"ok": ok, "gold": [gs, gv], "pred": [ps, pv]}

    for key, name in (("ghs_classification", "ghs_status"), ("hazard_statements", "hazard_status")):
        g, p = list_status(gold, key), list_status(pred, key)
        acc.hits[name] += g == p
        if g != p:
            detail[name] = {"gold": g, "pred": p}

    detail["ghs"] = acc.prf["ghs"].add_sets(
        ghs_keys(gold, include_non_ghs, unknown, "gold"), ghs_keys(pred, include_non_ghs, unknown, "pred")
    )
    detail["hcode"] = acc.prf["hcode"].add_sets(hcode_set(gold), hcode_set(pred))
    detail["htext"] = acc.prf["htext"].add_sets(htext_set(gold), htext_set(pred))

    g_ings, p_ings = ingredients(gold), ingredients(pred)
    detail["cas"] = acc.prf["cas"].add_sets({c for c, _ in g_ings if c}, {c for c, _ in p_ings if c})
    tp, fp, fn, paired, mismatch = pair_match(g_ings, p_ings)
    acc.prf["pair"].add(tp, fp, fn)
    acc.cas_paired += paired
    detail["pair"] = {"tp": tp, "fp": fp, "fn": fn, "content_mismatch": mismatch}

    # 상세 파일을 읽기 쉽게: 틀린 게 없는 항목은 "ok"로 줄인다
    for k in ("ghs", "hcode", "htext", "cas"):
        if not detail[k]["fp"] and not detail[k]["fn"]:
            detail[k] = "ok"
    if not mismatch and not fp and not fn:
        detail["pair"] = "ok"
    return detail


# ---------------------------------------------------------------- 입출력
def read_splits():
    with open(SPLITS_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r for r in csv.DictReader(f)}


def load_prediction(path):
    """→ (예측 dict | None, 레코드 dict | None, 실패 사유)"""
    if not path.exists():
        return None, None, "출력 파일 없음"
    rec = json.loads(path.read_text(encoding="utf-8"))
    if rec.get("skipped"):
        return None, rec, f"건너뜀({rec['skipped']})"
    obj, err = extract_json(rec.get("raw_output"))
    return obj, rec, err


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def upsert_scores(condition, split, rows):
    """같은 (condition, split)의 이전 기록을 지우고 새로 쓴다."""
    kept = []
    if SCORES_CSV.exists():
        with open(SCORES_CSV, encoding="utf-8-sig", newline="") as f:
            kept = [r for r in csv.DictReader(f) if not (r["condition"] == condition and r["split"] == split)]
    with open(SCORES_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["condition", "split", "subset", "metric", "value"], lineterminator="\n")
        w.writeheader()
        w.writerows(kept)
        for subset, metric, value in rows:
            w.writerow({"condition": condition, "split": split, "subset": subset, "metric": metric, "value": fmt(value)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--condition", help="outputs/ 아래 조건 폴더 이름 (base_zs, base_fs, qlora_r1, ...)")
    ap.add_argument("--split", required=True, choices=SPLITS)
    ap.add_argument("--include-non-ghs", action="store_true", help="Simple Asphyxiant 같은 GHS 외 항목도 채점")
    ap.add_argument("--self-check", action="store_true", help="정답을 예측으로 넣어 채점기 자체를 점검(파일 안 씀)")
    ap.add_argument("--no-write", action="store_true", help="scores.csv·상세 파일을 쓰지 않고 화면에만 출력")
    args = ap.parse_args()

    if not args.self_check and not args.condition:
        ap.error("--condition이 필요함(--self-check일 때만 생략 가능)")
    if args.split == "test" and not args.self_check:
        ok, msg = verify_seal()
        if not ok:
            sys.exit(f"[중단] Test 봉인 대조 실패: {msg}")
        print(msg)

    splits = read_splits()
    doc_ids = sorted(d for d, r in splits.items() if r["split"] == args.split)
    if args.split == "train":
        fs = set(json.loads(FEWSHOT_JSON.read_text(encoding="utf-8")).get("fewshot_doc_ids", []))
        doc_ids = [d for d in doc_ids if d not in fs]
    gold_dir = GOLD_DIRS[args.split]
    pred_dir = OUTPUT_ROOT / (args.condition or "_self_check") / args.split

    accs = defaultdict(Acc)
    unknown = defaultdict(set)
    details = {}
    for doc_id in doc_ids:
        gold_path = gold_dir / f"{doc_id}.json"
        if not gold_path.exists():
            sys.exit(f"정답 파일 없음: {gold_path}")
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        g_ok, g_err = check_schema(gold)
        if not g_ok:
            print(f"[경고] 정답 {doc_id}가 스키마를 어김: {g_err[:3]}")

        if args.self_check:
            pred, rec, err = gold, None, None
        else:
            pred, rec, err = load_prediction(pred_dir / f"{doc_id}.json")

        lang = splits[doc_id]["lang"]
        acc = accs[lang]
        acc.n += 1
        d = {"lang": lang}
        if not args.self_check and (rec is None or rec.get("skipped")):
            acc.missing += 1
        if rec and not rec.get("skipped"):
            acc.gen_time.append(rec["gen_time_sec"])
            acc.in_tok.append(rec["input_tokens"])
            acc.out_tok.append(rec["output_tokens"])
            acc.hit_max += bool(rec.get("hit_max_new_tokens"))

        if pred is None:
            d["parse_error"] = err
            pred = {}
        else:
            acc.parsed += 1
            s_ok, s_err = check_schema(pred)
            acc.schema_ok += s_ok
            if not s_ok:
                d["schema_errors"] = s_err[:10]
        d.update(score_doc(gold, pred, acc, args.include_non_ghs, unknown))
        details[doc_id] = d

    rows = [(subset, m, v) for subset in sorted(accs) for m, v in accs[subset].rows()]

    # 화면 출력: 지표 × subset 표
    subsets = sorted(accs)
    table = {s: dict(accs[s].rows()) for s in subsets}
    print(f"\n[{args.condition or 'self-check'} / {args.split}]  " + "  ".join(f"{s}={accs[s].n}건" for s in subsets))
    print(f"{'metric':<24}" + "".join(f"{s:>10}" for s in subsets))
    for metric in table[subsets[0]]:
        print(f"{metric:<24}" + "".join(f"{fmt(table[s][metric]):>10}" for s in subsets))

    if unknown:
        print("\n[별칭표에 없는 분류명] eval/hazard_class_alias.csv 보강 후보:")
        for raw in sorted(unknown):
            print(f"  - {raw!r}  ({'/'.join(sorted(unknown[raw]))})")

    if args.self_check:
        bad = sorted({m for s in subsets for m, v in table[s].items()
                      if m.endswith(("_acc", "_rate", "_p", "_r", "_f1")) and v is not None and v < 1.0})
        print("\nself-check:", "통과 (채점 대상 지표 모두 1.0)" if not bad else f"실패 — 1.0이 아닌 지표 {bad}")
        sys.exit(0 if not bad else 1)

    if not args.no_write:
        if args.split != "train":  # 진단 점수는 보고용 scores.csv와 섞지 않는다
            upsert_scores(args.condition, args.split, rows)
        detail_path = pred_dir / "_score_detail.json"
        detail_path.write_text(
            json.dumps({"include_non_ghs": args.include_non_ghs, "unknown_hazard_classes": sorted(unknown),
                        "docs": details}, ensure_ascii=False, indent=2, default=list),
            encoding="utf-8",
        )
        where = "scores.csv에는 안 씀(진단 전용)" if args.split == "train" else f"기록: {SCORES_CSV.relative_to(ROOT)}"
        print(f"\n{where}  /  문서별 상세: {detail_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
"""
[양세윤] 채점기 회귀 테스트 — 입력은 test/fixtures/(옛 라벨, 코드 테스트 전용)

한 필드만 일부러 틀린 예측이 그 필드에서만 틀린 것으로 잡히는지 본다.
self-check(정답 = 예측)는 "다 맞으면 1.0"만 확인하므로, 파일럿에서 nocas 계산이 pair 판정 변수를 덮어써
문서 완전 정답이 틀리게 나온 버그를 잡지 못했다(docs/plan.md 12절). 그 경우를 포함해 고정한다.
채점기를 고치면 이 파일도 같이 고치고 통과시킨다(plan 5절).

  python3 test/test_score.py -v
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.score import Acc, doc_exact, score_doc, score_docs  # noqa: E402

FIX = ROOT / "test" / "fixtures"
GSC = "KR-GSC-001"      # 성분 4 (CAS 있는 3 + 영업비밀 1, CAS null)
NOROO = "KR-NOROO-004"  # H코드 있는 문구, 영업비밀 성분
OLD = "KR-NOROO-005"    # H코드 없는 문구(구서식)


def label(doc_id):
    return json.loads((FIX / "labels" / f"{doc_id}.json").read_text(encoding="utf-8"))


def text(doc_id):
    return (FIX / "text" / f"{doc_id}.txt").read_text(encoding="utf-8")


def run(gold, pred, source=None):
    acc = Acc()
    d = score_doc(gold, pred, acc, False, defaultdict(set), source)
    exact, ext = doc_exact(d, pred)
    return d, dict(acc.rows()), exact, ext


def first_cas_idx(lab):
    return next(i for i, c in enumerate(lab["ingredients"]) if c["cas_number"])


class ScoreDocTest(unittest.TestCase):
    def test_identical_is_all_ok(self):
        for doc_id in (GSC, NOROO, OLD):
            g = label(doc_id)
            d, m, exact, ext = run(g, copy.deepcopy(g), text(doc_id))
            self.assertTrue(exact and ext, doc_id)
            self.assertTrue(all(d[k] == "ok" for k in ("ghs", "hcode", "htext", "cas", "pair", "nocas")), doc_id)
            self.assertEqual((m["misplace_ke_n"], m["misplace_content_n"], m["fab_any_docs"]), (0, 0, 0), doc_id)

    def test_pair_only_wrong(self):
        """CAS는 맞고 함유량만 틀림 → pair만 오답, 두 기준 모두 오답"""
        g = label(GSC)
        p = copy.deepcopy(g)
        p["ingredients"][first_cas_idx(p)]["content"] = "50~60"
        d, m, exact, ext = run(g, p)
        self.assertNotEqual(d["pair"], "ok")
        self.assertEqual((d["cas"], d["nocas"]), ("ok", "ok"))
        self.assertFalse(exact or ext)

    def test_nocas_only_wrong_keeps_legacy_exact(self):
        """CAS 없는 성분만 하나 더 지어냄 → nocas만 오답. 기존 기준은 정답, 확장 기준만 오답(파일럿 버그 회귀)"""
        g = label(GSC)
        p = copy.deepcopy(g)
        p["ingredients"].append({"chemical_name": "영업비밀2", "cas_number": None, "ke_number": None,
                                 "content": "1~2", "is_substitute_data": True})
        d, m, exact, ext = run(g, p)
        self.assertEqual((d["pair"], d["cas"]), ("ok", "ok"))
        self.assertEqual(d["nocas"]["fp"], 1)
        self.assertTrue(exact)
        self.assertFalse(ext)

    def test_substitute_flag_wrong(self):
        """영업비밀 성분의 is_substitute_data만 틀림 → nocas 오답"""
        g = label(GSC)
        p = copy.deepcopy(g)
        for c in p["ingredients"]:
            c["is_substitute_data"] = False
        d, m, exact, ext = run(g, p)
        self.assertNotEqual(d["nocas"], "ok")
        self.assertEqual(d["pair"], "ok")
        self.assertTrue(exact)
        self.assertFalse(ext)

    def test_ec_number_in_ke_field(self):
        """EC 번호를 ke_number에 넣음 → misplace_ke 1, 확장 기준 오답"""
        g = label(GSC)
        p = copy.deepcopy(g)
        p["ingredients"][first_cas_idx(p)]["ke_number"] = "265-157-1"
        d, m, exact, ext = run(g, p)
        self.assertEqual((m["misplace_ke_n"], m["misplace_content_n"]), (1, 0))
        self.assertFalse(ext)

    def test_cas_in_content_field(self):
        """함유량 칸에 CAS → misplace_content 1, pair 오답"""
        g = label(GSC)
        p = copy.deepcopy(g)
        i = first_cas_idx(p)
        p["ingredients"][i]["content"] = p["ingredients"][i]["cas_number"]
        d, m, exact, ext = run(g, p)
        self.assertEqual(m["misplace_content_n"], 1)
        self.assertNotEqual(d["pair"], "ok")
        self.assertFalse(exact or ext)

    def test_fabricated_h_code(self):
        """원문에 없는 H코드를 붙임 → 무근거 생성 1, H코드 오답"""
        g = label(NOROO)
        p = copy.deepcopy(g)
        p["hazard_statements"].append({"code": "H999", "text": "지어낸 문구"})
        d, m, exact, ext = run(g, p, text(NOROO))
        self.assertEqual(d["fabricated"]["hcode"], ["H999"])
        self.assertEqual(m["fab_hcode_n"], 1)
        self.assertNotEqual(d["hcode"], "ok")
        self.assertFalse(exact)

    def test_guessed_code_on_old_form(self):
        """H코드 없는 문구에 코드를 추정해 붙임 → htext FN + 무근거 생성"""
        g = label(OLD)
        p = copy.deepcopy(g)
        p["hazard_statements"][0]["code"] = "H225"
        d, m, exact, ext = run(g, p, text(OLD))
        self.assertNotEqual(d["htext"], "ok")
        self.assertEqual(d["fabricated"]["hcode"], ["H225"])
        self.assertFalse(exact)

    def test_split_cas_is_not_fabricated(self):
        """PDF에서 "134759-18-" / "5"로 줄이 갈린 CAS를 무근거 생성으로 세지 않는다"""
        g = label(GSC)
        p = copy.deepcopy(g)
        p["ingredients"][first_cas_idx(p)]["cas_number"] = "134759-18-5"
        source = text(GSC) + "\n134759-18-\n5\n"
        d, m, exact, ext = run(g, p, source)
        self.assertEqual(m["fab_cas_n"], 0)
        d, m, exact, ext = run(g, p, text(GSC))
        self.assertEqual(m["fab_cas_n"], 1)

    def test_empty_prediction_counts_everything_missing(self):
        """파싱 실패(빈 예측) → 두 기준 모두 오답, 정답 항목은 전부 FN"""
        g = label(NOROO)
        d, m, exact, ext = run(g, {})
        self.assertFalse(exact or ext)
        self.assertEqual((m["hcode_r"], m["cas_r"]), (0.0, 0.0))


class ScoreDocsFileTest(unittest.TestCase):
    """infer.py 출력 규약({doc_id}.json = 모델 원문, _log.jsonl = 시간·토큰)대로 읽어 분모를 지키는지"""

    def test_missing_skipped_and_broken_outputs_stay_in_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            pred = Path(tmp)
            (pred / f"{GSC}.json").write_text("```json\n" + json.dumps(label(GSC), ensure_ascii=False) + "\n```",
                                              encoding="utf-8")
            (pred / f"{NOROO}.json").write_text('{"product_name": {"value": "잘린 출', encoding="utf-8")
            # OLD: 출력 파일 없음, KR-KUMHO-002: 전처리 NOT_FOUND로 건너뜀
            log = [{"doc_id": GSC, "skipped": None, "gen_time_sec": 2.0, "input_tokens": 100, "output_tokens": 50},
                   {"doc_id": NOROO, "skipped": None, "gen_time_sec": 4.0, "input_tokens": 300, "output_tokens": 1024,
                    "hit_max_new_tokens": True},
                   {"doc_id": "KR-KUMHO-002", "skipped": "NOT_FOUND"}]
            (pred / "_log.jsonl").write_text("\n".join(json.dumps(r) for r in log) + "\n", encoding="utf-8")
            ids = [GSC, NOROO, OLD, "KR-KUMHO-002"]
            accs, _, details = score_docs(ids, {d: "ko" for d in ids}, FIX / "labels", pred, FIX / "text")
        m = dict(accs["ko"].rows())
        self.assertEqual(m["n_docs"], 4)
        self.assertEqual(m["n_missing_output"], 2)
        self.assertEqual(m["parse_rate"], 0.25)
        self.assertEqual(m["doc_exact_rate"], 0.25)
        self.assertEqual(m["gen_time_mean_s"], 3.0)
        self.assertEqual(m["n_hit_max_new_tokens"], 1)
        self.assertIn("parse_error", details[NOROO])

    def test_cli_self_check_on_fixtures(self):
        for split in ("train", "val"):
            r = subprocess.run(
                [sys.executable, "eval/score.py", "--split", split, "--self-check",
                 "--splits", "test/fixtures/splits.csv", "--label-dir", "test/fixtures/labels",
                 "--text-dir", "test/fixtures/text"],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_cli_refuses_test_without_gate(self):
        r = subprocess.run([sys.executable, "eval/score.py", "--condition", "base_zs", "--split", "test"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("거부", r.stderr)


if __name__ == "__main__":
    unittest.main()

"""
[양세윤] 짝 비교 회귀 테스트 — 입력은 test/fixtures/(옛 라벨, 코드 테스트 전용)

그룹 부트스트랩 구간, 문서별 맞음/틀림 변환, 10절 결론 분기, test 게이트(봉인 · 저장소 밖)를 본다.

  python3 test/test_paired.py -v
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "test"))  # 표준 라이브러리 test 패키지와 이름이 겹쳐 폴더를 직접 넣는다

from eval import paired, score, seal  # noqa: E402
from test_seal import make_test_set  # noqa: E402

FIX = ROOT / "test" / "fixtures"
DOCS = {"KR-NOROO-004": ("현행", "NOROO"), "KR-NOROO-005": ("구서식", "NOROO"), "KR-GSC-001": ("현행", "GSC"),
        "KR-KUMHO-002": ("현행", "KUMHO"), "KR-OCI-005": ("현행", "OCI")}


def label(doc_id):
    return json.loads((FIX / "labels" / f"{doc_id}.json").read_text(encoding="utf-8"))


class BootstrapTest(unittest.TestCase):
    def test_constant_diff_and_single_group(self):
        groups = {"a": "G1", "b": "G2", "c": "G3"}
        self.assertEqual(paired.bootstrap_ci({"a": 1, "b": 1, "c": 1}, groups, 200), (1.0, 1.0))
        self.assertEqual(paired.bootstrap_ci({"a": 1, "b": 0}, {"a": "G", "b": "G"}, 200), (None, None))

    def test_resamples_groups_not_documents(self):
        """한 그룹 안의 문서 여러 건은 함께 뽑힌다: 그룹 2개(1건 +1, 3건 0)면 평균은 {0, 1/4, 1/2, 1}뿐"""
        diffs = {"a": 1, "b": 0, "c": 0, "d": 0}
        groups = {"a": "G1", "b": "G2", "c": "G2", "d": "G2"}
        lo, hi = paired.bootstrap_ci(diffs, groups, 2000, seed=1)
        self.assertEqual((lo, hi), (0.0, 1.0))
        self.assertEqual(paired.bootstrap_ci(diffs, groups, 2000, seed=1), (lo, hi))  # seed 고정이면 같음

    def test_compare_counts(self):
        a = {"x": dict.fromkeys(paired.FIELDS, 1), "y": dict.fromkeys(paired.FIELDS, 0)}
        b = {"x": dict.fromkeys(paired.FIELDS, 0), "y": dict.fromkeys(paired.FIELDS, 0)}
        row = paired.compare(a, b, {"x": "G1", "y": "G2"}, ["x", "y"], 200)[0]
        self.assertEqual((row["win"], row["loss"], row["tie"], row["mean_diff"], row["n_groups"]), (1, 0, 1, 0.5, 2))


class ConclusionTest(unittest.TestCase):
    def test_branches(self):
        self.assertIn("이점이 확인됐다", paired.conclusion(0.1, 0.4, [], 0.4, 18))
        self.assertIn("우위 결론을 내지 않는다", paired.conclusion(0.1, 0.4, [("현행", "cas_f1")], 0.4, 18))
        self.assertIn("확인하지 못했다", paired.conclusion(-0.1, 0.3, [], 0.4, 18))
        self.assertIn("동등하다는 뜻이 아니다", paired.conclusion(0.0, 0.3, [], 0.4, 18))
        self.assertIn("낮다", paired.conclusion(-0.4, -0.1, [], 0.4, 18))
        self.assertIn("그룹 1개", paired.conclusion(None, None, [], None, 18))


class DocOutcomeTest(unittest.TestCase):
    def test_one_broken_field(self):
        gold = label("KR-GSC-001")
        pred = json.loads(json.dumps(gold))
        pred["product_name"]["value"] = "다른 제품"
        _, _, details = score.score_docs(["KR-GSC-001"], {"KR-GSC-001": "ko"}, FIX / "labels", self._pred(pred),
                                         FIX / "text")
        o = paired.doc_outcomes(details["KR-GSC-001"])
        self.assertEqual(o["product_name_acc"], 0)
        self.assertEqual(o["doc_exact_ext"], 0)
        self.assertEqual({k for k, v in o.items() if v == 0}, {"product_name_acc", "doc_exact", "doc_exact_ext"})

    def _pred(self, pred):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / "KR-GSC-001.json").write_text(json.dumps(pred, ensure_ascii=False), encoding="utf-8")
        return d


class TestSplitPairedTest(unittest.TestCase):
    """test 끝까지: 봉인 → 두 비교군 채점 → 짝 비교. 문서 ID는 화면에 안 나오고 문서별 승패는 저장소 밖에만."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.set_argv = make_test_set(self.tmp / "t", DOCS)
        self.args = dict(zip(self.set_argv[::2], self.set_argv[1::2]))
        self.manifest = self.tmp / "test_manifest.csv"
        self.manifest.write_text("kind,sha256\n", encoding="utf-8")
        exp = self.tmp / "experiment.json"
        exp.write_text('{"max_new_tokens": 1300, "adapter_sha256": "x", "prompt_version": "v1"}', encoding="utf-8")
        self.out = self.tmp / "out"
        for cond in ("qlora_final", "base_fs"):
            d = self.out / cond / "test"
            d.mkdir(parents=True)
            for doc_id in DOCS:
                pred = label(doc_id)
                if cond == "base_fs":  # base_fs는 모든 문서의 제품명을 틀림 → 주지표 차이 +1
                    pred["product_name"]["value"] = "다른 제품"
                (d / f"{doc_id}.json").write_text(json.dumps(pred, ensure_ascii=False), encoding="utf-8")
        self.scores = self.tmp / "scores.csv"
        self.paired_csv = self.tmp / "paired.csv"
        for target, attr, value in ((seal, "MANIFEST", self.manifest), (score, "EXPERIMENT_JSON", exp),
                                    (score, "SCORES_CSV", self.scores), (paired, "PAIRED_CSV", self.paired_csv)):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def quiet(self, fn, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(argv)
        return buf.getvalue()

    def paired_argv(self, *extra):
        return ["--a", "qlora_final", "--b", "base_fs", "--split", "test", "--allow-test", "--out-root", str(self.out),
                "--groups-csv", self.args["--groups-csv"], "--n-boot", "500", *extra]

    def test_end_to_end(self):
        self.quiet(seal.main, ["--write", *self.set_argv])
        for cond in ("qlora_final", "base_fs"):
            self.quiet(score.main, ["--condition", cond, "--split", "test", "--allow-test", "--out-root", str(self.out),
                                    "--label-dir", self.args["--label-dir"], "--text-dir", self.args["--text-dir"],
                                    "--subset-csv", self.args["--subset-csv"]])
        out = self.quiet(paired.main, self.paired_argv())
        for d in DOCS:
            self.assertNotIn(d, out)
        self.assertIn("문서 5건 · 그룹 4개", out)
        self.assertIn("이점이 확인됐다", out)
        rows = self.paired_csv.read_text(encoding="utf-8").splitlines()
        main = next(r for r in rows if ",all,doc_exact_ext," in r)
        self.assertIn("qlora_final,base_fs,test,latest,all,doc_exact_ext,5,4,5,0,0,1,1.0000,1.0000", main)
        self.assertTrue(any(",구서식,doc_exact_ext," in r for r in rows))  # 서식별 행도 따로
        per_doc = (self.out / "_paired_qlora_final_vs_base_fs_latest.jsonl").read_text(encoding="utf-8")
        self.assertEqual(len(per_doc.splitlines()), 5)
        # 최초 채점 상세로도 같은 결과
        out = self.quiet(paired.main, self.paired_argv("--first"))
        self.assertIn("이점이 확인됐다", out)

    def test_gates(self):
        cases = [
            ([a for a in self.paired_argv() if a != "--allow-test"], "--allow-test"),
            (["--a", "qlora_r1", *self.paired_argv()[2:]], "비교군"),
            ([a if a != self.args["--groups-csv"] else str(ROOT / "data" / "splits.csv") for a in self.paired_argv()],
             "저장소 밖"),
            (self.paired_argv(), "봉인"),  # 봉인 전(manifest 헤더만)
        ]
        for argv, msg in cases:
            with self.subTest(msg=msg), self.assertRaises(SystemExit) as cm:
                self.quiet(paired.main, argv)
            self.assertIn(msg, str(cm.exception))


if __name__ == "__main__":
    unittest.main()

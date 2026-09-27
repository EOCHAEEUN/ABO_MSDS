"""
평가 접근 게이트 — eval/infer.py(출력 생성) · eval/score.py(채점) · eval/paired.py(짝 비교)가 같은 규칙을 쓴다.

봉인 평가셋(test · test2)
  출력 생성: --allow-test · 봉인 대조 · 실험 정의 고정(eval/experiment.py check "generate") · 비교군 4개만 ·
             실행 설정이 고정된 조건 정의와 같을 것 · --overwrite / --limit 불가(조건당 1회, 전체 문서)
  채점·짝 비교: --allow-test · 봉인 대조 · 실험 정의 고정 · 비교군 4개만 · 추론 완료(모든 문서 출력 있음) ·
             실행 기록(_run.jsonl)이 고정된 조건 정의와 같을 것. 이 검사를 통과하기 전에는 정답을 읽지 않는다.
             고정된 출력의 재채점은 허용한다. 채점 파일이 고정 시점과 다르면 결과를 "채점 기준 변경" 이름으로
             따로 기록한다(최초 결과를 덮어쓰지 않음).

모든 split — 재개 대조
  출력 폴더마다 첫 실행 설정을 _run.jsonl(한 줄 JSON)에 남기고, 이어 돌릴 때 설정이 다르면 거부한다
  (같은 조건 이름으로 다른 어댑터를 지정해 한 폴더에 두 모델 출력이 섞이는 것을 막는다).
  CLAUDE.md 규약: 출력 폴더의 *.json은 검사기가 모두 보므로 기록 파일은 *.json이 아닌 이름으로 둔다.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import experiment  # noqa: E402
from eval.seal import verify as verify_seal  # noqa: E402

SEALED_SPLITS = ("test", "test2")
OUTPUT_ROOT = ROOT / "outputs"
RUN_FILE = "_run.jsonl"
PROMPT_FILE = "core/prompt.py"


def sealed(split):
    return split in SEALED_SPLITS


def rel(path):
    """어댑터 경로를 저장소 기준 상대 경로 문자열로(같은 폴더를 다르게 적어도 같게 비교)"""
    if not path:
        return None
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- 실행 기록
def run_record(condition, split, base_model, adapter, fewshot_ids, max_new_tokens):
    """출력 폴더 하나를 만든 설정(시간 제외). 조건 안에서 재개할 때 이 값이 같아야 한다."""
    return {
        "condition": condition,
        "split": split,
        "base_model": base_model,
        "model_revision": experiment.model_revision(base_model),
        "adapter": rel(adapter),
        "adapter_sha256": experiment.adapter_sha(rel(adapter)) if adapter else None,
        "fewshot_doc_ids": list(fewshot_ids),
        "fewshot_sha256": experiment.fewshot_state()[1] if fewshot_ids else None,
        "max_new_tokens": max_new_tokens,
        "prompt_sha256": experiment.sha(ROOT / PROMPT_FILE),
    }


def expected_run(exp, condition, split):
    """고정된 실험 정의대로라면 남았어야 할 실행 기록"""
    fz, c = exp["frozen"], exp["common"]
    cond, fc = exp["conditions"][condition], fz["conditions"][condition]
    return {
        "condition": condition,
        "split": split,
        "base_model": c["base_model"],
        "model_revision": fz["model_revision"],
        "adapter": cond["adapter"],
        "adapter_sha256": fc.get("adapter_sha256"),
        "fewshot_doc_ids": fc.get("fewshot_doc_ids", []),
        "fewshot_sha256": fc.get("fewshot_sha256"),
        "max_new_tokens": c["max_new_tokens"],
        "prompt_sha256": fz["generation_sha256"][PROMPT_FILE],
    }


def read_run(out_dir):
    p = Path(out_dir) / RUN_FILE
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8").splitlines()[0])


def differ(a, b):
    return sorted(k for k in set(a) | set(b) if k != "recorded_at" and a.get(k) != b.get(k))


def check_resume(out_dir, rec, doc_ids, overwrite, partial):
    """이어 돌리기 전: 앞선 실행과 설정이 같은지. 처음이면 기록을 남긴다."""
    out_dir = Path(out_dir)
    saved = read_run(out_dir)
    existing = [d for d in doc_ids if (out_dir / f"{d}.json").exists()]
    write = saved is None
    if saved is not None and (diff := differ(saved, rec)):
        if not overwrite:
            sys.exit(f"[거부] {out_dir.relative_to(ROOT)}의 앞선 실행과 설정이 다름 {diff} — 이어 돌리면 서로 다른 "
                     f"모델 출력이 한 폴더에 섞인다. 새로 만들려면 --overwrite(val·val_en 등, 전체 문서)")
        if partial:
            sys.exit("[거부] 설정이 바뀐 채 일부 문서만 다시 만들면 섞인다 — --limit 없이 --overwrite")
        write = True
    elif saved is None and existing and not overwrite:
        if sealed(rec["split"]):
            sys.exit(f"[거부] {out_dir.relative_to(ROOT)}에 실행 기록 없는 출력 {len(existing)}건 — 게이트 밖에서 만든 출력")
        print(f"[알림] 기존 출력 {len(existing)}건에 실행 기록이 없어 대조하지 못함. 지금 설정을 기록으로 남긴다")
    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / RUN_FILE).write_text(
            json.dumps({**rec, "recorded_at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n",
            encoding="utf-8")


# ---------------------------------------------------------------- 게이트
def _stop(what, problems):
    sys.exit(f"[거부] {what}:\n  " + "\n  ".join(problems))


def gate_generate(split, condition, rec, allow_test, overwrite, limit):
    """봉인 평가셋 출력 생성 전. 통과하지 못하면 종료한다."""
    if not sealed(split):
        return
    problems = []
    if not allow_test:
        problems.append(f"{split}는 모델 고정 전 사용 금지. 고정 후 최종 평가라면 --allow-test")
    if overwrite or limit:
        problems.append(f"{split}는 조건당 1회, 전체 문서만 돈다(--overwrite · --limit 불가)")
    exp = experiment.load()
    if condition not in exp["conditions"]:
        problems.append(f"{split}는 {tuple(exp['conditions'])}만 돌린다(조건 비교는 val로)")
    ok, p, _ = experiment.check("generate")
    problems += p
    if ok and condition in exp["conditions"] and (diff := differ(expected_run(exp, condition, split), rec)):
        problems.append(f"실행 설정이 고정된 {condition} 정의와 다름: {diff}")
    ok_seal, msg = verify_seal(split)
    if not ok_seal:
        problems.append(f"봉인 대조 실패: {msg}")
    if problems:
        _stop(f"{split} 출력 생성", problems)
    print(msg)


def scoring_files_sha(exp):
    files = [ROOT / p for p in exp["common"]["scoring_files"] if (ROOT / p).exists()]
    return experiment.sha_many(files)[:8]


def gate_score(split, conditions, allow_test, doc_ids):
    """봉인 평가셋 채점·짝 비교 전(정답을 읽기 전). → 결과 이름에 붙일 꼬리표('' 또는 채점 기준 변경 표시)"""
    if not sealed(split):
        return ""
    problems = []
    if not allow_test:
        problems.append(f"{split} 채점은 최종 평가 뒤에만. --allow-test")
    exp = experiment.load()
    if bad := [c for c in conditions if c not in exp["conditions"]]:
        problems.append(f"{bad}는 {split} 비교군이 아님({tuple(exp['conditions'])})")
    ok, p, changed = experiment.check("score")
    problems += p
    ok_seal, msg = verify_seal(split)
    if not ok_seal:
        problems.append(f"봉인 대조 실패: {msg}")
    for c in conditions:
        out_dir = OUTPUT_ROOT / c / split
        saved = read_run(out_dir)
        if saved is None:
            problems.append(f"{c}: 실행 기록 없음 — 추론 전이거나 게이트 밖에서 만든 출력")
        elif ok and c in exp["conditions"] and (diff := differ(expected_run(exp, c, split), saved)):
            problems.append(f"{c}: 출력이 고정된 정의와 다른 설정으로 만들어짐 {diff}")
        if missing := [d for d in doc_ids if not (out_dir / f"{d}.json").exists()]:
            problems.append(f"{c}: 추론이 끝나지 않음(출력 없는 문서 {len(missing)}/{len(doc_ids)}건)")
    if problems:
        _stop(f"{split} 채점", problems)
    print(msg)
    if changed:
        tag = f"[채점기변경-{scoring_files_sha(exp)}]"
        print(f"[알림] 채점 파일이 고정 시점과 다름 → 결과를 '{tag}' 이름으로 따로 기록한다(최초 결과와 구분해 보고)")
        return tag
    return ""

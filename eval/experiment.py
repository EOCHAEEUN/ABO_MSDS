"""
C안 최종 평가 실험 정의 고정 — eval/experiment.json

  python eval/experiment.py --show              # 정의와 고정 상태
  python eval/experiment.py --freeze            # 평가 전 1회. 해시·버전을 기록 → experiment.json 커밋
  python eval/experiment.py --check             # 지금 상태가 고정 시점과 같은지

네 조건에서 같아야 하는 것은 실험 정의다(실제 입력 프롬프트 전체가 아니다 — base_fs만 예시가 들어간다).
  공통 고정: Base 모델과 리비전, 생성 길이, 디코딩, 출력 생성에 영향을 주는 파일(전처리·프롬프트·추론·봉인·게이트),
             라이브러리 버전. 평가 문서·원문 해시는 봉인(eval/seal.py)이 고정한다.
  조건별 고정: few-shot 사용 여부와 예시(eval/fewshot.json + 예시 문서의 텍스트·정답 해시), 어댑터 유무와 해시.
  채점 파일(scoring_files)은 고정 시점 해시를 기준값으로 남긴다. 나중에 바뀌면 재채점은 허용하되
  eval/gate.py가 "채점 기준 변경" 결과로 따로 기록한다(최초 결과를 덮어쓰지 않음).

고정 조건: max_new_tokens와 모든 qlora 어댑터가 정해져 있고, 고정 대상 파일이 git에 커밋돼 있어야 한다
(미커밋 변경이 있으면 커밋 해시가 실제 코드를 가리키지 못한다).
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_JSON = ROOT / "eval" / "experiment.json"
FEWSHOT_JSON = ROOT / "eval" / "fewshot.json"
TEXT_DIR = ROOT / "data" / "text"
LABEL_DIR = ROOT / "data" / "labels"
ADAPTER_FILES = ("adapter_model.safetensors", "adapter_config.json")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha_many(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).name.encode())
        h.update(Path(p).read_bytes())
    return h.hexdigest()


def load():
    return json.loads(EXPERIMENT_JSON.read_text(encoding="utf-8"))


def definition_sha(exp):
    """common + conditions의 정규화 해시(고정 뒤 정의를 고쳤는지 본다)"""
    body = {"common": exp["common"], "conditions": exp["conditions"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------- 현재 상태 계산
def model_revision(base_model):
    """HF 캐시에 있는 Base 모델의 커밋 해시. 못 찾으면 None"""
    try:
        from huggingface_hub import try_to_load_from_cache

        p = try_to_load_from_cache(base_model, "config.json")
        return Path(p).parent.name if isinstance(p, str) else None
    except Exception:
        return None


def package_versions(names):
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for n in names:
        try:
            out[n] = version(n)
        except PackageNotFoundError:
            out[n] = None
    return out


def fewshot_state():
    """(예시 문서 ID, eval/fewshot.json + 예시 텍스트·정답을 묶은 해시)"""
    ids = json.loads(FEWSHOT_JSON.read_text(encoding="utf-8")).get("fewshot_doc_ids", [])
    files = [FEWSHOT_JSON] + [TEXT_DIR / f"{d}.txt" for d in ids] + [LABEL_DIR / f"{d}.json" for d in ids]
    missing = [str(p.relative_to(ROOT)) for p in files if not p.exists()]
    return ids, (None if missing else sha_many(files)), missing


def adapter_sha(adapter):
    d = ROOT / adapter
    files = [d / f for f in ADAPTER_FILES]
    if not all(p.exists() for p in files):
        return None
    return sha_many(files)


def condition_state(name, cond):
    """조건별 고정값 → (dict, 문제 목록)"""
    out, problems = {}, []
    if cond.get("fewshot"):
        ids, h, missing = fewshot_state()
        out.update(fewshot_doc_ids=ids, fewshot_sha256=h)
        problems += [f"{name}: few-shot 파일 없음 {missing}"] if missing else []
    if name.startswith("qlora"):
        if not cond.get("adapter"):
            problems.append(f"{name}: 어댑터가 정해지지 않음(eval/experiment.json conditions.{name}.adapter)")
        else:
            h = adapter_sha(cond["adapter"])
            out.update(adapter=cond["adapter"], adapter_sha256=h)
            if h is None:
                problems.append(f"{name}: 어댑터 파일 없음 ({cond['adapter']}/{'·'.join(ADAPTER_FILES)})")
    elif cond.get("adapter"):
        problems.append(f"{name}: Base 조건인데 어댑터가 있음")
    return out, problems


def file_hashes(paths):
    missing = [p for p in paths if not (ROOT / p).exists()]
    return {p: sha(ROOT / p) for p in paths if (ROOT / p).exists()}, missing


def git_unclean(paths):
    """커밋되지 않았거나 추적되지 않는 파일"""
    bad = []
    for p in paths:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", p], cwd=ROOT, capture_output=True).returncode == 0
        dirty = subprocess.run(["git", "status", "--porcelain", "--", p], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if not tracked or dirty:
            bad.append(p)
    return bad


def git_commit():
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() or None


def snapshot(exp):
    """지금 상태 → (고정 기록과 같은 모양의 dict, 문제 목록)"""
    c = exp["common"]
    problems = []
    gen, miss_g = file_hashes(c["generation_files"])
    score, miss_s = file_hashes(c["scoring_files"])
    problems += [f"파일 없음: {p}" for p in miss_g + miss_s]
    conds = {}
    for name, cond in exp["conditions"].items():
        conds[name], p = condition_state(name, cond)
        problems += p
    rev = model_revision(c["base_model"])
    if rev is None:
        problems.append(f"Base 모델 리비전을 찾지 못함({c['base_model']}, HF 캐시)")
    return {
        "definition_sha256": definition_sha(exp),
        "generation_sha256": gen,
        "scoring_sha256": score,
        "model_revision": rev,
        "python": platform.python_version(),
        "packages": package_versions(c["packages"]),
        "conditions": conds,
    }, problems


# ---------------------------------------------------------------- 고정 · 대조
def freeze(force=False):
    exp = load()
    if exp.get("frozen") and not force:
        sys.exit("이미 고정돼 있음. 다시 고정하려면 사유를 report/decisions.md에 적고 --force")
    c = exp["common"]
    problems = []
    if not isinstance(c.get("max_new_tokens"), int):
        problems.append("common.max_new_tokens가 정해지지 않음(새 라벨로 pipeline/length_stats.py 재측정 후 기입)")
    snap, p = snapshot(exp)
    problems += p
    if unclean := git_unclean(c["generation_files"] + c["scoring_files"] + ["eval/fewshot.json"]):
        problems.append(f"커밋되지 않은 고정 대상 파일: {unclean}")
    if problems:
        sys.exit("고정할 수 없음:\n  " + "\n  ".join(problems))
    exp["frozen"] = {"frozen_at": datetime.now().isoformat(timespec="seconds"), "git_commit": git_commit(), **snap}
    EXPERIMENT_JSON.write_text(json.dumps(exp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"실험 정의 고정 → {EXPERIMENT_JSON.relative_to(ROOT)}  (다음: 커밋. 커밋 전에는 --check가 실패한다)")


def check(scope="generate"):
    """(통과 여부, 문제 목록, 채점 파일이 바뀌었는지).

    scope="generate": 출력 생성 전 — 정의·생성 파일·모델 리비전·라이브러리·조건별 해시가 모두 고정 시점과 같아야 함
    scope="score"   : 채점 전 — 정의가 같아야 하고, 채점 파일은 커밋돼 있어야 함(바뀌었으면 세 번째 값 True)
    출력이 고정 시점 설정으로 만들어졌는지는 eval/gate.py가 실행 기록(_run.jsonl)으로 따로 본다.
    """
    exp = load()
    fz = exp.get("frozen")
    if not fz:
        return False, ["eval/experiment.json이 아직 고정되지 않음(python eval/experiment.py --freeze)"], False
    snap, problems = snapshot(exp)
    if snap["definition_sha256"] != fz["definition_sha256"]:
        problems.append("고정 뒤 common·conditions가 바뀜")
    if git_unclean(["eval/experiment.json"]):
        problems.append("eval/experiment.json이 커밋되지 않음(고정 직후 커밋할 것)")
    scoring_changed = snap["scoring_sha256"] != fz["scoring_sha256"]
    if scope == "generate":
        for key in ("generation_sha256", "model_revision", "python", "packages", "conditions"):
            if snap[key] != fz[key]:
                if isinstance(snap[key], dict) and isinstance(fz[key], dict):
                    changed = sorted(k for k in set(snap[key]) | set(fz[key]) if snap[key].get(k) != fz[key].get(k))
                    problems.append(f"고정 뒤 바뀜: {key} {changed}")
                else:
                    problems.append(f"고정 뒤 바뀜: {key} ({fz[key]} → {snap[key]})")
        if unclean := git_unclean(exp["common"]["generation_files"] + ["eval/fewshot.json"]):
            problems.append(f"커밋되지 않은 생성 파일: {unclean}")
    if unclean := git_unclean(exp["common"]["scoring_files"]):
        problems.append(f"커밋되지 않은 채점 파일: {unclean}")
    return not problems, problems, scoring_changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--freeze", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--show", action="store_true")
    ap.add_argument("--force", action="store_true", help="고정 다시 하기(비상용, 사유를 decisions.md에)")
    args = ap.parse_args()
    if args.freeze:
        freeze(args.force)
    elif args.check:
        ok, problems, changed = check("generate")
        print("OK  고정 시점과 같음" if ok else "FAIL\n  " + "\n  ".join(problems))
        if changed:
            print("[알림] 채점 파일이 고정 시점과 다름 — 재채점 결과는 '채점 기준 변경'으로 따로 기록된다")
        sys.exit(0 if ok else 1)
    else:
        exp = load()
        print(json.dumps({k: exp[k] for k in ("common", "conditions")}, ensure_ascii=False, indent=2))
        fz = exp.get("frozen")
        print(f"\n고정: {'아직' if not fz else fz['frozen_at'] + ' (commit ' + str(fz['git_commit'])[:8] + ')'}")


if __name__ == "__main__":
    main()

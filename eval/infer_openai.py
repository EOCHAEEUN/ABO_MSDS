"""
외부 API 비교군 — OpenAI 모델(gpt-5-mini 등)로 val을 추출해 r1 · Base와 같은 채점기로 비교한다.

본 비교군(base_zs · base_fs · qlora_*)이 아니다. 런타임 · 토크나이저 · 디코딩이 달라 report/scores.csv ·
final_table.md에 넣지 않고 따로 둔다. 입력(1~3항 텍스트) · 프롬프트(core/prompt.py, 기본 v1) · few-shot 예시
(eval/fewshot.json, train 2건)는 infer.py와 같게 쓴다. test는 돌리지 않는다(봉인 — 외부 전송 금지).

키: 저장소 루트 .env(git 제외)의 OPENAI_API_KEY. 모델 기본값은 .env의 OPENAI_MODEL, 없으면 gpt-5-mini.

출력 (infer.py와 같은 형식이라 eval/score.py가 그대로 채점)
  outputs/api/{모델}_{zs|fs}/val/{doc_id}.json   모델 응답 원문(파싱 실패도 그대로)
  outputs/api/{모델}_{zs|fs}/val/_log.jsonl      문서별 시간 · 토큰(입력 · 출력 · 추론) · finish_reason · 응답 모델 이름
  outputs/api/{모델}_{zs|fs}/val/_run.jsonl      첫 실행 설정(모델 · 추론 강도 · 생성 한도 · few-shot · 프롬프트 · 입력 해시)
  - 이미 출력이 있으면 건너뛴다(--overwrite로 다시). API 오류는 출력 없이 _log.jsonl에 skipped로 남는다(채점에선 실패)
  - 토큰 수는 OpenAI 토크나이저 기준이라 Qwen 토큰 수와 직접 비교하지 않는다

  python3 eval/infer_openai.py --mode zs --text-dir runs/deploy/text_r1   # r1 val과 같은 입력
  python3 eval/infer_openai.py --mode fs --text-dir runs/deploy/text_r1
  python3 eval/score.py --condition gpt-5-mini_zs --split val --out-root outputs/api --scores-csv report/api/scores_openai.csv
  python3 eval/compare_api.py
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt import DEFAULT_PROMPT, PROMPTS, build_messages, prompt_sha256  # noqa: E402
from eval.infer import (  # noqa: E402
    LABEL_DIR,
    SPLITS_CSV,
    TEXT_DIR,
    append_log,
    check_resume,
    inputs_digest,
    load_fewshot,
    now,
    read_cut_status,
    read_splits,
)

API_URL = "https://api.openai.com/v1/chat/completions"
OUT_ROOT = ROOT / "outputs" / "api"
ENV_FILE = ROOT / ".env"
DEFAULT_MODEL = "gpt-5-mini"
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")  # reasoning_effort를 받고 temperature를 받지 않는 모델


def read_env(path=ENV_FILE):
    """.env(KEY=VALUE, # 주석) → dict. 환경 변수가 이미 있으면 그쪽이 우선."""
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return {**env, **{k: os.environ[k] for k in ("OPENAI_API_KEY", "OPENAI_MODEL") if os.environ.get(k)}}


def is_reasoning(model):
    return model.startswith(REASONING_PREFIXES)


def request_body(model, messages, args):
    body = {"model": model, "messages": messages, "max_completion_tokens": args.max_completion_tokens}
    if is_reasoning(model):
        body["reasoning_effort"] = args.reasoning_effort
    else:
        body["temperature"] = 0  # 로컬 비교군의 greedy에 맞춤(완전한 결정성은 보장되지 않음)
    return body


def call(client, key, body, retries=4):
    """→ (응답 JSON, 걸린 초). 429 · 5xx · 네트워크 오류는 지수 대기 후 다시. 그 밖의 오류는 바로 예외."""
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            r = client.post(API_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}: {e}"
        else:
            if r.status_code == 200:
                return r.json(), time.time() - t0
            err = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code != 429 and r.status_code < 500:
                raise RuntimeError(err)
        if attempt == retries:
            raise RuntimeError(err)
        wait = 2 ** attempt * 5
        print(f"    재시도 {attempt + 1}/{retries} ({wait}s 뒤): {err[:120]}")
        time.sleep(wait)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help=f"OpenAI 모델(기본 .env의 OPENAI_MODEL, 없으면 {DEFAULT_MODEL})")
    ap.add_argument("--mode", choices=("zs", "fs"), required=True, help="zs: 예시 없음, fs: eval/fewshot.json의 train 2건")
    ap.add_argument("--split", choices=("val",), default="val", help="val만(test는 외부로 보내지 않는다)")
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default=DEFAULT_PROMPT)
    ap.add_argument("--reasoning-effort", choices=("minimal", "low", "medium", "high"), default="medium",
                    help="gpt-5 · o 계열만. 기본 medium(API 기본값과 같음)")
    ap.add_argument("--max-completion-tokens", type=int, default=16000,
                    help="gpt-5 계열은 추론 토큰 포함 한도. 도달하면 hit_max_new_tokens로 기록")
    ap.add_argument("--text-dir", default=TEXT_DIR,
                    help="1~3항 텍스트 폴더. 본 비교군과 비교하려면 그 _run.jsonl의 inputs_sha256과 같은 입력을 준다"
                         "(r1 val = runs/deploy/text_r1, data/text는 268e4e4로 바뀜)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--out-root", default=OUT_ROOT)
    args = ap.parse_args(argv)

    env = read_env()
    key = env.get("OPENAI_API_KEY")
    if not key:
        sys.exit(f"OPENAI_API_KEY가 없다({ENV_FILE} 또는 환경 변수)")
    model = args.model or env.get("OPENAI_MODEL") or DEFAULT_MODEL
    condition = f"{model}_{args.mode}"

    splits = read_splits(SPLITS_CSV)
    all_ids = sorted(d for d, r in splits.items() if r["split"] == args.split)
    doc_ids = all_ids[: args.limit] if args.limit else all_ids
    text_dir = Path(args.text_dir)
    cut = read_cut_status(text_dir)
    fewshot_ids, fewshot = load_fewshot(splits, TEXT_DIR, LABEL_DIR) if args.mode == "fs" else ([], [])
    out_dir = Path(args.out_root) / condition / args.split
    missing = [d for d in doc_ids if cut.get(d) != "NOT_FOUND" and not (text_dir / f"{d}.txt").exists()]
    if missing:
        sys.exit(f"전처리 텍스트 없음: {missing}")

    run = {
        "condition": condition, "split": args.split, "provider": "openai", "model": model,
        "reasoning_effort": args.reasoning_effort if is_reasoning(model) else None,
        "temperature": None if is_reasoning(model) else 0,
        "max_new_tokens": args.max_completion_tokens,
        "fewshot_doc_ids": fewshot_ids,
        "prompt_version": args.prompt, "prompt_text_sha256": prompt_sha256(args.prompt),
        "text_dir": str(text_dir), "n_docs": len(all_ids), "inputs_sha256": inputs_digest(all_ids, text_dir, cut),
    }
    check_resume(out_dir, run)
    todo = [d for d in doc_ids if args.overwrite or not (out_dir / f"{d}.json").exists()]
    if not todo:
        print(f"할 일 없음: {out_dir}에 {len(doc_ids)}건 모두 있음(다시 돌리려면 --overwrite)")
        return
    print(f"[{condition} / {args.split}] {len(todo)}/{len(doc_ids)}건 → {out_dir}")

    n_fail = 0
    with httpx.Client(timeout=args.timeout) as client:
        for n, doc_id in enumerate(todo, 1):
            rec = {"doc_id": doc_id, "skipped": None, "gen_time_sec": None, "input_tokens": None,
                   "output_tokens": None, "reasoning_tokens": None, "hit_max_new_tokens": False,
                   "finish_reason": None, "response_model": None, "created_at": now()}
            if cut.get(doc_id) == "NOT_FOUND":
                rec["skipped"] = "NOT_FOUND"
                (out_dir / f"{doc_id}.json").unlink(missing_ok=True)
                print(f"  ({n}/{len(todo)}) {doc_id}  건너뜀: _cut_log NOT_FOUND")
                append_log(out_dir, rec)
                continue
            text = (text_dir / f"{doc_id}.txt").read_text(encoding="utf-8")
            body = request_body(model, build_messages(text, fewshot, prompt=args.prompt), args)
            try:
                resp, sec = call(client, key, body)
            except RuntimeError as e:
                n_fail += 1
                rec["skipped"] = f"API_ERROR: {str(e)[:200]}"
                (out_dir / f"{doc_id}.json").unlink(missing_ok=True)
                print(f"  ({n}/{len(todo)}) {doc_id}  실패: {str(e)[:160]}")
                append_log(out_dir, rec)
                if "HTTP 401" in str(e):
                    sys.exit("API 키가 거부됐다(401). .env의 OPENAI_API_KEY를 확인할 것")
                continue
            choice, usage = resp["choices"][0], resp.get("usage") or {}
            raw = choice["message"].get("content") or ""
            rec.update(gen_time_sec=round(sec, 3), input_tokens=usage.get("prompt_tokens"),
                       output_tokens=usage.get("completion_tokens"),
                       reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                       finish_reason=choice.get("finish_reason"), hit_max_new_tokens=choice.get("finish_reason") == "length",
                       response_model=resp.get("model"))
            (out_dir / f"{doc_id}.json").write_text(raw, encoding="utf-8")
            flag = "  ← 생성 한도 도달" if rec["hit_max_new_tokens"] else ""
            print(f"  ({n}/{len(todo)}) {doc_id}  {sec:.1f}s  in={rec['input_tokens']} out={rec['output_tokens']}"
                  f" (추론 {rec['reasoning_tokens']}){flag}")
            append_log(out_dir, rec)

    print(f"완료 → {out_dir}" + (f"  (API 실패 {n_fail}건 — 다시 실행하면 빠진 문서만 채움)" if n_fail else ""))
    print(f"다음: python3 eval/score.py --condition {condition} --split {args.split} --out-root {args.out_root} "
          "--scores-csv report/api/scores_openai.csv")


if __name__ == "__main__":
    main()

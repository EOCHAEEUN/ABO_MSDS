# 저장 위치: <프로젝트 루트>/scripts/labels_to_jsonl.py
"""data/labels/*.json (LLM 라벨, 동결 스키마) → compare.py 가 읽는 JSONL.

값이 없을 때의 규칙은 data/README.md 를 따른다.
  · 리스트가 비었으면 list_status(자료없음/해당없음)를 값 하나로 넣는다.
    골든 시트가 "해당없음"을 한 행으로 적기 때문에 이렇게 맞춘다.
  · 신호어 value 가 null 이면 source_status 를 쓴다.
  · 성분의 cas/ke 가 null 이면 "자료없음" (README: 비었으면 null).
  · GHS분류는 "hazard_class : category" 로 잇는다 (골든 시트 표기).
  · 유해위험문구는 "H코드 문구" 로 잇는다. code 가 null 이면 문구만.

사용법
  python scripts/labels_to_jsonl.py data/labels runs/llm_labels.jsonl
"""
import glob, json, os, sys


def convert(d, doc_id):
    status = d.get("list_status", {})

    def listed(key, items):
        return items or ([status[key]] if status.get(key) in ("자료없음", "해당없음") else [])

    sw = d.get("signal_word") or {}
    hazard = [" ".join(x for x in (h.get("code"), h.get("text")) if x)
              for h in d.get("hazard_statements", [])]
    ghs = [g if isinstance(g, str) else
           " : ".join(x for x in (g.get("hazard_class"), g.get("category")) if x)
           for g in d.get("ghs_classification", [])]
    return {
        "doc_id": doc_id,
        "제품명": (d.get("product_name") or {}).get("value") or "",
        "신호어": sw.get("value") or sw.get("source_status") or "",
        "GHS분류": listed("ghs_classification", ghs),
        "유해위험문구": listed("hazard_statements", hazard),
        "성분": [{"성분명": c.get("chemical_name") or "",
                "CAS": c.get("cas_number") or "자료없음",
                "KE": c.get("ke_number") or "자료없음",
                "함유량": c.get("content") or ""}
               for c in d.get("ingredients", [])],
    }


def main(src, dst):
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    paths = sorted(glob.glob(os.path.join(src, "*.json")))
    with open(dst, "w", encoding="utf-8") as f:
        for p in paths:
            with open(p, encoding="utf-8") as g:
                d = json.load(g)
            doc = os.path.splitext(os.path.basename(p))[0]
            f.write(json.dumps(convert(d, doc), ensure_ascii=False) + "\n")
    print(f"{len(paths)}건 → {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

# 저장 위치: <프로젝트 루트>/scripts/load_labels.py
"""라벨 뭉치를 공통 형태로 읽어들인다.

받는 것
  · 시트 CSV 두 장 (라벨링 시트 + 성분표 시트)  — 사람이 매긴 라벨
  · JSONL 한 장                                — 모델 출력

돌려주는 것: {doc_id: record} 의 dict
  record = {doc_id, product_name, signal_word, ghs[], hazard[], components[]}
"""
import csv, json, re, sys

FIELD_ALIAS = {
    "제품명": "product_name", "productname": "product_name", "product_name": "product_name",
    "신호어": "signal_word", "signalword": "signal_word", "signal_word": "signal_word",
    "ghs분류": "ghs", "ghs": "ghs", "분류": "ghs",
    "ghs_classification": "ghs", "ghs_classifications": "ghs", "classification": "ghs",
    "유해위험문구": "hazard", "hazard": "hazard", "hazard_statement": "hazard",
    "hazard_statements": "hazard", "유해·위험문구": "hazard",
}
COMP_ALIAS = {"name": ["성분명", "name", "chemical_name", "component_name"],
              "cas": ["cas번호", "cas", "cas_no", "cas_number"],
              "ke": ["ke번호", "ke", "ke_number", "식별번호"],
              "amount": ["함유량", "amount", "content", "concentration"]}


def _key(s):
    return re.sub(r"[\s_·ㆍ]", "", (s or "")).lower()


def _blank(rec):
    return {"doc_id": rec, "product_name": None, "signal_word": None,
            "ghs": [], "hazard": [], "components": []}


def _pick(d, names):
    for n in names:
        for k, v in d.items():
            if _key(k) == _key(n):
                return (v or "").strip()
    return ""


def from_sheets(main_csv, comp_csv=None):
    out = {}
    with open(main_csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            doc = _pick(row, ["문서ID", "doc_id"])
            fld = FIELD_ALIAS.get(_key(_pick(row, ["필드", "field"])))
            val = _pick(row, ["값", "value"])
            if not doc or not fld or not val:
                continue
            r = out.setdefault(doc, _blank(doc))
            if fld in ("ghs", "hazard"):
                r[fld].append(val)
            else:
                r[fld] = val
    if comp_csv:
        with open(comp_csv, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                doc = _pick(row, ["문서ID", "doc_id"])
                name = _pick(row, COMP_ALIAS["name"])
                if not doc or not name:
                    continue
                out.setdefault(doc, _blank(doc))["components"].append({
                    "name": name,
                    "cas": _pick(row, COMP_ALIAS["cas"]),
                    "ke": _pick(row, COMP_ALIAS["ke"]),
                    "amount": _pick(row, COMP_ALIAS["amount"])})
    return out


def from_jsonl(path):
    """모델 출력. 키 이름이 흔들려도 최대한 받아준다.
    JSON 파싱에 실패한 줄은 doc_id 를 알 수 없으므로 순번으로 기록하고 표시해 둔다."""
    out, bad = {}, []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad.append(i)
                continue
            doc = str(_pick(obj, ["문서id", "doc_id", "id", "document_id"]) or f"LINE-{i}")
            r = _blank(doc)
            r["product_name"] = _pick(obj, ["제품명", "product_name"]) or None
            r["signal_word"] = _pick(obj, ["신호어", "signal_word"]) or None
            for canon, names in (("ghs", ["ghs분류", "ghs", "분류", "ghs_classification",
                                          "ghs_classifications", "classification"]),
                                 ("hazard", ["유해위험문구", "hazard", "hazard_statement",
                                             "hazard_statements"])):
                for n in names:
                    for k, v in obj.items():
                        if _key(k) == _key(n) and isinstance(v, list):
                            r[canon] = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
                                        for x in v]
                            break
                    if r[canon]:
                        break
            for k, v in obj.items():
                if _key(k) in {"성분", "components", "component", "구성성분"} and isinstance(v, list):
                    for c in v:
                        if isinstance(c, dict):
                            r["components"].append({a: _pick(c, ns) for a, ns in COMP_ALIAS.items()})
                    break
            out[doc] = r
    return out, bad


def load(spec):
    """spec: 'a.csv,b.csv' 또는 'out.jsonl'"""
    parts = [p for p in spec.split(",") if p]
    if parts[0].lower().endswith(".jsonl"):
        recs, bad = from_jsonl(parts[0])
        if bad:
            print(f"  [경고] JSON 파싱 실패 {len(bad)}줄: {bad[:10]}", file=sys.stderr)
        return recs
    return from_sheets(parts[0], parts[1] if len(parts) > 1 else None)

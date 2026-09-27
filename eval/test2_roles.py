"""test2 문서 역할 목록 — 주 분석 대상을 사전에 고정한다(docs/plan_c.md 6절, report/decisions.md "test2 역할 목록").

eval/test2_roles.csv (doc_id, role, note). splits.csv의 test2 문서마다 한 줄.
  main     주 분석 대상: 국문 현행 · 수입품 국문판이고 독립 주평가 적격성이 확인된 문서. C 결론은 이것만 본다
  oldform  구서식. 따로 보고한다
  exposed  개발 세션에 정답 등이 유입된 문서. 노출 이력이 있는 보조평가로 따로 보고한다(note에 경로)
  pending  영향 점검 대기. 실험 고정 전에 main · exposed 중 하나로 정한다(note에 점검할 경로)

채점(eval/score.py) · 짝 비교(eval/paired.py)는 이 목록 하나로 test2를 나누고, 목록의 모든 문서를 분모에 둔다
(출력이 없거나 파싱에 실패한 문서도 실패로 센다). 역할은 정답 · 모델 결과를 보고 바꾸지 않는다.

분석 대상 목록(analysis_set: doc_id · 역할 · 언어 · 서식 · split_group)은 실험 고정 때 experiment.json에 그대로
기록된다. 고정 뒤 목록이 바뀌면 출력 생성과 채점을 모두 거부한다("채점 기준 변경" 꼬리표로 허용하지 않는다 —
평가 대상 변경은 채점 방식 변경과 다르다). 대상을 바꾼 분석이 필요하면 결정 기록 후 별도 사후 분석으로 한다.
한 문서에 역할 줄은 하나다. 중복 doc_id는 역할이 같아도 읽는 단계에서 거부한다.
"""
import collections
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES_CSV = ROOT / "eval" / "test2_roles.csv"
SPLITS_CSV = ROOT / "data" / "splits.csv"
ROLES = {"main": "주 분석 대상", "oldform": "구서식(따로 보고)", "exposed": "노출 보조평가", "pending": "영향 점검 대기"}
REPORT_ORDER = ("main", "oldform", "exposed")      # 채점 · 짝 비교에 나오는 순서. pending은 고정 전에 없어야 함
MAIN_FORMS = ("현행", "수입품 국문판")


def read_roles(path=None):
    """{doc_id: {"role", "note"}}. 파일이 없으면 빈 dict. 열 누락 · 빈 doc_id · 중복 doc_id는 ValueError"""
    path = Path(path or ROLES_CSV)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if missing := [c for c in ("doc_id", "role") if c not in (reader.fieldnames or [])]:
            raise ValueError(f"{path.name}: 열이 없음 {missing}")
        rows = [((r["doc_id"] or "").strip(), (r["role"] or "").strip(), (r.get("note") or "").strip()) for r in reader]
    if blank := [i for i, (d, _, _) in enumerate(rows, 2) if not d]:
        raise ValueError(f"{path.name}: doc_id가 빈 줄 {blank}")
    if dup := sorted(d for d, n in collections.Counter(d for d, _, _ in rows).items() if n > 1):
        raise ValueError(f"{path.name}: doc_id 중복 {dup} — 한 문서에 역할 한 줄(역할이 같아도 거부)")
    return {d: {"role": role, "note": note} for d, role, note in rows}


def problems(split_rows, roles, final=False):
    """splits.csv 행 목록과 역할 목록 → (오류, 경고). final이면 점검 대기도 오류"""
    err, warn = [], []
    t2 = {r["doc_id"]: r for r in split_rows if r["split"] == "test2"}
    ids = collections.Counter(r["doc_id"] for r in split_rows)
    err += [f"test2 {d}: 역할이 없음(eval/test2_roles.csv)" for d in sorted(t2) if d not in roles]
    err += [f"역할 목록의 {d}는 splits.csv의 test2가 아님" for d in sorted(roles) if d not in t2]
    err += [f"splits.csv doc_id 중복: {d}" for d, n in ids.items() if n > 1 and d in t2]
    for d in sorted(set(t2) & set(roles)):
        r, role, note = t2[d], roles[d]["role"], roles[d]["note"]
        if role not in ROLES:
            err.append(f"test2 {d}: 알 수 없는 역할 '{role}'({'/'.join(ROLES)})")
        elif role == "main" and (r["form"] not in MAIN_FORMS or r["lang"] != "ko"):
            err.append(f"test2 {d}: 주 분석 대상은 국문 {'·'.join(MAIN_FORMS)}만(지금 {r['lang']} {r['form']})")
        elif role == "oldform" and r["form"] != "구서식":
            err.append(f"test2 {d}: oldform인데 서식이 '{r['form']}'")
        elif role in ("exposed", "pending") and not note:
            err.append(f"test2 {d}: {role}는 note에 경로를 적어야 함")
        if final and role == "pending":
            err.append(f"test2 {d}: 영향 점검 대기가 남음 — 실험 고정 전에 main · exposed 중 하나로 정할 것")
    affected = {t2[d]["split_group"] for d in t2 if roles.get(d, {}).get("role") in ("exposed", "pending")}
    for d in sorted(t2):
        if roles.get(d, {}).get("role") == "main" and t2[d]["split_group"] in affected:
            warn.append(f"주 분석 대상 {d}의 split_group {t2[d]['split_group']}에 노출 · 점검 대기 문서가 있음 "
                        "— 영향받은 그룹과 분리 권고")
    return err, warn


def read_split_rows(path=None):
    with open(path or SPLITS_CSV, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def check_files(splits_path=None, roles_path=None, final=True):
    """실험 고정 · 채점 전 확인: (오류, 경고)"""
    try:
        roles = read_roles(roles_path)
    except ValueError as e:
        return [str(e)], []
    return problems(read_split_rows(splits_path), roles, final)


def analysis_set(split_rows, roles):
    """고정할 분석 대상 목록: test2 문서마다 [doc_id, 역할, 언어, 서식, split_group], doc_id 순"""
    return [[r["doc_id"], roles.get(r["doc_id"], {}).get("role", ""), r["lang"], r["form"], r["split_group"]]
            for r in sorted((r for r in split_rows if r["split"] == "test2"), key=lambda r: r["doc_id"])]


def current_analysis_set(splits_path=None, roles_path=None):
    """지금 파일로 만든 분석 대상 목록 → (목록, 문제)"""
    try:
        roles = read_roles(roles_path)
    except ValueError as e:
        return [], [str(e)]
    return analysis_set(read_split_rows(splits_path), roles), []


def subset_ids(doc_ids, roles):
    """test2 문서 목록 → [(역할, 문서 목록)] REPORT_ORDER 순. 목록에 없는 역할의 문서가 있으면 ValueError"""
    by = collections.defaultdict(list)
    for d in doc_ids:
        role = roles.get(d, {}).get("role")
        if role not in REPORT_ORDER:
            raise ValueError(f"test2 {d}: 채점할 수 있는 역할이 아님({role}) — eval/test2_roles.csv 확인")
        by[role].append(d)
    return [(role, sorted(by[role])) for role in REPORT_ORDER if by[role]]

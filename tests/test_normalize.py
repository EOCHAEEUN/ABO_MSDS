# 저장 위치: <프로젝트 루트>/tests/test_normalize.py
"""실제 문서에서 나온 표기 변이만 모았다. 추측으로 만든 케이스는 없다."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.compare_norm import (norm_loose, norm_amount, norm_cas, norm_ke,
                            blank_kind, cas_checkdigit, UNDECIDED)

SAME = [  # 같은 값으로 봐야 하는 쌍
    ("H225 - 고인화성 액체 및 증기", "H225 고인화성 액체 및 증기"),   # 피셔 ↔ 노루
    ("인화성 액체 구분 2", "인화성 액체 : 구분2"),                   # 피셔 ↔ 레미픽스
    ("특정표적장기 독성 (1회 노출) : 구분3", "특정표적장기독성(1회 노출):구분3"),
    ("석회암 ; 석회석", "석회암 : 석회석"),
    ("- 급성 독성(흡입: 분진/미스트) : 구분4", "급성 독성(흡입: 분진/미스트) : 구분4"),
    ("○ 피부 과민성 : 구분1", "피부 과민성 : 구분1"),
]
DIFF = [  # 붙이면 안 되는 쌍 — 사람이 판정할 몫이다
    ("심한 눈 손상성/눈 자극성 : 구분2", "심한 눈 손상 또는 자극성물질 2A"),
    ("자료없음", "해당없음"),          # 고시 제11조제7항: 뜻이 다르다
    ("구분1", "구분2"),
]
AMOUNT = [("50 이상 ~ 60 % 미만", "50~60"), ("99 - 100", "99~100"),
          ("28∼38", "28~38"), ("78.5 ~ 81.5", "78.5~81.5"),
          ("1 이상 ~10 % 미만", "1~10"), ("0.1∼4", "0.1~4")]
CAS = [("9003-55-8 / KE-13258", "9003-55-8"), ("67-64-1", "67-64-1"), ("-", UNDECIDED)]
KE  = [("(KE-32301)", "KE-32301"), ("KE-04179", "KE-04179"), ("자료 없음", "자료없음")]
BLANK = [("자료 없음.", "자료없음"), ("해당없음", "해당없음"), ("N/A", "해당없음"),
         ("-", UNDECIDED), ("", UNDECIDED), ("경고", None)]
CHECK = [("67-64-1", True), ("1317-65-3", True), ("317-65-3", False),
         ("7732-18-5", True), ("자료없음", None)]


def run():
    bad = []
    for a, b in SAME:
        if norm_loose(a) != norm_loose(b):
            bad.append(f"SAME 실패: {a!r} vs {b!r} → {norm_loose(a)!r} / {norm_loose(b)!r}")
    for a, b in DIFF:
        if norm_loose(a) == norm_loose(b):
            bad.append(f"DIFF 실패(붙어버림): {a!r} vs {b!r} → {norm_loose(a)!r}")
    for fn, cases, nm in ((norm_amount, AMOUNT, "amount"), (norm_cas, CAS, "cas"),
                          (norm_ke, KE, "ke"), (blank_kind, BLANK, "blank")):
        for src, want in cases:
            got = fn(src)
            if got != want:
                bad.append(f"{nm} 실패: {src!r} → {got!r} (기대 {want!r})")
    for cas, want in CHECK:
        if cas_checkdigit(cas) is not want:
            bad.append(f"checkdigit 실패: {cas!r} → {cas_checkdigit(cas)!r} (기대 {want!r})")

    total = len(SAME) + len(DIFF) + len(AMOUNT) + len(CAS) + len(KE) + len(BLANK) + len(CHECK)
    if bad:
        print(f"FAIL  {len(bad)}/{total}")
        for b in bad:
            print("  -", b)
        return 1
    print(f"PASS  {total}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(run())

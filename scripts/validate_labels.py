"""정답 라벨(또는 모델 출력) 폴더를 스키마로 검사한다.

사용법 (저장소 루트에서):
    python scripts/validate_labels.py data/labels
    python scripts/validate_labels.py eval/test
    python scripts/validate_labels.py outputs/qlora_r1/val
"""
import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from schema import MSDSLabel  # noqa: E402


def main(folder: str) -> int:
    files = sorted(Path(folder).glob("*.json"))
    bad = parse_fail = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            parse_fail += 1
            print(f"[PARSE] {f.name}: {e}")
            continue
        try:
            MSDSLabel.model_validate(data)
        except ValidationError as e:
            bad += 1
            print(f"[SCHEMA] {f.name}")
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                print(f"    {loc}: {err['msg']}")
    n = len(files)
    ok = n - bad - parse_fail
    print(f"\n파일 {n}개 | JSON 파싱 성공 {n - parse_fail} | 스키마 통과 {ok} | 스키마 실패 {bad}")
    return 0 if (bad == 0 and parse_fail == 0) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/labels"))

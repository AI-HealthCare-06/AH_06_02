"""마크다운 본문에 이스케이프하지 않은 물결표가 있으면 막는다.

GitHub 은 같은 문단의 물결표 두 개 사이를 취소선으로 그린다. "1~7 ... 2~3" 처럼 범위를 적으면
그 사이 글자가 지워진 것처럼 보이므로 본문에서는 항상 \\~ 로 쓴다. 코드(`...`, ``` 블록) 안은 그대로 둔다.
pre-commit 이 바뀐 .md 파일 경로를 넘겨 부른다.
"""

import re
import sys
from pathlib import Path

INLINE_CODE = re.compile(r"`[^`]*`")
BARE_TILDE = re.compile(r"(?<!\\)~")


def unescaped_tilde_lines(text: str) -> list[int]:
    found: list[int] = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and BARE_TILDE.search(INLINE_CODE.sub("", line)):
            found.append(number)
    return found


def main(paths: list[str]) -> int:
    failed = False
    for path in paths:
        for number in unescaped_tilde_lines(Path(path).read_text(encoding="utf-8")):
            print(f"{path}:{number}: 물결표는 \\~ 로 쓰거나 `코드` 안에 넣어 주세요")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

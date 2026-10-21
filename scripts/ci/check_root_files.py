"""저장소 루트에 허용 목록 밖의 파일·폴더가 올라오지 못하게 막는다.

루트에는 도구가 그 자리에서만 찾는 파일과 최상위 폴더만 둔다. 문서는 docs/, 스크립트는 scripts/,
인프라 설정은 infra/ 로 보낸다. pre-commit 과 GitHub Actions 가 둘 다 이 검사를 부른다.
"""

import subprocess
import sys
from collections.abc import Iterable

#: 폴더는 이름 끝에 / 를 붙인다. 늘릴 때는 그 도구가 정말 루트에서만 찾는지 먼저 확인한다
ALLOWED_ROOT_ENTRIES = frozenset(
    {
        ".claude/",  # Claude Code 설정
        ".github/",  # PR 템플릿·Actions
        ".dockerignore",  # 이미지 빌드 기준 폴더가 루트
        ".gitignore",
        ".pre-commit-config.yaml",
        "AGENTS.md",  # 에이전트가 루트에서 자동으로 읽는다
        "README.md",  # GitHub 첫 화면
        "ai_worker/",
        "app/",
        "data/",
        "docker-compose.yml",  # docker compose 가 루트에서 찾는다
        "docs/",
        "envs/",
        "frontend/",
        "infra/",
        "pyproject.toml",  # uv·ruff·pytest 설정
        "scripts/",
        "tests/",
        "uv.lock",
    }
)


def unexpected_root_entries(paths: Iterable[str]) -> list[str]:
    entries = {path.split("/", 1)[0] + ("/" if "/" in path else "") for path in paths}
    return sorted(entries - ALLOWED_ROOT_ENTRIES)


def tracked_paths() -> list[str]:
    # 스테이징한 파일까지 포함하므로 커밋 직전 pre-commit 에서도 새 파일을 잡는다
    output = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True, text=True).stdout
    return [path for path in output.split("\0") if path]


def main() -> int:
    unexpected = unexpected_root_entries(tracked_paths())
    if not unexpected:
        return 0
    print("저장소 루트에 둘 수 없는 항목이 있습니다:")
    for entry in unexpected:
        print(f"  {entry}")
    print("문서는 docs/, 스크립트는 scripts/, 인프라 설정은 infra/ 로 옮겨 주세요.")
    print("루트에만 둘 수 있는 도구 파일이면 scripts/ci/check_root_files.py 의 허용 목록에 이유와 함께 더합니다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

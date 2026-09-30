"""레벨과 경험치.

레벨별 필요 경험치는 테이블로 만들지 않고 코드 상수로 둔다.
levels 테이블을 만들면 ERD가 13개가 되는데, 밸런스는 자주 조정할 값이라
상수 배열이면 숫자만 바꾸면 된다.

아래 값은 임시다. 실제 곡선은 4주차에 챌린지 목록을 채우면서 정한다.
"""

MAX_LEVEL = 30

#: 레벨 n에 도달하는 데 필요한 누적 경험치. 인덱스가 곧 레벨이다(0번은 자리 채움).
#: 지금은 레벨당 100씩 늘어나는 단순 곡선이다.
XP_THRESHOLDS: list[int] = [0] + [100 * n for n in range(MAX_LEVEL)]


def level_for_xp(total_xp: int) -> int:
    """누적 경험치로 레벨을 구한다."""
    level = 1
    for candidate in range(1, MAX_LEVEL + 1):
        if total_xp >= XP_THRESHOLDS[candidate]:
            level = candidate
        else:
            break
    return level


def level_progress(total_xp: int) -> tuple[int, int, int | None]:
    """(레벨, 이번 레벨에서 쌓은 경험치, 다음 레벨까지 필요한 경험치)를 돌려준다.

    최고 레벨이면 다음 값이 없으므로 None을 준다.
    """
    level = level_for_xp(total_xp)
    current_level_xp = total_xp - XP_THRESHOLDS[level]

    if level >= MAX_LEVEL:
        return level, current_level_xp, None

    next_level_xp = XP_THRESHOLDS[level + 1] - XP_THRESHOLDS[level]
    return level, current_level_xp, next_level_xp

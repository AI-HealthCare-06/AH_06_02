"""나의 성장 달력과 주차별 이력. 인정 완료 기록만 도장으로 집계한다."""

from calendar import monthrange
from collections import Counter
from datetime import date, datetime
from typing import Any

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import Challenge, ChallengeLog, Monster, UserAttackCycle, UserChallenge, UserMonster
from app.services.challenge_goals import mission_title


class AdventureProgressService:
    async def get(self, user_id: int, month: str | None) -> dict[str, Any]:
        selected = month or datetime.now(config.TIMEZONE).strftime("%Y-%m")
        try:
            first = date.fromisoformat(selected + "-01")
            if first.strftime("%Y-%m") != selected:
                raise ValueError
        except ValueError as exc:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="조회할 달을 YYYY-MM으로 입력해주세요.") from exc
        last = first.replace(day=monthrange(first.year, first.month)[1])
        missions = await UserChallenge.filter(user_id=user_id, start_date__lte=last, end_date__gte=first).order_by(
            "-start_date", "-id"
        )
        masters = {ch.id: ch for ch in await Challenge.filter(id__in=[m.challenge_id for m in missions])}
        logs = await ChallengeLog.filter(
            user_challenge_id__in=[m.id for m in missions],
            log_date__gte=first,
            log_date__lte=last,
            reward_eligible=True,
        ).order_by("log_date", "id")
        counts = Counter(log.log_date.isoformat() for log in logs)
        cycles = await UserAttackCycle.filter(user_id=user_id, start_date__lte=last, end_date__gte=first).order_by(
            "-id"
        )
        target_rows = {
            row.id: row
            for row in await UserMonster.filter(
                user_id=user_id, id__in=[cycle.target_user_monster_id for cycle in cycles]
            )
        }
        monsters = {
            row.id: row for row in await Monster.filter(id__in=[row.monster_id for row in target_rows.values()])
        }
        return {
            "month": selected,
            "days": [{"date": day, "count": count} for day, count in sorted(counts.items())],
            "missions": [
                {
                    "user_challenge_id": m.id,
                    "cycle_id": m.cycle_id,
                    "title": mission_title(m, masters[m.challenge_id]),
                    "factor_key": masters[m.challenge_id].factor_key,
                    "start_date": m.start_date,
                    "end_date": m.end_date,
                    "status": m.status,
                    "goal_config_snapshot": m.goal_config_snapshot,
                    "logs": [
                        {"log_id": log.id, "date": log.log_date, "xp": log.xp_granted, "context_slot": log.context_slot}
                        for log in logs
                        if log.user_challenge_id == m.id
                    ],
                }
                for m in missions
            ],
            "cycles": [
                {
                    "cycle_id": cycle.id,
                    "status": cycle.status,
                    "start_date": cycle.start_date,
                    "end_date": cycle.end_date,
                    "target": monsters[target_rows[cycle.target_user_monster_id].monster_id].code,
                }
                for cycle in cycles
            ],
        }

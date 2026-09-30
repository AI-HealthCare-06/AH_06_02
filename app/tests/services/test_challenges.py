from datetime import date

from app.services.challenges import progress_rate, week_start_for


def test_week_start_for_uses_monday() -> None:
    assert week_start_for(date(2026, 9, 30)) == date(2026, 9, 28)


def test_progress_rate_caps_at_100() -> None:
    assert progress_rate(0, 2) == 0.0
    assert progress_rate(1, 2) == 50.0
    assert progress_rate(2, 2) == 100.0
    assert progress_rate(5, 2) == 100.0

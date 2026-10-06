from datetime import datetime

from tortoise.contrib.test import TestCase

from app.models.health_records import HealthRecord, InputMode


def test_health_record_uses_fixed_table_name() -> None:
    assert HealthRecord._meta.db_table == "health_records"


def test_input_mode_contract() -> None:
    assert {item.value for item in InputMode} == {"simple", "detail", "daily"}


def test_health_record_has_26_spec_columns() -> None:
    assert len(HealthRecord._meta.db_fields) == 26


class TestHealthRecordModel(TestCase):
    async def test_records_accumulate_per_user(self) -> None:
        recorded_at = datetime(2026, 10, 6)
        await HealthRecord.create(user_id=1, recorded_at=recorded_at)
        await HealthRecord.create(user_id=1, recorded_at=recorded_at)

        # 덮어쓰지 않고 쌓는다 (REQ-HLTH-004)
        assert await HealthRecord.filter(user_id=1).count() == 2

    async def test_input_mode_defaults_to_simple(self) -> None:
        record = await HealthRecord.create(user_id=2, recorded_at=datetime(2026, 10, 6))

        assert record.input_mode == InputMode.SIMPLE
        assert record.sbp is None

import datetime as dt
from zoneinfo import ZoneInfo

from bot.digest import next_run_at

TZ = ZoneInfo("Europe/Madrid")


def test_before_target_time_runs_today():
    now = dt.datetime(2026, 7, 16, 6, 30, tzinfo=TZ)
    target = next_run_at(now, 7, 0)
    assert target == dt.datetime(2026, 7, 16, 7, 0, tzinfo=TZ)


def test_after_target_time_runs_tomorrow():
    now = dt.datetime(2026, 7, 16, 8, 0, tzinfo=TZ)
    target = next_run_at(now, 7, 0)
    assert target == dt.datetime(2026, 7, 17, 7, 0, tzinfo=TZ)


def test_exactly_at_target_time_runs_tomorrow():
    now = dt.datetime(2026, 7, 16, 7, 0, tzinfo=TZ)
    target = next_run_at(now, 7, 0)
    assert target == dt.datetime(2026, 7, 17, 7, 0, tzinfo=TZ)

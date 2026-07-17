import asyncio
import datetime as dt

from bot.config import Config
from bot.task_view import (
    _cutoff_for_ctx,
    _days_overdue,
    _format_task_line,
    _overdue_marker,
    empty_message_for_ctx,
    format_due,
    format_task_list_text,
    get_completed_between,
    has_tasks_due_between,
    week_end,
    week_start,
)


def _config(timezone: str = "Europe/Madrid", week_start_day: int = 1) -> Config:
    return Config(
        bot_token="x",
        vikunja_url="https://example.com/api/v1",
        admin_telegram_id=1,
        fernet_key="x",
        users_file="users.json",
        pause_state_file="digest_pause.json",
        default_project_name="Inbox",
        weekly_project_name="Week to Week",
        daily_project_name="Day to Day",
        digest_time="07:00",
        timezone=timezone,
        digest_chat_id=None,
        week_start_day=week_start_day,
    )


class _FakeClient:
    def __init__(self, tasks):
        self._tasks = tasks

    async def list_tasks(self, project_id=None, done=False):
        if done is None:
            return self._tasks
        return [t for t in self._tasks if t.get("done", False) == done]


def test_empty_message_for_ctx():
    assert empty_message_for_ctx("t") == "Nothing due today. 🎉"
    assert empty_message_for_ctx("w") == "Nothing due this week. 🎉"
    assert empty_message_for_ctx("a") == "No open tasks. 🎉"
    assert empty_message_for_ctx("p12") == "No open tasks. 🎉"


def test_format_due_converts_utc_to_local():
    # 22:00 UTC on a summer day is 00:00 the next day in Madrid (CEST, UTC+2)
    text = format_due("2026-07-16T22:00:00Z", _config("Europe/Madrid"))
    assert "Fri 17 Jul 00:00" in text


def test_format_due_empty_for_unset_due_date():
    assert format_due(None, _config()) == ""
    assert format_due("0001-01-01T00:00:00Z", _config()) == ""


def test_cutoff_for_project_ctx_is_none():
    assert _cutoff_for_ctx("p5", _config()) is None
    assert _cutoff_for_ctx("a", _config()) is None


def test_week_cutoff_is_upcoming_sunday():
    import zoneinfo

    tz = zoneinfo.ZoneInfo("Europe/Madrid")
    config = _config("Europe/Madrid")

    # Thursday 2026-07-16
    thursday = dt.datetime(2026, 7, 16, 10, 0, tzinfo=tz)
    cutoff = _cutoff_for_ctx("w", config, now=thursday)
    assert cutoff == dt.datetime(2026, 7, 19, 23, 59, 59, tzinfo=tz)

    # Sunday itself: week cutoff should equal today's end
    sunday = dt.datetime(2026, 7, 19, 10, 0, tzinfo=tz)
    cutoff_sunday = _cutoff_for_ctx("w", config, now=sunday)
    assert cutoff_sunday == dt.datetime(2026, 7, 19, 23, 59, 59, tzinfo=tz)


def test_week_boundaries_respect_configurable_start_day():
    import zoneinfo

    tz = zoneinfo.ZoneInfo("Europe/Madrid")
    wednesday = dt.datetime(2026, 7, 15, 10, 0, tzinfo=tz)  # 2026-07-15 is a Wednesday

    monday_config = _config(week_start_day=1)
    assert week_start(monday_config, wednesday) == dt.datetime(2026, 7, 13, 0, 0, tzinfo=tz)
    assert week_end(monday_config, wednesday) == dt.datetime(2026, 7, 19, 23, 59, 59, tzinfo=tz)

    wednesday_config = _config(week_start_day=3)
    assert week_start(wednesday_config, wednesday) == dt.datetime(2026, 7, 15, 0, 0, tzinfo=tz)
    assert week_end(wednesday_config, wednesday) == dt.datetime(2026, 7, 21, 23, 59, 59, tzinfo=tz)


def test_has_tasks_due_between():
    tz_start = dt.datetime(2026, 7, 13, 0, 0, tzinfo=dt.timezone.utc)
    tz_end = dt.datetime(2026, 7, 19, 23, 59, 59, tzinfo=dt.timezone.utc)

    empty_client = _FakeClient([{"id": 1, "due_date": "0001-01-01T00:00:00Z"}])
    assert asyncio.run(has_tasks_due_between(empty_client, 5, tz_start, tz_end)) is False

    matching_client = _FakeClient([{"id": 1, "due_date": "2026-07-15T10:00:00Z"}])
    assert asyncio.run(has_tasks_due_between(matching_client, 5, tz_start, tz_end)) is True


def test_get_completed_between_filters_by_done_at_not_current_status():
    start = dt.datetime(2026, 7, 6, 0, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 7, 12, 23, 59, 59, tzinfo=dt.timezone.utc)

    tasks = [
        # Completed within range, currently still marked done
        {"id": 1, "title": "Buy milk", "done": True, "done_at": "2026-07-08T09:00:00Z"},
        # A recurring task: done_at falls in range but it's already flipped
        # back to done=false for its next occurrence - must still count.
        {"id": 2, "title": "Water plants", "done": False, "done_at": "2026-07-09T09:00:00Z"},
        # Outside the range
        {"id": 3, "title": "Old task", "done": True, "done_at": "2026-06-01T09:00:00Z"},
        # Never completed
        {"id": 4, "title": "Someday", "done": False, "done_at": "0001-01-01T00:00:00Z"},
    ]
    client = _FakeClient(tasks)
    result = asyncio.run(get_completed_between(client, start, end))
    assert [t["id"] for t in result] == [1, 2]


def test_overdue_marker_tiers():
    assert _overdue_marker(0) == ("", False)
    assert _overdue_marker(-1) == ("", False)
    assert _overdue_marker(1) == ("⚠️ ", False)
    assert _overdue_marker(2) == ("⚠️ ", False)
    assert _overdue_marker(3) == ("🔴 ", True)
    assert _overdue_marker(6) == ("🔴 ", True)
    assert _overdue_marker(7) == ("🚨🚨 ", True)
    assert _overdue_marker(30) == ("🚨🚨 ", True)


def test_days_overdue():
    import zoneinfo

    config = _config("Europe/Madrid")
    now = dt.datetime(2026, 7, 20, 10, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Madrid"))
    assert _days_overdue(None, config, now) == 0
    assert _days_overdue("0001-01-01T00:00:00Z", config, now) == 0
    assert _days_overdue("2026-07-20T05:00:00Z", config, now) == 0  # due today (local)
    assert _days_overdue("2026-07-17T05:00:00Z", config, now) == 3
    assert _days_overdue("2026-07-25T05:00:00Z", config, now) == -5  # due in the future


def test_format_task_line_escapes_and_bolds():
    config = _config("Europe/Madrid")
    now = dt.datetime(2026, 7, 20, 10, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Madrid"))

    not_overdue = {"id": 1, "title": "Buy milk", "due_date": "0001-01-01T00:00:00Z"}
    line = _format_task_line(1, not_overdue, config, now)
    assert line == "1. Buy milk"

    mildly_overdue = {"id": 2, "title": "<script>alert(1)</script>", "due_date": "2026-07-19T05:00:00Z"}
    line = _format_task_line(2, mildly_overdue, config, now)
    assert line.startswith("⚠️ 2. &lt;script&gt;")
    assert "<b>" not in line

    badly_overdue = {"id": 3, "title": "Old & forgotten", "due_date": "2026-07-10T05:00:00Z"}
    line = _format_task_line(3, badly_overdue, config, now)
    assert line.startswith("<b>🚨🚨 3. Old &amp; forgotten")
    assert line.endswith("</b>")


def test_format_task_list_text_escapes_project_header():
    config = _config("Europe/Madrid")
    tasks = [{"id": 1, "title": "Task", "project_id": 5, "due_date": "0001-01-01T00:00:00Z"}]
    titles = {5: "R&D <ideas>"}
    text = format_task_list_text(tasks, "a", titles, config)
    assert "📁 R&amp;D &lt;ideas&gt;" in text

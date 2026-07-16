import datetime as dt

from bot.config import Config
from bot.task_view import _cutoff_for_ctx, empty_message_for_ctx, format_due


def _config(timezone: str = "Europe/Madrid") -> Config:
    return Config(
        bot_token="x",
        vikunja_url="https://example.com/api/v1",
        admin_telegram_id=1,
        fernet_key="x",
        users_file="users.json",
        default_project_name="Inbox",
        weekly_project_name="Week to Week",
        digest_time="07:00",
        timezone=timezone,
    )


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

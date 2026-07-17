from datetime import datetime

from bot.quickadd import describe_repeat, parse, parse_date_only

BASE = datetime(2026, 7, 15, 9, 0)


def test_plain_title():
    result = parse("Buy milk")
    assert result.title == "Buy milk"
    assert result.project is None
    assert result.labels == []
    assert result.priority is None
    assert result.due_date is None


def test_label_and_project():
    result = parse("Buy milk *shopping +Home")
    assert result.title == "Buy milk"
    assert result.project == "Home"
    assert result.labels == ["shopping"]


def test_multiple_labels():
    result = parse("Plan trip *travel *urgent-ish")
    assert result.title == "Plan trip"
    assert result.labels == ["travel", "urgent-ish"]


def test_priority_word():
    result = parse("Finish report !urgent")
    assert result.title == "Finish report"
    assert result.priority == 4


def test_priority_digit():
    result = parse("Finish report !3")
    assert result.title == "Finish report"
    assert result.priority == 3


def test_due_date_relative():
    result = parse("Pay rent tomorrow 5pm", relative_base=BASE)
    assert result.title == "Pay rent"
    assert result.due_date is not None
    assert result.due_date.day == 16
    assert result.due_date.hour == 17


def test_combined():
    result = parse("Pay rent +Bills !high tomorrow 5pm", relative_base=BASE)
    assert result.title == "Pay rent"
    assert result.project == "Bills"
    assert result.priority == 3
    assert result.due_date is not None
    assert result.due_date.day == 16


def test_quoted_multi_word_label_and_project():
    result = parse('Call plumber *"home repair" +"Household Chores"')
    assert result.title == "Call plumber"
    assert result.labels == ["home repair"]
    assert result.project == "Household Chores"


def test_parse_date_only_finds_a_date():
    due = parse_date_only("friday 5pm", relative_base=BASE)
    assert due is not None
    assert due.hour == 17


def test_parse_date_only_returns_none_for_gibberish():
    assert parse_date_only("asdkfjadsf", relative_base=BASE) is None


def test_parse_date_only_returns_none_for_empty_text():
    assert parse_date_only("", relative_base=BASE) is None


def test_repeat_monthly():
    result = parse("Clean dishwasher filter ~monthly")
    assert result.title == "Clean dishwasher filter"
    assert result.repeat_after is None
    assert result.repeat_mode == 1
    assert describe_repeat(result.repeat_after, result.repeat_mode) == "monthly"


def test_repeat_daily():
    result = parse("Water plants ~daily")
    assert result.title == "Water plants"
    assert result.repeat_after == 86400
    assert result.repeat_mode == 3


def test_repeat_weekly():
    result = parse("Take out recycling ~weekly")
    assert result.repeat_after == 7 * 86400
    assert result.repeat_mode == 3


def test_repeat_every_n_days():
    result = parse("Check dehumidifier ~every 3 days")
    assert result.title == "Check dehumidifier"
    assert result.repeat_after == 3 * 86400
    assert result.repeat_mode == 3
    assert describe_repeat(result.repeat_after, result.repeat_mode) == "every 3 days"


def test_repeat_every_n_weeks():
    result = parse("Mow lawn ~every 2 weeks")
    assert result.repeat_after == 2 * 7 * 86400
    assert describe_repeat(result.repeat_after, result.repeat_mode) == "every 2 weeks"


def test_no_repeat_by_default():
    result = parse("Buy milk")
    assert result.repeat_after is None
    assert result.repeat_mode is None
    assert describe_repeat(result.repeat_after, result.repeat_mode) is None


def test_repeat_yearly():
    result = parse("Test smoke detectors ~yearly")
    assert result.title == "Test smoke detectors"
    assert result.repeat_after == 365 * 86400
    assert result.repeat_mode == 3
    assert describe_repeat(result.repeat_after, result.repeat_mode) == "yearly"


def test_repeat_every_n_months():
    result = parse("Service HVAC ~every 3 months")
    assert result.title == "Service HVAC"
    assert result.repeat_after == 3 * 30 * 86400
    assert result.repeat_mode == 3
    assert describe_repeat(result.repeat_after, result.repeat_mode) == "every 3 months"


def test_repeat_every_n_years():
    result = parse("Renew insurance ~every 2 years")
    assert result.repeat_after == 2 * 365 * 86400
    assert describe_repeat(result.repeat_after, result.repeat_mode) == "every 2 years"


def test_describe_repeat_prefers_largest_unit():
    # 90 days is expressible as weeks or days too, but months reads better.
    assert describe_repeat(90 * 86400, 3) == "every 3 months"
    assert describe_repeat(365 * 86400, 3) == "yearly"
    assert describe_repeat(730 * 86400, 3) == "every 2 years"

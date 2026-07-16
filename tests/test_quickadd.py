from datetime import datetime

from bot.quickadd import parse, parse_date_only

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

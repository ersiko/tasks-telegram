import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from dateparser.search import search_dates

LABEL_RE = re.compile(r'\*("([^"]+)"|(\S+))')
PROJECT_RE = re.compile(r'\+("([^"]+)"|(\S+))')
PRIORITY_WORDS = {"low": 1, "medium": 2, "high": 3, "urgent": 4, "donow": 5}
PRIORITY_RE = re.compile(r"!(donow|urgent|high|medium|low|[1-5])\b", re.IGNORECASE)
REPEAT_RE = re.compile(r"~(daily|weekly|monthly|every\s+\d+\s+(?:days|day|weeks|week))", re.IGNORECASE)
REPEAT_EVERY_RE = re.compile(r"every\s+(\d+)\s+(days|day|weeks|week)", re.IGNORECASE)

SECONDS_PER_DAY = 86400

# repeat_mode values match Vikunja's Task model: 1 = fixed monthly step
# (calendar-correct, ignores repeat_after); 3 = repeat_after seconds,
# counted from the completion date rather than the original due date -
# the more intuitive default for chores ("a month after I actually did it",
# not "a month after it was originally due").
REPEAT_MODE_MONTHLY = 1
REPEAT_MODE_FROM_COMPLETION = 3


@dataclass
class QuickAddResult:
    title: str
    project: Optional[str] = None
    labels: list = field(default_factory=list)
    priority: Optional[int] = None
    due_date: Optional[datetime] = None
    repeat_after: Optional[int] = None
    repeat_mode: Optional[int] = None


def _match_value(match: re.Match) -> str:
    return match.group(2) or match.group(3)


def _extract_all(pattern: re.Pattern, text: str) -> tuple[list[str], str]:
    values: list[str] = []

    def _consume(match: re.Match) -> str:
        values.append(_match_value(match))
        return " "

    return values, pattern.sub(_consume, text)


def _extract_one(pattern: re.Pattern, text: str) -> tuple[Optional[str], str]:
    match = pattern.search(text)
    if not match:
        return None, text
    remaining = text[: match.start()] + " " + text[match.end():]
    return _match_value(match), remaining


def _search_date(text: str, relative_base: Optional[datetime]) -> Optional[tuple[str, datetime]]:
    settings = {"PREFER_DATES_FROM": "future"}
    if relative_base is not None:
        settings["RELATIVE_BASE"] = relative_base
    matches = search_dates(text, languages=["en"], settings=settings)
    if not matches:
        return None
    matched_text, parsed_dt = matches[-1]
    if len(matched_text.strip()) < 3:
        return None
    return matched_text, parsed_dt


def parse_date_only(text: str, relative_base: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a natural-language date/time out of free text with no quick-add magic expected."""
    match = _search_date(text.strip(), relative_base)
    return match[1] if match else None


def _parse_repeat_phrase(phrase: str) -> tuple[Optional[int], Optional[int]]:
    lowered = phrase.lower()
    if lowered == "daily":
        return SECONDS_PER_DAY, REPEAT_MODE_FROM_COMPLETION
    if lowered == "weekly":
        return 7 * SECONDS_PER_DAY, REPEAT_MODE_FROM_COMPLETION
    if lowered == "monthly":
        return None, REPEAT_MODE_MONTHLY
    every_match = REPEAT_EVERY_RE.match(lowered)
    if every_match:
        count = int(every_match.group(1))
        unit = every_match.group(2)
        per_unit = SECONDS_PER_DAY if unit.startswith("day") else 7 * SECONDS_PER_DAY
        return count * per_unit, REPEAT_MODE_FROM_COMPLETION
    return None, None


def describe_repeat(repeat_after: Optional[int], repeat_mode: Optional[int]) -> Optional[str]:
    """Human-readable description of a repeat_after/repeat_mode pair, for confirmation messages."""
    if repeat_mode is None:
        return None
    if repeat_mode == REPEAT_MODE_MONTHLY:
        return "monthly"
    if not repeat_after:
        return None
    days = repeat_after / SECONDS_PER_DAY
    if days == 1:
        return "daily"
    if days == 7:
        return "weekly"
    if days % 7 == 0:
        return f"every {int(days // 7)} weeks"
    return f"every {int(days)} days"


def parse(text: str, relative_base: Optional[datetime] = None) -> QuickAddResult:
    working = text

    labels, working = _extract_all(LABEL_RE, working)
    project, working = _extract_one(PROJECT_RE, working)

    priority = None
    priority_match = PRIORITY_RE.search(working)
    if priority_match:
        raw = priority_match.group(1).lower()
        priority = PRIORITY_WORDS.get(raw) or (int(raw) if raw.isdigit() else None)
        working = working[: priority_match.start()] + " " + working[priority_match.end():]

    repeat_after = None
    repeat_mode = None
    repeat_match = REPEAT_RE.search(working)
    if repeat_match:
        repeat_after, repeat_mode = _parse_repeat_phrase(repeat_match.group(1))
        working = working[: repeat_match.start()] + " " + working[repeat_match.end():]

    working = re.sub(r"\s+", " ", working).strip()

    due_date = None
    if working:
        found = _search_date(working, relative_base)
        if found:
            matched_text, due_date = found
            start = working.rfind(matched_text)
            if start != -1:
                working = working[:start] + working[start + len(matched_text):]

    title = re.sub(r"\s+", " ", working).strip()

    return QuickAddResult(
        title=title,
        project=project,
        labels=labels,
        priority=priority,
        due_date=due_date,
        repeat_after=repeat_after,
        repeat_mode=repeat_mode,
    )

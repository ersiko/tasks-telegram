import datetime as dt
import html
from typing import Optional
from zoneinfo import ZoneInfo

from bot.config import Config
from bot.vikunja_client import VikunjaClient

MAX_LISTED_TASKS = 20


def _tz(config: Config) -> ZoneInfo:
    return ZoneInfo(config.timezone)


def _parse_due(due_date: Optional[str]) -> Optional[dt.datetime]:
    if not due_date or due_date.startswith("0001"):
        return None
    try:
        return dt.datetime.fromisoformat(due_date.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_due(due_date: Optional[str], config: Config) -> str:
    parsed = _parse_due(due_date)
    if parsed is None:
        return ""
    local = parsed.astimezone(_tz(config))
    return f" (due {local.strftime('%a %d %b %H:%M')})"


def _days_overdue(due_date: Optional[str], config: Config, now: Optional[dt.datetime] = None) -> int:
    parsed = _parse_due(due_date)
    if parsed is None:
        return 0
    now_local = now if now is not None else dt.datetime.now(_tz(config))
    due_local = parsed.astimezone(_tz(config))
    return (now_local.date() - due_local.date()).days


def _overdue_marker(days_overdue: int) -> tuple[str, bool]:
    """(emoji prefix, bold) - escalates the more overdue a task is, so
    something ignored for a week doesn't blend in with something a day
    late. Not overdue (due today or later) gets no marker at all."""
    if days_overdue <= 0:
        return "", False
    if days_overdue <= 2:
        return "⚠️ ", False
    if days_overdue <= 6:
        return "🔴 ", True
    return "🚨🚨 ", True


def _format_task_line(index: int, task: dict, config: Config, now: Optional[dt.datetime] = None) -> str:
    title = html.escape(task["title"])
    due_str = format_due(task.get("due_date"), config)
    prefix, bold = _overdue_marker(_days_overdue(task.get("due_date"), config, now))
    line = f"{prefix}{index}. {title}{due_str}"
    return f"<b>{line}</b>" if bold else line


def empty_message_for_ctx(ctx: str) -> str:
    return {
        "t": "Nothing due today. 🎉",
        "w": "Nothing due this week. 🎉",
    }.get(ctx, "No open tasks. 🎉")


def _week_start(now_local: dt.datetime, week_start_day: int) -> dt.datetime:
    """Start (00:00 local) of the week containing now_local, for a week that
    begins on week_start_day (ISO weekday, 1=Monday..7=Sunday)."""
    days_since_start = (now_local.isoweekday() - week_start_day) % 7
    start_date = now_local - dt.timedelta(days=days_since_start)
    return start_date.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_end(now_local: dt.datetime, week_start_day: int) -> dt.datetime:
    start = _week_start(now_local, week_start_day)
    return (start + dt.timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=0)


def week_start(config: Config, now: Optional[dt.datetime] = None) -> dt.datetime:
    """Start (00:00 local) of the current week, per config.week_start_day."""
    now_local = now if now is not None else dt.datetime.now(_tz(config))
    return _week_start(now_local, config.week_start_day)


def week_end(config: Config, now: Optional[dt.datetime] = None) -> dt.datetime:
    """End of the current week in local time, per config.week_start_day -
    the target due date for /plan_week and the cutoff /week uses."""
    now_local = now if now is not None else dt.datetime.now(_tz(config))
    return _week_end(now_local, config.week_start_day)


def _cutoff_for_ctx(ctx: str, config: Config, now: Optional[dt.datetime] = None) -> Optional[dt.datetime]:
    """End-of-day/week cutoff in local time, or None for non-date-bounded ctx.

    `now` is injectable for tests; defaults to the real current time.
    """
    now_local = now if now is not None else dt.datetime.now(_tz(config))
    if ctx == "t":
        return now_local.replace(hour=23, minute=59, second=59, microsecond=0)
    if ctx == "w":
        return _week_end(now_local, config.week_start_day)
    return None


async def get_planning_candidates(
    client: VikunjaClient, project_id: int, config: Config, now: Optional[dt.datetime] = None
) -> list[dict]:
    """Open tasks in project_id with no due date, or a due date before this
    week (never scheduled, or carried over unfinished) - candidates for
    /plan_week to assign this week's due date to. Tasks already scheduled
    for this week or later are left alone."""
    now_local = now if now is not None else dt.datetime.now(_tz(config))
    start = _week_start(now_local, config.week_start_day)

    tasks = await client.list_tasks(project_id=project_id)
    candidates = []
    for task in tasks:
        parsed = _parse_due(task.get("due_date"))
        if parsed is None or parsed.astimezone(start.tzinfo) < start:
            candidates.append(task)
    candidates.sort(key=lambda t: t.get("due_date") or "9999")
    return candidates[:MAX_LISTED_TASKS]


async def has_tasks_due_between(
    client: VikunjaClient, project_id: int, start: dt.datetime, end: dt.datetime
) -> bool:
    """Whether project_id has any (open) task due within [start, end]."""
    tasks = await client.list_tasks(project_id=project_id)
    for task in tasks:
        parsed = _parse_due(task.get("due_date"))
        if parsed is not None and start <= parsed.astimezone(start.tzinfo) <= end:
            return True
    return False


async def get_completed_between(client: VikunjaClient, start: dt.datetime, end: dt.datetime) -> list[dict]:
    """Tasks marked done with done_at in [start, end], oldest first.

    Recurring tasks flip done -> undone again as part of advancing to their
    next occurrence, so this can't filter on current done status via the API
    (done=True would exclude exactly the recurring completions we want) -
    fetch everything and rely on done_at (Vikunja: "system-controlled", set
    whenever a task is marked done) still reflecting the last completion
    even after that flip. Not yet confirmed against a real recurring task -
    worth checking once one has actually gone through a done/recur cycle.
    """
    tasks = await client.list_tasks(project_id=None, done=None)
    completed = []
    for task in tasks:
        done_at = _parse_due(task.get("done_at"))
        if done_at is None:
            continue
        done_at_local = done_at.astimezone(start.tzinfo)
        if start <= done_at_local <= end:
            completed.append((done_at_local, task))
    completed.sort(key=lambda pair: pair[0])
    return [task for _, task in completed]


async def get_tasks_for_ctx(client: VikunjaClient, ctx: str, config: Config) -> list[dict]:
    cutoff = _cutoff_for_ctx(ctx, config)
    if cutoff is not None:
        tasks = await client.list_tasks()
        due_soon = []
        for task in tasks:
            parsed = _parse_due(task.get("due_date"))
            if parsed is None:
                continue
            if parsed.astimezone(cutoff.tzinfo) <= cutoff:
                due_soon.append((parsed, task))
        due_soon.sort(key=lambda pair: pair[0])
        return [task for _, task in due_soon[:MAX_LISTED_TASKS]]

    project_id = int(ctx[1:]) if ctx.startswith("p") else None
    tasks = await client.list_tasks(project_id=project_id)
    tasks = sorted(tasks, key=lambda t: t.get("due_date") or "9999")
    return tasks[:MAX_LISTED_TASKS]


async def project_titles(client: VikunjaClient) -> dict[int, str]:
    projects = await client.list_projects()
    return {p["id"]: p["title"] for p in projects}


async def ordered_tasks(client: VikunjaClient, ctx: str, config: Config) -> tuple[list[dict], Optional[dict[int, str]]]:
    """Fetch tasks for ctx; for multi-project views, group them by project.

    Returns (tasks, project_titles) - project_titles is None for a
    single-project view (ctx starts with "p"), since grouping there would
    be redundant. The same ordering drives both the displayed text and any
    picker keyboard, so buttons line up with what's on screen.
    """
    tasks = await get_tasks_for_ctx(client, ctx, config)
    if not tasks or ctx.startswith("p"):
        return tasks, None
    titles = await project_titles(client)
    tasks = sorted(tasks, key=lambda t: titles.get(t.get("project_id"), "").lower())
    return tasks, titles


def format_task_list_text(
    tasks: list[dict],
    ctx: str,
    project_titles_map: Optional[dict[int, str]],
    config: Config,
    now: Optional[dt.datetime] = None,
) -> str:
    if not tasks:
        return empty_message_for_ctx(ctx)

    if not project_titles_map:
        return "\n".join(_format_task_line(i, t, config, now) for i, t in enumerate(tasks, start=1))

    lines: list[str] = []
    current_project = None
    for i, task in enumerate(tasks, start=1):
        title = project_titles_map.get(task.get("project_id"), "Unknown")
        if title != current_project:
            if lines:
                lines.append("")
            lines.append(f"📁 {html.escape(title)}")
            current_project = title
        lines.append(_format_task_line(i, task, config, now))
    return "\n".join(lines)

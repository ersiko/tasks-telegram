import datetime as dt
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


def empty_message_for_ctx(ctx: str) -> str:
    return {
        "t": "Nothing due today. 🎉",
        "w": "Nothing due this week. 🎉",
    }.get(ctx, "No open tasks. 🎉")


def _cutoff_for_ctx(ctx: str, config: Config, now: Optional[dt.datetime] = None) -> Optional[dt.datetime]:
    """End-of-day/week cutoff in local time, or None for non-date-bounded ctx.

    Weeks run Monday-Sunday. On Sunday, the week cutoff equals today's.
    `now` is injectable for tests; defaults to the real current time.
    """
    now_local = now if now is not None else dt.datetime.now(_tz(config))
    if ctx == "t":
        return now_local.replace(hour=23, minute=59, second=59, microsecond=0)
    if ctx == "w":
        days_until_sunday = 7 - now_local.isoweekday()
        end_date = now_local + dt.timedelta(days=days_until_sunday)
        return end_date.replace(hour=23, minute=59, second=59, microsecond=0)
    return None


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
    tasks: list[dict], ctx: str, project_titles_map: Optional[dict[int, str]], config: Config
) -> str:
    if not tasks:
        return empty_message_for_ctx(ctx)

    if not project_titles_map:
        return "\n".join(f"{i}. {t['title']}{format_due(t.get('due_date'), config)}" for i, t in enumerate(tasks, start=1))

    lines: list[str] = []
    current_project = None
    for i, task in enumerate(tasks, start=1):
        title = project_titles_map.get(task.get("project_id"), "Unknown")
        if title != current_project:
            if lines:
                lines.append("")
            lines.append(f"📁 {title}")
            current_project = title
        lines.append(f"{i}. {task['title']}{format_due(task.get('due_date'), config)}")
    return "\n".join(lines)

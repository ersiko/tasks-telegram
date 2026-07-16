import datetime as dt
from typing import Optional

from bot.vikunja_client import VikunjaClient

MAX_LISTED_TASKS = 20


def format_due(due_date: Optional[str]) -> str:
    if not due_date or due_date.startswith("0001"):
        return ""
    try:
        parsed = dt.datetime.fromisoformat(due_date.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return ""
    return f" (due {parsed.strftime('%a %d %b %H:%M')})"


def empty_message_for_ctx(ctx: str) -> str:
    return "Nothing due today. 🎉" if ctx == "t" else "No open tasks. 🎉"


async def get_tasks_for_ctx(client: VikunjaClient, ctx: str) -> list[dict]:
    if ctx == "t":
        tasks = await client.list_tasks()
        today_end = dt.datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=0)
        due_today = []
        for task in tasks:
            due = task.get("due_date")
            if not due or due.startswith("0001"):
                continue
            try:
                due_dt = dt.datetime.fromisoformat(due.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
            if due_dt <= today_end:
                due_today.append((due_dt, task))
        due_today.sort(key=lambda pair: pair[0])
        return [task for _, task in due_today[:MAX_LISTED_TASKS]]

    project_id = int(ctx[1:]) if ctx.startswith("p") else None
    tasks = await client.list_tasks(project_id=project_id)
    tasks = sorted(tasks, key=lambda t: t.get("due_date") or "9999")
    return tasks[:MAX_LISTED_TASKS]


async def project_titles(client: VikunjaClient) -> dict[int, str]:
    projects = await client.list_projects()
    return {p["id"]: p["title"] for p in projects}


async def ordered_tasks(client: VikunjaClient, ctx: str) -> tuple[list[dict], Optional[dict[int, str]]]:
    """Fetch tasks for ctx; for multi-project views, group them by project.

    Returns (tasks, project_titles) - project_titles is None for a
    single-project view (ctx starts with "p"), since grouping there would
    be redundant. The same ordering drives both the displayed text and any
    picker keyboard, so buttons line up with what's on screen.
    """
    tasks = await get_tasks_for_ctx(client, ctx)
    if not tasks or ctx.startswith("p"):
        return tasks, None
    titles = await project_titles(client)
    tasks = sorted(tasks, key=lambda t: titles.get(t.get("project_id"), "").lower())
    return tasks, titles


def format_task_list_text(tasks: list[dict], ctx: str, project_titles_map: Optional[dict[int, str]]) -> str:
    if not tasks:
        return empty_message_for_ctx(ctx)

    if not project_titles_map:
        return "\n".join(f"{i}. {t['title']}{format_due(t.get('due_date'))}" for i, t in enumerate(tasks, start=1))

    lines: list[str] = []
    current_project = None
    for i, task in enumerate(tasks, start=1):
        title = project_titles_map.get(task.get("project_id"), "Unknown")
        if title != current_project:
            if lines:
                lines.append("")
            lines.append(f"📁 {title}")
            current_project = title
        lines.append(f"{i}. {task['title']}{format_due(task.get('due_date'))}")
    return "\n".join(lines)

import datetime as dt

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import quickadd
from bot.access import UNREGISTERED_MESSAGE, get_client_for_user
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.keyboards import list_menu_keyboard, task_picker_keyboard, task_row_keyboard
from bot.vikunja_client import VikunjaAPIError, VikunjaClient

router = Router(name="tasks")

MAX_LISTED_TASKS = 20


def _format_due(due_date: str | None) -> str:
    if not due_date or due_date.startswith("0001"):
        return ""
    try:
        parsed = dt.datetime.fromisoformat(due_date.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return ""
    return f" (due {parsed.strftime('%a %d %b %H:%M')})"


def _empty_message_for_ctx(ctx: str) -> str:
    return "Nothing due today. 🎉" if ctx == "t" else "No open tasks. 🎉"


async def _get_tasks_for_ctx(client: VikunjaClient, ctx: str) -> list[dict]:
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


async def _project_titles(client: VikunjaClient) -> dict[int, str]:
    projects = await client.list_projects()
    return {p["id"]: p["title"] for p in projects}


async def _ordered_tasks(client: VikunjaClient, ctx: str) -> tuple[list[dict], dict[int, str] | None]:
    """Fetch tasks for ctx; for multi-project views, group them by project.

    Returns (tasks, project_titles) - project_titles is None for a
    single-project view (ctx starts with "p"), since grouping there would
    be redundant. The same ordering drives both the displayed text and the
    picker keyboard, so buttons line up with what's on screen.
    """
    tasks = await _get_tasks_for_ctx(client, ctx)
    if not tasks or ctx.startswith("p"):
        return tasks, None
    titles = await _project_titles(client)
    tasks = sorted(tasks, key=lambda t: titles.get(t.get("project_id"), "").lower())
    return tasks, titles


def _format_task_list_text(tasks: list[dict], ctx: str, project_titles: dict[int, str] | None) -> str:
    if not tasks:
        return _empty_message_for_ctx(ctx)

    if not project_titles:
        return "\n".join(f"{i}. {t['title']}{_format_due(t.get('due_date'))}" for i, t in enumerate(tasks, start=1))

    lines: list[str] = []
    current_project = None
    for i, task in enumerate(tasks, start=1):
        project_title = project_titles.get(task.get("project_id"), "Unknown")
        if project_title != current_project:
            if lines:
                lines.append("")
            lines.append(f"📁 {project_title}")
            current_project = project_title
        lines.append(f"{i}. {task['title']}{_format_due(task.get('due_date'))}")
    return "\n".join(lines)


async def _send_task_list(message: Message, client: VikunjaClient, ctx: str):
    tasks, titles = await _ordered_tasks(client, ctx)
    text = _format_task_list_text(tasks, ctx, titles)
    kb = list_menu_keyboard(ctx) if tasks else None
    await message.answer(text, reply_markup=kb)


async def _refresh_list_message(callback: CallbackQuery, client: VikunjaClient, ctx: str) -> None:
    tasks, titles = await _ordered_tasks(client, ctx)
    text = _format_task_list_text(tasks, ctx, titles)
    kb = list_menu_keyboard(ctx) if tasks else None
    await callback.message.edit_text(text, reply_markup=kb)


@router.message(Command("list"))
async def cmd_list(message: Message, command: CommandObject, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    ctx = "a"
    if command.args:
        project = await client.resolve_project(command.args.strip())
        if project is None:
            await message.answer(f"No project matching '{command.args.strip()}'.")
            return
        ctx = f"p{project['id']}"

    try:
        await _send_task_list(message, client, ctx)
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")


@router.message(Command("today"))
async def cmd_today(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    try:
        await _send_task_list(message, client, "t")
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_quick_add(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    result = quickadd.parse(message.text)
    if not result.title:
        await message.answer("I couldn't find a task title in that message.")
        return

    try:
        project = None
        if result.project:
            project = await client.resolve_project(result.project)
            if project is None:
                await message.answer(f"No project matching '{result.project}'; using the default instead.")
        if project is None:
            project = await client.resolve_project(config.default_project_name)
        if project is None:
            projects = await client.list_projects()
            if not projects:
                await message.answer("You have no projects in Vikunja yet — create one first.")
                return
            project = projects[0]

        task = await client.create_task(
            project["id"], result.title, due_date=result.due_date, priority=result.priority
        )

        for label_name in result.labels:
            label = await client.resolve_label(label_name)
            await client.add_label_to_task(task["id"], label["id"])

        summary = [f"✅ Added: {result.title}", f"Project: {project['title']}"]
        if result.labels:
            summary.append("Labels: " + ", ".join(result.labels))
        if result.priority:
            summary.append(f"Priority: {result.priority}")
        if result.due_date:
            summary.append(f"Due: {result.due_date.strftime('%a %d %b %H:%M')}")
        await message.answer("\n".join(summary), reply_markup=task_row_keyboard(task["id"]))
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja rejected that: {exc}")


@router.callback_query(F.data.startswith("menu:"))
async def cb_menu(callback: CallbackQuery, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(callback.from_user.id, user_store, cipher, config)
    if client is None:
        await callback.answer("You're not registered.", show_alert=True)
        return

    _, action, ctx = callback.data.split(":", 2)
    try:
        tasks, _ = await _ordered_tasks(client, ctx)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return

    if not tasks:
        await callback.answer("Nothing left to pick.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=task_picker_keyboard(tasks, action, ctx))
    await callback.answer()


@router.callback_query(F.data.startswith("back:"))
async def cb_back(callback: CallbackQuery, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(callback.from_user.id, user_store, cipher, config)
    if client is None:
        await callback.answer("You're not registered.", show_alert=True)
        return

    _, ctx = callback.data.split(":", 1)
    try:
        await _refresh_list_message(callback, client, ctx)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick(callback: CallbackQuery, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(callback.from_user.id, user_store, cipher, config)
    if client is None:
        await callback.answer("You're not registered.", show_alert=True)
        return

    _, action, ctx, task_id_str = callback.data.split(":", 3)
    task_id = int(task_id_str)
    try:
        if action == "done":
            await client.set_done(task_id, True)
        else:
            await client.delete_task(task_id)
        await _refresh_list_message(callback, client, ctx)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return

    await callback.answer("Marked done ✅" if action == "done" else "Deleted 🗑")


@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: CallbackQuery, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(callback.from_user.id, user_store, cipher, config)
    if client is None:
        await callback.answer("You're not registered.", show_alert=True)
        return
    task_id = int(callback.data.split(":", 1)[1])
    try:
        await client.set_done(task_id, True)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return
    await callback.message.edit_text(f"{callback.message.text}\n✅ marked done")
    await callback.answer("Marked done")


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(callback.from_user.id, user_store, cipher, config)
    if client is None:
        await callback.answer("You're not registered.", show_alert=True)
        return
    task_id = int(callback.data.split(":", 1)[1])
    try:
        await client.delete_task(task_id)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return
    await callback.message.edit_text(f"{callback.message.text}\n🗑 deleted")
    await callback.answer("Deleted")

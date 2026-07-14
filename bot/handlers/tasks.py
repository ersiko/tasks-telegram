import datetime as dt

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import quickadd
from bot.access import UNREGISTERED_MESSAGE, get_client_for_user
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.keyboards import task_row_keyboard
from bot.vikunja_client import VikunjaAPIError

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


@router.message(Command("list"))
async def cmd_list(message: Message, command: CommandObject, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    project_id = None
    if command.args:
        project = await client.resolve_project(command.args.strip())
        if project is None:
            await message.answer(f"No project matching '{command.args.strip()}'.")
            return
        project_id = project["id"]

    try:
        tasks = await client.list_tasks(project_id=project_id)
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")
        return

    if not tasks:
        await message.answer("No open tasks. 🎉")
        return

    tasks = sorted(tasks, key=lambda t: t.get("due_date") or "9999")[:MAX_LISTED_TASKS]
    for task in tasks:
        await message.answer(
            f"{task['title']}{_format_due(task.get('due_date'))}",
            reply_markup=task_row_keyboard(task["id"]),
        )


@router.message(Command("today"))
async def cmd_today(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    try:
        tasks = await client.list_tasks()
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")
        return

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

    if not due_today:
        await message.answer("Nothing due today. 🎉")
        return

    due_today.sort(key=lambda pair: pair[0])
    for due_dt, task in due_today[:MAX_LISTED_TASKS]:
        await message.answer(
            f"{task['title']} (due {due_dt.strftime('%a %d %b %H:%M')})",
            reply_markup=task_row_keyboard(task["id"]),
        )


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

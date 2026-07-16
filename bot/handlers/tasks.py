import time
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import quickadd
from bot.access import UNREGISTERED_MESSAGE, get_client_for_user
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.keyboards import list_menu_keyboard, reschedule_prompt_keyboard, task_picker_keyboard, task_row_keyboard
from bot.task_view import format_task_list_text, ordered_tasks
from bot.vikunja_client import VikunjaAPIError, VikunjaClient

router = Router(name="tasks")

RESCHEDULE_CLEAR_WORDS = {"none", "no date", "remove", "clear"}
RESCHEDULE_TTL_SECONDS = 600

# In-memory only, keyed by telegram_id: which task a user is mid-reschedule
# on. Lost on restart, which is fine - worst case they just tap Reschedule
# again. Bounded by RESCHEDULE_TTL_SECONDS so an abandoned reschedule can't
# permanently hijack that user's next quick-add message.
_pending_reschedule: dict[int, dict] = {}


def _pop_valid_pending_reschedule(user_id: int) -> Optional[dict]:
    entry = _pending_reschedule.pop(user_id, None)
    if entry is None:
        return None
    if time.monotonic() - entry["set_at"] > RESCHEDULE_TTL_SECONDS:
        return None
    return entry


async def _send_task_list(message: Message, client: VikunjaClient, ctx: str, config: Config):
    tasks, titles = await ordered_tasks(client, ctx, config)
    text = format_task_list_text(tasks, ctx, titles, config)
    kb = list_menu_keyboard(ctx) if tasks else None
    await message.answer(text, reply_markup=kb)


async def _refresh_list_message(callback: CallbackQuery, client: VikunjaClient, ctx: str, config: Config) -> None:
    tasks, titles = await ordered_tasks(client, ctx, config)
    text = format_task_list_text(tasks, ctx, titles, config)
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
        await _send_task_list(message, client, ctx, config)
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")


@router.message(Command("today"))
async def cmd_today(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    try:
        await _send_task_list(message, client, "t", config)
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")


@router.message(Command("week", "this_week"))
async def cmd_week(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    try:
        await _send_task_list(message, client, "w", config)
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")


async def _handle_reschedule_reply(message: Message, client: VikunjaClient, config: Config, pending: dict) -> None:
    text = message.text.strip()
    new_due = None if text.lower() in RESCHEDULE_CLEAR_WORDS else quickadd.parse_date_only(text)

    if new_due is None and text.lower() not in RESCHEDULE_CLEAR_WORDS:
        _pending_reschedule[message.from_user.id] = pending  # let them retry
        await message.answer(
            "I couldn't find a date in that. Try again (e.g. 'friday 5pm'), "
            "reply 'none' to remove the due date, or tap Cancel above."
        )
        return

    try:
        await client.set_due_date(pending["task_id"], new_due)
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja rejected that: {exc}")
        return

    tasks, titles = await ordered_tasks(client, pending["ctx"], config)
    list_text = format_task_list_text(tasks, pending["ctx"], titles, config)
    kb = list_menu_keyboard(pending["ctx"]) if tasks else None
    try:
        await message.bot.edit_message_text(
            chat_id=pending["chat_id"], message_id=pending["message_id"], text=list_text, reply_markup=kb
        )
    except Exception:
        pass  # original list message may be gone/too old to edit - not critical

    if new_due is None:
        await message.answer("🚫 Due date removed")
    else:
        await message.answer(f"📅 Rescheduled to {new_due.strftime('%a %d %b %H:%M')}")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_quick_add(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    pending = _pop_valid_pending_reschedule(message.from_user.id)
    if pending is not None:
        await _handle_reschedule_reply(message, client, config, pending)
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
        tasks, _ = await ordered_tasks(client, ctx, config)
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
        await _refresh_list_message(callback, client, ctx, config)
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

    if action == "reschedule":
        try:
            task = await client.get_task(task_id)
        except VikunjaAPIError as exc:
            await callback.answer(f"Error: {exc}", show_alert=True)
            return
        _pending_reschedule[callback.from_user.id] = {
            "task_id": task_id,
            "ctx": ctx,
            "chat_id": callback.message.chat.id,
            "message_id": callback.message.message_id,
            "set_at": time.monotonic(),
        }
        await callback.message.edit_text(
            f"📅 When should '{task['title']}' be due?\n"
            "Reply with a date (e.g. 'tomorrow 5pm', 'next friday'), or tap below.",
            reply_markup=reschedule_prompt_keyboard(task_id, ctx),
        )
        await callback.answer()
        return

    try:
        if action == "done":
            await client.set_done(task_id, True)
        else:
            await client.delete_task(task_id)
        await _refresh_list_message(callback, client, ctx, config)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return

    await callback.answer("Marked done ✅" if action == "done" else "Deleted 🗑")


@router.callback_query(F.data.startswith("resched_clear:"))
async def cb_reschedule_clear(callback: CallbackQuery, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(callback.from_user.id, user_store, cipher, config)
    if client is None:
        await callback.answer("You're not registered.", show_alert=True)
        return

    _, task_id_str, ctx = callback.data.split(":", 2)
    _pending_reschedule.pop(callback.from_user.id, None)
    try:
        await client.set_due_date(int(task_id_str), None)
        await _refresh_list_message(callback, client, ctx, config)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return

    await callback.answer("Due date removed 🚫")


@router.callback_query(F.data.startswith("resched_cancel:"))
async def cb_reschedule_cancel(callback: CallbackQuery, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(callback.from_user.id, user_store, cipher, config)
    if client is None:
        await callback.answer("You're not registered.", show_alert=True)
        return

    _, ctx = callback.data.split(":", 1)
    _pending_reschedule.pop(callback.from_user.id, None)
    try:
        await _refresh_list_message(callback, client, ctx, config)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return

    await callback.answer("Cancelled")


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

import datetime as dt
import html
import time
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import quickadd
from bot.config import Config
from bot.keyboards import (
    cancel_pending_keyboard,
    delete_confirm_keyboard,
    list_menu_keyboard,
    priority_picker_keyboard,
    reschedule_prompt_keyboard,
    task_picker_keyboard,
    task_row_keyboard,
)
from bot.task_view import format_task_list_text, ordered_tasks
from bot.vikunja_client import VikunjaClient

router = Router(name="tasks")

RESCHEDULE_CLEAR_WORDS = {"none", "no date", "remove", "clear"}
PENDING_ACTION_TTL_SECONDS = 600

# In-memory only, keyed by telegram_id: which task/action a user is
# mid-reply on (reschedule or rename - both need a free-text follow-up,
# unlike done/delete/priority which are pure button flows). Lost on
# restart, which is fine - worst case they just tap the button again.
# Bounded by PENDING_ACTION_TTL_SECONDS so an abandoned reply can't
# permanently hijack that user's next quick-add message.
_pending_text_action: dict[int, dict] = {}


def _pop_valid_pending(user_id: int) -> Optional[dict]:
    entry = _pending_text_action.pop(user_id, None)
    if entry is None:
        return None
    if time.monotonic() - entry["set_at"] > PENDING_ACTION_TTL_SECONDS:
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


async def _edit_original_list_message(bot, pending: dict, client: VikunjaClient, config: Config) -> None:
    tasks, titles = await ordered_tasks(client, pending["ctx"], config)
    text = format_task_list_text(tasks, pending["ctx"], titles, config)
    kb = list_menu_keyboard(pending["ctx"]) if tasks else None
    try:
        await bot.edit_message_text(chat_id=pending["chat_id"], message_id=pending["message_id"], text=text, reply_markup=kb)
    except Exception:
        pass  # original list message may be gone/too old to edit - not critical


@router.message(Command("list"))
async def cmd_list(message: Message, command: CommandObject, client: VikunjaClient, config: Config):
    ctx = "a"
    if command.args:
        project = await client.resolve_project(command.args.strip())
        if project is None:
            await message.answer(f"No project matching '{command.args.strip()}'.")
            return
        ctx = f"p{project['id']}"

    await _send_task_list(message, client, ctx, config)


@router.message(Command("today"))
async def cmd_today(message: Message, client: VikunjaClient, config: Config):
    await _send_task_list(message, client, "t", config)


@router.message(Command("week", "this_week"))
async def cmd_week(message: Message, client: VikunjaClient, config: Config):
    await _send_task_list(message, client, "w", config)


async def _handle_reschedule_reply(message: Message, client: VikunjaClient, config: Config, pending: dict) -> None:
    text = message.text.strip()
    is_clear = text.lower() in RESCHEDULE_CLEAR_WORDS
    new_due = None if is_clear else quickadd.parse_date_only(text)

    if new_due is None and not is_clear:
        _pending_text_action[message.from_user.id] = pending  # let them retry
        await message.answer(
            "I couldn't find a date in that. Try again (e.g. 'friday 5pm'), "
            "reply 'none' to remove the due date, or tap Cancel above."
        )
        return

    await client.set_due_date(pending["task_id"], new_due)
    await _edit_original_list_message(message.bot, pending, client, config)

    if new_due is None:
        await message.answer("🚫 Due date removed")
    else:
        await message.answer(f"📅 Rescheduled to {new_due.strftime('%a %d %b %H:%M')}")


async def _handle_rename_reply(message: Message, client: VikunjaClient, config: Config, pending: dict) -> None:
    new_title = message.text.strip()
    if not new_title:
        _pending_text_action[message.from_user.id] = pending  # let them retry
        await message.answer("Title can't be empty. Try again, or tap Cancel above.")
        return

    await client.set_title(pending["task_id"], new_title)
    await _edit_original_list_message(message.bot, pending, client, config)
    await message.answer(f"✏️ Renamed to '{html.escape(new_title)}'")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_quick_add(message: Message, client: VikunjaClient, config: Config):
    pending = _pop_valid_pending(message.from_user.id)
    if pending is not None:
        if pending["kind"] == "reschedule":
            await _handle_reschedule_reply(message, client, config, pending)
        elif pending["kind"] == "rename":
            await _handle_rename_reply(message, client, config, pending)
        return

    result = quickadd.parse(message.text)
    if not result.title:
        await message.answer("I couldn't find a task title in that message.")
        return

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

    due_date = result.due_date
    if result.repeat_mode is not None and due_date is None:
        # Repeat needs an initial due date to repeat from; default to
        # now rather than silently dropping the repeat setting.
        due_date = dt.datetime.now(ZoneInfo(config.timezone))

    task = await client.create_task(
        project["id"],
        result.title,
        due_date=due_date,
        priority=result.priority,
        repeat_after=result.repeat_after,
        repeat_mode=result.repeat_mode,
    )

    for label_name in result.labels:
        label = await client.resolve_label(label_name)
        await client.add_label_to_task(task["id"], label["id"])

    summary = [f"✅ Added: {html.escape(result.title)}", f"Project: {html.escape(project['title'])}"]
    if result.labels:
        summary.append("Labels: " + ", ".join(html.escape(label) for label in result.labels))
    if result.priority:
        summary.append(f"Priority: {result.priority}")
    if due_date:
        summary.append(f"Due: {due_date.strftime('%a %d %b %H:%M')}")
    repeat_desc = quickadd.describe_repeat(result.repeat_after, result.repeat_mode)
    if repeat_desc:
        summary.append(f"Repeats: {repeat_desc}")
    await message.answer("\n".join(summary), reply_markup=task_row_keyboard(task["id"]))


@router.callback_query(F.data.startswith("menu:"))
async def cb_menu(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, action, ctx = callback.data.split(":", 2)
    tasks, _ = await ordered_tasks(client, ctx, config)

    if not tasks:
        await callback.answer("Nothing left to pick.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=task_picker_keyboard(tasks, action, ctx))
    await callback.answer()


@router.callback_query(F.data.startswith("back:"))
async def cb_back(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, ctx = callback.data.split(":", 1)
    await _refresh_list_message(callback, client, ctx, config)
    await callback.answer()


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, action, ctx, task_id_str = callback.data.split(":", 3)
    task_id = int(task_id_str)

    if action == "reschedule":
        task = await client.get_task(task_id)
        _pending_text_action[callback.from_user.id] = {
            "kind": "reschedule",
            "task_id": task_id,
            "ctx": ctx,
            "chat_id": callback.message.chat.id,
            "message_id": callback.message.message_id,
            "set_at": time.monotonic(),
        }
        await callback.message.edit_text(
            f"📅 When should '{html.escape(task['title'])}' be due?\n"
            "Reply with a date (e.g. 'tomorrow 5pm', 'next friday'), or tap below.",
            reply_markup=reschedule_prompt_keyboard(task_id, ctx),
        )
        await callback.answer()
        return

    if action == "priority":
        await callback.message.edit_reply_markup(reply_markup=priority_picker_keyboard(task_id, ctx))
        await callback.answer()
        return

    if action == "rename":
        task = await client.get_task(task_id)
        _pending_text_action[callback.from_user.id] = {
            "kind": "rename",
            "task_id": task_id,
            "ctx": ctx,
            "chat_id": callback.message.chat.id,
            "message_id": callback.message.message_id,
            "set_at": time.monotonic(),
        }
        await callback.message.edit_text(
            f"✏️ Reply with the new title for '{html.escape(task['title'])}'.",
            reply_markup=cancel_pending_keyboard(ctx),
        )
        await callback.answer()
        return

    if action == "delete":
        task = await client.get_task(task_id)
        await callback.message.edit_text(
            f"🗑 Delete '{html.escape(task['title'])}'? This can't be undone.",
            reply_markup=delete_confirm_keyboard(task_id, ctx),
        )
        await callback.answer()
        return

    # action == "done"
    await client.set_done(task_id, True)
    await _refresh_list_message(callback, client, ctx, config)
    await callback.answer("Marked done ✅")


@router.callback_query(F.data.startswith("delconfirm:"))
async def cb_delete_confirm(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, task_id_str, ctx = callback.data.split(":", 2)
    await client.delete_task(int(task_id_str))
    await _refresh_list_message(callback, client, ctx, config)
    await callback.answer("Deleted 🗑")


@router.callback_query(F.data.startswith("setprio:"))
async def cb_set_priority(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, value_str, task_id_str, ctx = callback.data.split(":", 3)
    await client.set_priority(int(task_id_str), int(value_str))
    await _refresh_list_message(callback, client, ctx, config)
    await callback.answer("Priority updated")


@router.callback_query(F.data.startswith("resched_clear:"))
async def cb_reschedule_clear(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, task_id_str, ctx = callback.data.split(":", 2)
    _pending_text_action.pop(callback.from_user.id, None)
    await client.set_due_date(int(task_id_str), None)
    await _refresh_list_message(callback, client, ctx, config)
    await callback.answer("Due date removed 🚫")


@router.callback_query(F.data.startswith("resched_snooze:"))
async def cb_reschedule_snooze(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, task_id_str, ctx, days_str = callback.data.split(":", 3)
    _pending_text_action.pop(callback.from_user.id, None)
    # Relative to now, not the task's current due date - snoozing an
    # already-overdue task should land it clearly in the future, not just
    # nudge a stale due date by a day and leave it still overdue. Tasks
    # reach this button via a list that's already filtered to due/overdue,
    # so "now + N" is virtually always what's meant in practice.
    new_due = dt.datetime.now(ZoneInfo(config.timezone)) + dt.timedelta(days=int(days_str))
    await client.set_due_date(int(task_id_str), new_due)
    await _refresh_list_message(callback, client, ctx, config)
    await callback.answer(f"😴 Snoozed to {new_due.strftime('%a %d %b')}")


@router.callback_query(F.data.startswith("pending_cancel:"))
async def cb_pending_cancel(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, ctx = callback.data.split(":", 1)
    _pending_text_action.pop(callback.from_user.id, None)
    await _refresh_list_message(callback, client, ctx, config)
    await callback.answer("Cancelled")


@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: CallbackQuery, client: VikunjaClient, config: Config):
    task_id = int(callback.data.split(":", 1)[1])
    await client.set_done(task_id, True)
    await callback.message.edit_text(f"{callback.message.text}\n✅ marked done")
    await callback.answer("Marked done")


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery, client: VikunjaClient, config: Config):
    task_id = int(callback.data.split(":", 1)[1])
    await client.delete_task(task_id)
    await callback.message.edit_text(f"{callback.message.text}\n🗑 deleted")
    await callback.answer("Deleted")

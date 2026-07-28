import datetime as dt
import html
import time
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import i18n, quickadd
from bot.config import Config
from bot.db import UserStore
from bot.keyboards import (
    cancel_pending_keyboard,
    delete_confirm_keyboard,
    list_menu_keyboard,
    priority_picker_keyboard,
    reschedule_prompt_keyboard,
    task_picker_keyboard,
    task_row_keyboard,
)
from bot.task_view import format_task_list_text, ordered_tasks, resolve_personal_project_id
from bot.vikunja_client import VikunjaClient

router = Router(name="tasks")

RESCHEDULE_CLEAR_WORDS = {"none", "no date", "remove", "clear", "cap", "sense data", "elimina", "esborra"}
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


async def _personal_scope(
    client: VikunjaClient, user_store: UserStore, telegram_id: int, chat_type: str, ctx: str
) -> tuple[Optional[int], bool]:
    """(personal_project_id, only_personal) for the "a"/"t"/"w" aggregate
    views: a DM narrows down to just the caller's own personal project, a
    group chat excludes it instead, showing the shared/common projects -
    see task_view.get_tasks_for_ctx. An explicit single-project view (ctx
    starting with "p") is left untouched, same precedent as quick-add's
    +project always overriding its DM/group default. Doesn't create the
    personal project if missing (unlike quick-add's default-project
    resolution) - a read-only list shouldn't have the side effect of
    creating a project; personal_project_id just comes back None and
    filtering becomes a no-op, same as before this feature existed."""
    if ctx not in ("a", "t", "w"):
        return None, False
    user = await user_store.get_user(telegram_id)
    if user is None:
        return None, False
    personal_project_id = await resolve_personal_project_id(client, user.display_name)
    return personal_project_id, chat_type == "private"


async def _send_task_list(message: Message, client: VikunjaClient, user_store: UserStore, ctx: str, config: Config):
    personal_project_id, only_personal = await _personal_scope(
        client, user_store, message.from_user.id, message.chat.type, ctx
    )
    tasks, titles = await ordered_tasks(client, ctx, config, personal_project_id, only_personal)
    text = format_task_list_text(tasks, ctx, titles, config)
    kb = list_menu_keyboard(ctx) if tasks else None
    await message.answer(text, reply_markup=kb)


async def _refresh_list_message(
    callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, ctx: str, config: Config
) -> None:
    personal_project_id, only_personal = await _personal_scope(
        client, user_store, callback.from_user.id, callback.message.chat.type, ctx
    )
    tasks, titles = await ordered_tasks(client, ctx, config, personal_project_id, only_personal)
    text = format_task_list_text(tasks, ctx, titles, config)
    kb = list_menu_keyboard(ctx) if tasks else None
    await callback.message.edit_text(text, reply_markup=kb)


async def _edit_original_list_message(
    message: Message, pending: dict, client: VikunjaClient, user_store: UserStore, config: Config
) -> None:
    # message is the incoming text reply (reschedule/rename), sent in the
    # same chat as the list message being refreshed - its chat.type is
    # therefore also the original list's, so no need to have stashed it in
    # `pending` separately.
    personal_project_id, only_personal = await _personal_scope(
        client, user_store, message.from_user.id, message.chat.type, pending["ctx"]
    )
    tasks, titles = await ordered_tasks(client, pending["ctx"], config, personal_project_id, only_personal)
    text = format_task_list_text(tasks, pending["ctx"], titles, config)
    kb = list_menu_keyboard(pending["ctx"]) if tasks else None
    try:
        await message.bot.edit_message_text(
            chat_id=pending["chat_id"], message_id=pending["message_id"], text=text, reply_markup=kb
        )
    except Exception:
        pass  # original list message may be gone/too old to edit - not critical


@router.message(Command("list", "llista"))
async def cmd_list(message: Message, command: CommandObject, client: VikunjaClient, user_store: UserStore, config: Config):
    ctx = "a"
    if command.args:
        project = await client.resolve_project(command.args.strip())
        if project is None:
            await message.answer(i18n.t("list_no_project", name=command.args.strip()))
            return
        ctx = f"p{project['id']}"

    await _send_task_list(message, client, user_store, ctx, config)


@router.message(Command("today", "avui"))
async def cmd_today(message: Message, client: VikunjaClient, user_store: UserStore, config: Config):
    await _send_task_list(message, client, user_store, "t", config)


@router.message(Command("week", "this_week", "setmana"))
async def cmd_week(message: Message, client: VikunjaClient, user_store: UserStore, config: Config):
    await _send_task_list(message, client, user_store, "w", config)


async def _handle_reschedule_reply(
    message: Message, client: VikunjaClient, user_store: UserStore, config: Config, pending: dict
) -> None:
    text = message.text.strip()
    is_clear = text.lower() in RESCHEDULE_CLEAR_WORDS
    new_due = None if is_clear else quickadd.parse_date_only(text)

    if new_due is None and not is_clear:
        _pending_text_action[message.from_user.id] = pending  # let them retry
        await message.answer(i18n.t("reschedule_no_date_found"))
        return

    await client.set_due_date(pending["task_id"], new_due)
    await _edit_original_list_message(message, pending, client, user_store, config)

    if new_due is None:
        await message.answer(i18n.t("due_date_removed"))
    else:
        await message.answer(i18n.t("rescheduled_to", date=i18n.fmt_datetime(new_due)))


async def _handle_rename_reply(
    message: Message, client: VikunjaClient, user_store: UserStore, config: Config, pending: dict
) -> None:
    new_title = message.text.strip()
    if not new_title:
        _pending_text_action[message.from_user.id] = pending  # let them retry
        await message.answer(i18n.t("rename_empty"))
        return

    await client.set_title(pending["task_id"], new_title)
    await _edit_original_list_message(message, pending, client, user_store, config)
    await message.answer(i18n.t("renamed_to", title=html.escape(new_title)))


async def _resolve_context_default_project(
    message: Message, client: VikunjaClient, user_store: UserStore, config: Config
) -> Optional[dict]:
    """The project a quick-add with no explicit +project should land in,
    based on where the message came from - a DM is one person adding
    something just for themselves, a group is the shared household chat.

    A DM's personal project (named after the sender's registered
    display_name) gets created on first use if it doesn't exist yet,
    rather than silently falling back to DEFAULT_PROJECT_NAME - unlike the
    shared DAILY_PROJECT_NAME, which the household is expected to already
    have set up, a personal project has no other setup step to create it.
    Falls through to config.default_project_name (checked by the caller) if
    DAILY_PROJECT_NAME itself doesn't exist in Vikunja for the group case.
    """
    if message.chat.type == "private":
        user = await user_store.get_user(message.from_user.id)
        if user is None:
            return None
        project = await client.resolve_project(user.display_name)
        if project is None:
            project = await client.create_project(user.display_name)
        return project
    return await client.resolve_project(config.daily_project_name)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_quick_add(message: Message, client: VikunjaClient, user_store: UserStore, config: Config):
    pending = _pop_valid_pending(message.from_user.id)
    if pending is not None:
        if pending["kind"] == "reschedule":
            await _handle_reschedule_reply(message, client, user_store, config, pending)
        elif pending["kind"] == "rename":
            await _handle_rename_reply(message, client, user_store, config, pending)
        return

    result = quickadd.parse(message.text)
    if not result.title:
        await message.answer(i18n.t("no_title_found"))
        return

    project = None
    if result.project:
        project = await client.resolve_project(result.project)
        if project is None:
            await message.answer(i18n.t("project_fallback", project=result.project))
    if project is None:
        project = await _resolve_context_default_project(message, client, user_store, config)
    if project is None:
        project = await client.resolve_project(config.default_project_name)
    if project is None:
        projects = await client.list_projects()
        if not projects:
            await message.answer(i18n.t("no_projects_yet"))
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

    summary = [
        i18n.t("summary_added", title=html.escape(result.title)),
        i18n.t("summary_project", title=html.escape(project["title"])),
    ]
    if result.labels:
        summary.append(i18n.t("summary_labels", labels=", ".join(html.escape(label) for label in result.labels)))
    if result.priority:
        summary.append(i18n.t("summary_priority", value=result.priority))
    if due_date:
        summary.append(i18n.t("summary_due", date=i18n.fmt_datetime(due_date)))
    repeat_desc = quickadd.describe_repeat(result.repeat_after, result.repeat_mode)
    if repeat_desc:
        summary.append(i18n.t("summary_repeats", desc=i18n.repeat_desc(repeat_desc)))
    await message.answer("\n".join(summary), reply_markup=task_row_keyboard(task["id"]))


@router.callback_query(F.data.startswith("menu:"))
async def cb_menu(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
    _, action, ctx = callback.data.split(":", 2)
    personal_project_id, only_personal = await _personal_scope(
        client, user_store, callback.from_user.id, callback.message.chat.type, ctx
    )
    tasks, _ = await ordered_tasks(client, ctx, config, personal_project_id, only_personal)

    if not tasks:
        await callback.answer(i18n.t("nothing_left_to_pick"), show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=task_picker_keyboard(tasks, action, ctx))
    await callback.answer()


@router.callback_query(F.data.startswith("back:"))
async def cb_back(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
    _, ctx = callback.data.split(":", 1)
    await _refresh_list_message(callback, client, user_store, ctx, config)
    await callback.answer()


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
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
            i18n.t("reschedule_prompt", title=html.escape(task["title"])),
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
            i18n.t("rename_prompt", title=html.escape(task["title"])),
            reply_markup=cancel_pending_keyboard(ctx),
        )
        await callback.answer()
        return

    if action == "delete":
        task = await client.get_task(task_id)
        await callback.message.edit_text(
            i18n.t("delete_confirm_prompt", title=html.escape(task["title"])),
            reply_markup=delete_confirm_keyboard(task_id, ctx),
        )
        await callback.answer()
        return

    # action == "done"
    await client.set_done(task_id, True)
    await _refresh_list_message(callback, client, user_store, ctx, config)
    await callback.answer(i18n.t("marked_done_full"))


@router.callback_query(F.data.startswith("delconfirm:"))
async def cb_delete_confirm(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
    _, task_id_str, ctx = callback.data.split(":", 2)
    await client.delete_task(int(task_id_str))
    await _refresh_list_message(callback, client, user_store, ctx, config)
    await callback.answer(i18n.t("deleted_full"))


@router.callback_query(F.data.startswith("setprio:"))
async def cb_set_priority(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
    _, value_str, task_id_str, ctx = callback.data.split(":", 3)
    await client.set_priority(int(task_id_str), int(value_str))
    await _refresh_list_message(callback, client, user_store, ctx, config)
    await callback.answer(i18n.t("priority_updated"))


@router.callback_query(F.data.startswith("resched_clear:"))
async def cb_reschedule_clear(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
    _, task_id_str, ctx = callback.data.split(":", 2)
    _pending_text_action.pop(callback.from_user.id, None)
    await client.set_due_date(int(task_id_str), None)
    await _refresh_list_message(callback, client, user_store, ctx, config)
    await callback.answer(i18n.t("due_date_removed_short"))


@router.callback_query(F.data.startswith("resched_snooze:"))
async def cb_reschedule_snooze(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
    _, task_id_str, ctx, days_str = callback.data.split(":", 3)
    _pending_text_action.pop(callback.from_user.id, None)
    # Relative to now, not the task's current due date - snoozing an
    # already-overdue task should land it clearly in the future, not just
    # nudge a stale due date by a day and leave it still overdue. Tasks
    # reach this button via a list that's already filtered to due/overdue,
    # so "now + N" is virtually always what's meant in practice.
    new_due = dt.datetime.now(ZoneInfo(config.timezone)) + dt.timedelta(days=int(days_str))
    await client.set_due_date(int(task_id_str), new_due)
    await _refresh_list_message(callback, client, user_store, ctx, config)
    await callback.answer(i18n.t("snoozed_to", date=i18n.fmt_date(new_due)))


@router.callback_query(F.data.startswith("pending_cancel:"))
async def cb_pending_cancel(callback: CallbackQuery, client: VikunjaClient, user_store: UserStore, config: Config):
    _, ctx = callback.data.split(":", 1)
    _pending_text_action.pop(callback.from_user.id, None)
    await _refresh_list_message(callback, client, user_store, ctx, config)
    await callback.answer(i18n.t("cancelled"))


@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: CallbackQuery, client: VikunjaClient, config: Config):
    task_id = int(callback.data.split(":", 1)[1])
    await client.set_done(task_id, True)
    await callback.message.edit_text(f"{callback.message.text}\n{i18n.t('marked_done_suffix')}")
    await callback.answer(i18n.t("marked_done_short"))


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery, client: VikunjaClient, config: Config):
    task_id = int(callback.data.split(":", 1)[1])
    await client.delete_task(task_id)
    await callback.message.edit_text(f"{callback.message.text}\n{i18n.t('deleted_suffix')}")
    await callback.answer(i18n.t("deleted_short"))

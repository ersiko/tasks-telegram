import asyncio
import datetime as dt
import html
import logging
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.access import get_client_for_user
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.keyboards import list_menu_keyboard
from bot.pause_store import PauseStore
from bot.task_view import (
    format_task_list_text,
    get_completed_between,
    has_tasks_due_between,
    ordered_tasks,
    parse_due_date,
    week_end,
    week_start,
)
from bot.vikunja_client import VikunjaAPIError

logger = logging.getLogger(__name__)

DIGEST_HEADER = "☀️ Good morning! Due today or overdue:\n\n"


def next_run_at(now: dt.datetime, hour: int, minute: int) -> dt.datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(days=1)
    return candidate


async def _merged_today_tasks(
    user_store: UserStore, cipher: TokenCipher, config: Config
) -> tuple[list[dict], Optional[dict[int, str]]]:
    """Today-or-overdue tasks across every registered account, deduplicated
    by task ID. Separate Vikunja accounts sharing the same projects would
    otherwise each report the same tasks - merge rather than picking one
    account arbitrarily, since either person's account should see the full
    household list in the group digest."""
    seen_ids: set[int] = set()
    merged: list[dict] = []
    titles: dict[int, str] = {}

    for telegram_id, display_name in await user_store.list_users():
        client = await get_client_for_user(telegram_id, user_store, cipher, config)
        if client is None:
            continue
        async with client:
            try:
                tasks, user_titles = await ordered_tasks(client, "t", config)
            except VikunjaAPIError:
                logger.exception("Failed to fetch digest tasks for %s (%s)", display_name, telegram_id)
                continue
        if user_titles:
            titles.update(user_titles)
        for task in tasks:
            if task["id"] not in seen_ids:
                seen_ids.add(task["id"])
                merged.append(task)

    if not merged:
        return [], None
    if titles:
        merged.sort(key=lambda t: titles.get(t.get("project_id"), "").lower())
    return merged, titles or None


async def merged_completed_between(
    user_store: UserStore, cipher: TokenCipher, config: Config, start: dt.datetime, end: dt.datetime
) -> list[dict]:
    """Tasks completed within [start, end] across every registered account,
    deduplicated by task ID (same rationale as _merged_today_tasks) -
    used by both the weekly/monthly recap sections and /recap."""
    seen_ids: set[int] = set()
    merged: list[tuple[str, dict]] = []

    for telegram_id, display_name in await user_store.list_users():
        client = await get_client_for_user(telegram_id, user_store, cipher, config)
        if client is None:
            continue
        async with client:
            try:
                tasks = await get_completed_between(client, start, end)
            except VikunjaAPIError:
                logger.exception("Failed to fetch completed tasks for %s (%s)", display_name, telegram_id)
                continue
        for task in tasks:
            if task["id"] not in seen_ids:
                seen_ids.add(task["id"])
                merged.append((task.get("done_at") or "", task))

    merged.sort(key=lambda pair: pair[0])  # ISO8601 strings sort chronologically
    return [task for _, task in merged]


async def _new_week_has_plan(
    user_store: UserStore, cipher: TokenCipher, config: Config, now_local: dt.datetime
) -> bool:
    """Whether WEEKLY_PROJECT_NAME already has something due in the week
    starting now_local - used to decide whether to nudge toward /plan_week.
    Checked via the admin's account as a representative view; if it can't
    be checked, don't nudge on uncertain data."""
    client = await get_client_for_user(config.admin_telegram_id, user_store, cipher, config)
    if client is None:
        return True
    async with client:
        try:
            project = await client.resolve_project(config.weekly_project_name)
            if project is None:
                return True
            start = week_start(config, now_local)
            end = week_end(config, now_local)
            return await has_tasks_due_between(client, project["id"], start, end)
        except VikunjaAPIError:
            logger.exception("Failed to check whether the new week already has a plan")
            return True


async def catch_up_daily_tasks(
    user_store: UserStore, cipher: TokenCipher, config: Config, now: dt.datetime
) -> int:
    """When a pause ends (either kind - see bot/handlers/pause.py), push any
    open DAILY_PROJECT_NAME task due at or before `now` to be due exactly
    `now` instead. Coming back from being away shouldn't mean an immediate
    overdue-escalation pile-up for chores that simply couldn't happen while
    paused - and tasks due after the pause ends are left alone, since the
    pause never affected them. Uses the admin's account as a representative
    view of the shared project, same reasoning as _new_week_has_plan:
    avoids processing (and double-shifting) the same shared tasks once per
    registered account. Returns how many tasks were shifted."""
    client = await get_client_for_user(config.admin_telegram_id, user_store, cipher, config)
    if client is None:
        return 0

    shifted = 0
    async with client:
        try:
            project = await client.resolve_project(config.daily_project_name)
            if project is None:
                logger.warning(
                    "DAILY_PROJECT_NAME %r not found - nothing to catch up", config.daily_project_name
                )
                return 0
            tasks = await client.list_tasks(project_id=project["id"])
            for task in tasks:
                due = parse_due_date(task.get("due_date"))
                if due is not None and due <= now:
                    await client.set_due_date(task["id"], now)
                    shifted += 1
        except VikunjaAPIError:
            logger.exception("Failed to catch up daily tasks after pause")
    return shifted


async def _weekly_wrapup_section(
    user_store: UserStore, cipher: TokenCipher, config: Config, now_local: dt.datetime
) -> str:
    this_week_start = week_start(config, now_local)
    last_week_start = this_week_start - dt.timedelta(days=7)
    last_week_end = this_week_start - dt.timedelta(seconds=1)

    completed = await merged_completed_between(user_store, cipher, config, last_week_start, last_week_end)
    lines = ["📊 Last week you completed:"]
    if completed:
        lines += [f"• {html.escape(t['title'])}" for t in completed[:20]]
    else:
        lines.append("Nothing marked done — a quiet week.")

    if not await _new_week_has_plan(user_store, cipher, config, now_local):
        lines += ["", "📋 Nothing planned for this week yet — try /plan_week."]

    return "\n".join(lines)


def _previous_month_range(now_local: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    this_month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if this_month_start.month == 1:
        last_month_start = this_month_start.replace(year=this_month_start.year - 1, month=12)
    else:
        last_month_start = this_month_start.replace(month=this_month_start.month - 1)
    last_month_end = this_month_start - dt.timedelta(seconds=1)
    return last_month_start, last_month_end


async def _monthly_recap_section(
    user_store: UserStore, cipher: TokenCipher, config: Config, now_local: dt.datetime
) -> str:
    start, end = _previous_month_range(now_local)
    completed = await merged_completed_between(user_store, cipher, config, start, end)
    lines = [f"📅 In {start.strftime('%B')} you completed:"]
    if completed:
        lines += [f"• {html.escape(t['title'])}" for t in completed[:30]]
    else:
        lines.append("Nothing marked done that month.")
    return "\n".join(lines)


async def send_digests(bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config, now: dt.datetime) -> None:
    if config.digest_chat_id is not None:
        await _send_group_digest(bot, user_store, cipher, config, now)
    else:
        await _send_individual_digests(bot, user_store, cipher, config)


async def _send_group_digest(
    bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config, now: dt.datetime
) -> None:
    tasks, titles = await _merged_today_tasks(user_store, cipher, config)

    parts = []
    if tasks:
        parts.append(DIGEST_HEADER + format_task_list_text(tasks, "t", titles, config))
    if now.isoweekday() == config.week_start_day:
        parts.append(await _weekly_wrapup_section(user_store, cipher, config, now))
    if now.day == 1:
        parts.append(await _monthly_recap_section(user_store, cipher, config, now))

    if not parts:
        return

    text = "\n\n".join(parts)
    try:
        await bot.send_message(
            config.digest_chat_id, text, reply_markup=list_menu_keyboard("t") if tasks else None
        )
    except Exception:
        logger.exception("Failed to send morning digest to group chat %s", config.digest_chat_id)


async def _send_individual_digests(bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config) -> None:
    for telegram_id, display_name in await user_store.list_users():
        client = await get_client_for_user(telegram_id, user_store, cipher, config)
        if client is None:
            continue
        async with client:
            try:
                tasks, titles = await ordered_tasks(client, "t", config)
            except VikunjaAPIError:
                logger.exception("Failed to fetch morning digest tasks for %s (%s)", display_name, telegram_id)
                continue
        if not tasks:
            continue

        text = DIGEST_HEADER + format_task_list_text(tasks, "t", titles, config)
        try:
            await bot.send_message(telegram_id, text, reply_markup=list_menu_keyboard("t"))
        except Exception:
            logger.exception("Failed to send morning digest to %s (%s)", display_name, telegram_id)


async def run_digest_loop(
    bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config, pause_store: PauseStore
) -> None:
    tz = ZoneInfo(config.timezone)
    hour, minute = (int(part) for part in config.digest_time.split(":"))

    while True:
        now = dt.datetime.now(tz)
        target = next_run_at(now, hour, minute)
        sleep_seconds = (target - now).total_seconds()
        logger.info("Next morning digest at %s (in %.0f min)", target.isoformat(), sleep_seconds / 60)
        await asyncio.sleep(sleep_seconds)
        try:
            if await pause_store.check_and_clear_if_expired(target):
                shifted = await catch_up_daily_tasks(user_store, cipher, config, target)
                logger.info("Timed pause ended, caught up %d daily task(s)", shifted)
            elif await pause_store.is_paused(target):
                logger.info("Digest paused, skipping")
                continue
            await send_digests(bot, user_store, cipher, config, target)
        except Exception:
            logger.exception("Morning digest run failed")

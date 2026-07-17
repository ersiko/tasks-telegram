import asyncio
import datetime as dt
import logging
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.access import get_client_for_user
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.keyboards import list_menu_keyboard
from bot.task_view import format_task_list_text, ordered_tasks
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


async def send_digests(bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config) -> None:
    if config.digest_chat_id is not None:
        await _send_group_digest(bot, user_store, cipher, config)
    else:
        await _send_individual_digests(bot, user_store, cipher, config)


async def _send_group_digest(bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config) -> None:
    tasks, titles = await _merged_today_tasks(user_store, cipher, config)
    if not tasks:
        return
    text = DIGEST_HEADER + format_task_list_text(tasks, "t", titles, config)
    try:
        await bot.send_message(config.digest_chat_id, text, reply_markup=list_menu_keyboard("t"))
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


async def run_digest_loop(bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config) -> None:
    tz = ZoneInfo(config.timezone)
    hour, minute = (int(part) for part in config.digest_time.split(":"))

    while True:
        now = dt.datetime.now(tz)
        target = next_run_at(now, hour, minute)
        sleep_seconds = (target - now).total_seconds()
        logger.info("Next morning digest at %s (in %.0f min)", target.isoformat(), sleep_seconds / 60)
        await asyncio.sleep(sleep_seconds)
        try:
            await send_digests(bot, user_store, cipher, config)
        except Exception:
            logger.exception("Morning digest run failed")

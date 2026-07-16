import asyncio
import datetime as dt
import logging
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


def next_run_at(now: dt.datetime, hour: int, minute: int) -> dt.datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(days=1)
    return candidate


async def send_digests(bot: Bot, user_store: UserStore, cipher: TokenCipher, config: Config) -> None:
    for telegram_id, display_name in await user_store.list_users():
        client = await get_client_for_user(telegram_id, user_store, cipher, config)
        if client is None:
            continue
        try:
            tasks, titles = await ordered_tasks(client, "t", config)
        except VikunjaAPIError:
            logger.exception("Failed to fetch morning digest tasks for %s (%s)", display_name, telegram_id)
            continue
        if not tasks:
            continue

        text = "☀️ Good morning! Due today or overdue:\n\n" + format_task_list_text(tasks, "t", titles, config)
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

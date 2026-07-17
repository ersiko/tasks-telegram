import datetime as dt
import html
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.digest import merged_completed_between
from bot.task_view import week_start

router = Router(name="recap")


@router.message(Command("recap"))
async def cmd_recap(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    # Registration-gated like any other command, but doesn't go through
    # VikunjaClientMiddleware - it merges every registered account's
    # completions rather than acting on just the caller's, same as the
    # scheduled weekly/monthly recap sections in bot/digest.py.
    if await user_store.get_user(message.from_user.id) is None:
        await message.answer(
            f"You're not registered yet. Your Telegram ID is `{message.from_user.id}`.",
            parse_mode="Markdown",
        )
        return

    now = dt.datetime.now(ZoneInfo(config.timezone))
    start = week_start(config, now)
    completed = await merged_completed_between(user_store, cipher, config, start, now)
    if not completed:
        await message.answer("Nothing completed so far this week.")
        return

    lines = [f"📊 Completed since {start.strftime('%a %d %b')}:"]
    lines += [f"• {html.escape(t['title'])}" for t in completed[:20]]
    await message.answer("\n".join(lines))

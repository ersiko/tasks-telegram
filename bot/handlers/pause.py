import datetime as dt
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import Config
from bot.db import UserStore
from bot.pause_store import PauseStore

router = Router(name="pause")


async def _require_registered(message: Message, user_store: UserStore) -> bool:
    if await user_store.get_user(message.from_user.id) is None:
        await message.answer(
            f"You're not registered yet. Your Telegram ID is `{message.from_user.id}`.",
            parse_mode="Markdown",
        )
        return False
    return True


@router.message(Command("pause"))
async def cmd_pause(
    message: Message, command: CommandObject, user_store: UserStore, pause_store: PauseStore, config: Config
):
    if not await _require_registered(message, user_store):
        return

    resume_at = None
    if command.args:
        try:
            days = int(command.args.strip())
        except ValueError:
            await message.answer(
                "Usage: /pause [days] - e.g. /pause 7 to auto-resume in a week, "
                "or /pause with no number to pause until you run /resume."
            )
            return
        if days <= 0:
            await message.answer("Days must be a positive number.")
            return
        now = dt.datetime.now(ZoneInfo(config.timezone))
        resume_at = now + dt.timedelta(days=days)

    await pause_store.pause(resume_at)
    if resume_at is not None:
        await message.answer(
            f"⏸ Digest paused until {resume_at.strftime('%a %d %b')}. Run /resume to lift it early."
        )
    else:
        await message.answer("⏸ Digest paused indefinitely. Run /resume when you're back.")


@router.message(Command("resume"))
async def cmd_resume(message: Message, user_store: UserStore, pause_store: PauseStore):
    if not await _require_registered(message, user_store):
        return
    await pause_store.resume()
    await message.answer("▶️ Digest resumed.")

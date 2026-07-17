import datetime as dt
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.digest import catch_up_daily_tasks
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
    catch_up_note = (
        f" Any {config.daily_project_name} task due while paused will be pushed to when you're back."
    )
    if resume_at is not None:
        await message.answer(
            f"⏸ Digest paused until {resume_at.strftime('%a %d %b')}. Run /resume to lift it early."
            + catch_up_note
        )
    else:
        await message.answer("⏸ Digest paused indefinitely. Run /resume when you're back." + catch_up_note)


@router.message(Command("resume"))
async def cmd_resume(
    message: Message, user_store: UserStore, cipher: TokenCipher, pause_store: PauseStore, config: Config
):
    if not await _require_registered(message, user_store):
        return

    was_paused = await pause_store.is_paused()
    await pause_store.resume()

    if not was_paused:
        await message.answer("▶️ Digest resumed.")
        return

    now = dt.datetime.now(ZoneInfo(config.timezone))
    shifted = await catch_up_daily_tasks(user_store, cipher, config, now)
    if shifted:
        await message.answer(
            f"▶️ Digest resumed. Pushed {shifted} {config.daily_project_name} task(s) that were "
            "due while paused to today."
        )
    else:
        await message.answer("▶️ Digest resumed.")

import datetime as dt
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import i18n
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.digest import catch_up_daily_tasks
from bot.pause_store import PauseStore

router = Router(name="pause")


async def _require_registered(message: Message, user_store: UserStore) -> bool:
    if await user_store.get_user(message.from_user.id) is None:
        await message.answer(
            i18n.t("not_registered_short", user_id=message.from_user.id),
            parse_mode="Markdown",
        )
        return False
    return True


@router.message(Command("pause", "pausa"))
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
            await message.answer(i18n.t("pause_usage"))
            return
        if days <= 0:
            await message.answer(i18n.t("days_must_be_positive"))
            return
        now = dt.datetime.now(ZoneInfo(config.timezone))
        resume_at = now + dt.timedelta(days=days)

    await pause_store.pause(resume_at)
    catch_up_note = i18n.t("pause_catch_up_note", project=config.daily_project_name)
    if resume_at is not None:
        await message.answer(i18n.t("paused_until", date=i18n.fmt_date(resume_at)) + catch_up_note)
    else:
        await message.answer(i18n.t("paused_indefinite") + catch_up_note)


@router.message(Command("resume", "repren"))
async def cmd_resume(
    message: Message, user_store: UserStore, cipher: TokenCipher, pause_store: PauseStore, config: Config
):
    if not await _require_registered(message, user_store):
        return

    was_paused = await pause_store.is_paused()
    await pause_store.resume()

    if not was_paused:
        await message.answer(i18n.t("resumed"))
        return

    now = dt.datetime.now(ZoneInfo(config.timezone))
    shifted = await catch_up_daily_tasks(user_store, cipher, config, now)
    if shifted:
        await message.answer(i18n.t("resumed_with_catchup", count=shifted, project=config.daily_project_name))
    else:
        await message.answer(i18n.t("resumed"))

import html

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import i18n
from bot.db import UserStore

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message, user_store: UserStore):
    user = await user_store.get_user(message.from_user.id)
    if user is None:
        await message.answer(
            i18n.t("start_not_registered", user_id=message.from_user.id),
            parse_mode="Markdown",
        )
        return
    await message.answer(i18n.t("greeting", name=html.escape(user.display_name)) + i18n.t("help_text"))


@router.message(Command("help", "ajuda"))
async def cmd_help(message: Message, user_store: UserStore):
    user = await user_store.get_user(message.from_user.id)
    if user is None:
        await message.answer(
            i18n.t("not_registered_short", user_id=message.from_user.id),
            parse_mode="Markdown",
        )
        return
    await message.answer(i18n.t("help_text"))


@router.message(Command("chatid", "id_xat"))
async def cmd_chatid(message: Message):
    # No registration/auth needed - just a setup utility, e.g. to find a
    # group's chat ID for DIGEST_CHAT_ID after adding the bot to it.
    await message.answer(i18n.t("chatid_message", chat_id=message.chat.id), parse_mode="Markdown")

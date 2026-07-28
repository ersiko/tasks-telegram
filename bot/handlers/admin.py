import html

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import i18n
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore

router = Router(name="admin")


def _is_admin(message: Message, config: Config) -> bool:
    return message.from_user.id == config.admin_telegram_id


@router.message(Command("adduser", "afegeix_usuari"))
async def cmd_adduser(
    message: Message, command: CommandObject, user_store: UserStore, cipher: TokenCipher, config: Config
):
    if not _is_admin(message, config):
        return
    if message.chat.type != "private":
        await message.answer(i18n.t("adduser_group_warning"))
        return
    if not command.args:
        await message.answer(i18n.t("adduser_usage"))
        return

    parts = command.args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(i18n.t("adduser_usage"))
        return

    try:
        telegram_id = int(parts[0])
    except ValueError:
        await message.answer(i18n.t("telegram_id_not_a_number"))
        return

    token = parts[1]
    display_name = parts[2] if len(parts) > 2 else str(telegram_id)

    await user_store.add_user(telegram_id, cipher.encrypt(token), display_name)
    await message.answer(i18n.t("adduser_success", name=html.escape(display_name), id=telegram_id))


@router.message(Command("removeuser", "elimina_usuari"))
async def cmd_removeuser(message: Message, command: CommandObject, user_store: UserStore, config: Config):
    if not _is_admin(message, config):
        return
    if not command.args:
        await message.answer(i18n.t("removeuser_usage"))
        return

    try:
        telegram_id = int(command.args.strip())
    except ValueError:
        await message.answer(i18n.t("telegram_id_not_a_number"))
        return

    removed = await user_store.remove_user(telegram_id)
    await message.answer(i18n.t("removed") if removed else i18n.t("no_such_user"))


@router.message(Command("users", "usuaris"))
async def cmd_users(message: Message, user_store: UserStore, config: Config):
    if not _is_admin(message, config):
        return

    users = await user_store.list_users()
    if not users:
        await message.answer(i18n.t("no_users_registered"))
        return

    await message.answer("\n".join(f"• {html.escape(name)} ({telegram_id})" for telegram_id, name in users))

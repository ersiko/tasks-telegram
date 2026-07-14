from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore

router = Router(name="admin")


def _is_admin(message: Message, config: Config) -> bool:
    return message.from_user.id == config.admin_telegram_id


@router.message(Command("adduser"))
async def cmd_adduser(
    message: Message, command: CommandObject, user_store: UserStore, cipher: TokenCipher, config: Config
):
    if not _is_admin(message, config):
        return
    if not command.args:
        await message.answer("Usage: /adduser <telegram_id> <vikunja_api_token> [display name]")
        return

    parts = command.args.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /adduser <telegram_id> <vikunja_api_token> [display name]")
        return

    try:
        telegram_id = int(parts[0])
    except ValueError:
        await message.answer("telegram_id must be a number.")
        return

    token = parts[1]
    display_name = parts[2] if len(parts) > 2 else str(telegram_id)

    await user_store.add_user(telegram_id, cipher.encrypt(token), display_name)
    await message.answer(
        f"Registered {display_name} ({telegram_id}).\n"
        "Please delete your message above now — I can't delete it for you in a private chat, "
        "and it contains their API token in plaintext."
    )


@router.message(Command("removeuser"))
async def cmd_removeuser(message: Message, command: CommandObject, user_store: UserStore, config: Config):
    if not _is_admin(message, config):
        return
    if not command.args:
        await message.answer("Usage: /removeuser <telegram_id>")
        return

    try:
        telegram_id = int(command.args.strip())
    except ValueError:
        await message.answer("telegram_id must be a number.")
        return

    removed = await user_store.remove_user(telegram_id)
    await message.answer("Removed." if removed else "No such user.")


@router.message(Command("users"))
async def cmd_users(message: Message, user_store: UserStore, config: Config):
    if not _is_admin(message, config):
        return

    users = await user_store.list_users()
    if not users:
        await message.answer("No users registered.")
        return

    await message.answer("\n".join(f"• {name} ({telegram_id})" for telegram_id, name in users))

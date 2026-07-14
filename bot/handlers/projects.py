from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.access import UNREGISTERED_MESSAGE, get_client_for_user
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.vikunja_client import VikunjaAPIError

router = Router(name="projects")


@router.message(Command("projects"))
async def cmd_projects(message: Message, user_store: UserStore, cipher: TokenCipher, config: Config):
    client = await get_client_for_user(message.from_user.id, user_store, cipher, config)
    if client is None:
        await message.answer(UNREGISTERED_MESSAGE.format(user_id=message.from_user.id), parse_mode="Markdown")
        return

    try:
        projects = await client.list_projects()
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")
        return

    if not projects:
        await message.answer("No projects found.")
        return

    await message.answer("\n".join(f"• {p['title']}" for p in projects))

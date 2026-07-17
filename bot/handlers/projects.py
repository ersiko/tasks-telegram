from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.vikunja_client import VikunjaAPIError, VikunjaClient

router = Router(name="projects")


@router.message(Command("projects"))
async def cmd_projects(message: Message, client: VikunjaClient):
    try:
        projects = await client.list_projects()
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")
        return

    if not projects:
        await message.answer("No projects found.")
        return

    await message.answer("\n".join(f"• {p['title']}" for p in projects))

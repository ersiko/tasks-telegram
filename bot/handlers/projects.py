import html

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.vikunja_client import VikunjaClient

router = Router(name="projects")


@router.message(Command("projects"))
async def cmd_projects(message: Message, client: VikunjaClient):
    projects = await client.list_projects()

    if not projects:
        await message.answer("No projects found.")
        return

    await message.answer("\n".join(f"• {html.escape(p['title'])}" for p in projects))

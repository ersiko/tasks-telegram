import html

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot import i18n
from bot.vikunja_client import VikunjaClient

router = Router(name="projects")


@router.message(Command("projects", "projectes"))
async def cmd_projects(message: Message, client: VikunjaClient):
    projects = await client.list_projects()

    if not projects:
        await message.answer(i18n.t("no_projects_found"))
        return

    await message.answer("\n".join(f"• {html.escape(p['title'])}" for p in projects))

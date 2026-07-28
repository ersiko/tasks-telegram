import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import i18n
from bot.config import Config
from bot.keyboards import plan_week_keyboard
from bot.task_view import format_due, get_planning_candidates, week_end
from bot.vikunja_client import VikunjaClient

router = Router(name="planning")


def _format_plan_week_text(tasks: list[dict], config: Config) -> str:
    if not tasks:
        return i18n.t("nothing_to_plan")
    lines = [
        f"{i}. {html.escape(t['title'])}{format_due(t.get('due_date'), config)}"
        for i, t in enumerate(tasks, start=1)
    ]
    return i18n.t("plan_week_prompt") + "\n".join(lines)


async def _send_plan_week_list(message: Message, client: VikunjaClient, project: dict, config: Config) -> None:
    candidates = await get_planning_candidates(client, project["id"], config)
    text = _format_plan_week_text(candidates, config)
    kb = plan_week_keyboard(candidates, project["id"]) if candidates else None
    await message.answer(text, reply_markup=kb)


async def _refresh_plan_week_message(
    callback: CallbackQuery, client: VikunjaClient, project_id: int, config: Config
) -> None:
    candidates = await get_planning_candidates(client, project_id, config)
    text = _format_plan_week_text(candidates, config)
    kb = plan_week_keyboard(candidates, project_id) if candidates else None
    await callback.message.edit_text(text, reply_markup=kb)


@router.message(Command("plan_week", "choose_weekly_tasks", "planifica_setmana"))
async def cmd_plan_week(message: Message, client: VikunjaClient, config: Config):
    project = await client.resolve_project(config.weekly_project_name)
    if project is None:
        await message.answer(i18n.t("plan_week_no_project", name=config.weekly_project_name))
        return

    await _send_plan_week_list(message, client, project, config)


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan_pick(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, project_id_str, task_id_str = callback.data.split(":", 2)
    project_id = int(project_id_str)
    task_id = int(task_id_str)

    await client.set_due_date(task_id, week_end(config))
    await _refresh_plan_week_message(callback, client, project_id, config)

    await callback.answer(i18n.t("plan_week_added"))

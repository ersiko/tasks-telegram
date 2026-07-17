from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.keyboards import plan_week_keyboard
from bot.task_view import format_due, get_planning_candidates, week_end
from bot.vikunja_client import VikunjaAPIError, VikunjaClient

router = Router(name="planning")

NOTHING_TO_PLAN = "Nothing to plan — every open task already has a due date this week or later. 🎉"


def _format_plan_week_text(tasks: list[dict], config: Config) -> str:
    if not tasks:
        return NOTHING_TO_PLAN
    lines = [f"{i}. {t['title']}{format_due(t.get('due_date'), config)}" for i, t in enumerate(tasks, start=1)]
    return "Tap a task to put it on this week's plan:\n\n" + "\n".join(lines)


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


@router.message(Command("plan_week", "choose_weekly_tasks"))
async def cmd_plan_week(message: Message, client: VikunjaClient, config: Config):
    project = await client.resolve_project(config.weekly_project_name)
    if project is None:
        await message.answer(
            f"No project matching '{config.weekly_project_name}' — check the WEEKLY_PROJECT_NAME setting."
        )
        return

    try:
        await _send_plan_week_list(message, client, project, config)
    except VikunjaAPIError as exc:
        await message.answer(f"Vikunja error: {exc}")


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan_pick(callback: CallbackQuery, client: VikunjaClient, config: Config):
    _, project_id_str, task_id_str = callback.data.split(":", 2)
    project_id = int(project_id_str)
    task_id = int(task_id_str)

    try:
        await client.set_due_date(task_id, week_end(config))
        await _refresh_plan_week_message(callback, client, project_id, config)
    except VikunjaAPIError as exc:
        await callback.answer(f"Error: {exc}", show_alert=True)
        return

    await callback.answer("Added to this week's plan ✅")

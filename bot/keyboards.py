from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import i18n


def task_row_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n.t("btn_done"), callback_data=f"done:{task_id}"),
                InlineKeyboardButton(text=i18n.t("btn_delete"), callback_data=f"del:{task_id}"),
            ]
        ]
    )


def list_menu_keyboard(ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n.t("btn_mark_done"), callback_data=f"menu:done:{ctx}"),
                InlineKeyboardButton(text=i18n.t("btn_delete"), callback_data=f"menu:delete:{ctx}"),
            ],
            [
                InlineKeyboardButton(text=i18n.t("btn_reschedule"), callback_data=f"menu:reschedule:{ctx}"),
                InlineKeyboardButton(text=i18n.t("btn_priority"), callback_data=f"menu:priority:{ctx}"),
            ],
            [
                InlineKeyboardButton(text=i18n.t("btn_rename"), callback_data=f"menu:rename:{ctx}"),
            ],
        ]
    )


def task_picker_keyboard(tasks: list[dict], action: str, ctx: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=task["title"][:40], callback_data=f"pick:{action}:{ctx}:{task['id']}")]
        for task in tasks
    ]
    rows.append([InlineKeyboardButton(text=i18n.t("btn_back"), callback_data=f"back:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reschedule_prompt_keyboard(task_id: int, ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n.t("btn_snooze_day"), callback_data=f"resched_snooze:{task_id}:{ctx}:1"),
                InlineKeyboardButton(text=i18n.t("btn_snooze_week"), callback_data=f"resched_snooze:{task_id}:{ctx}:7"),
            ],
            [InlineKeyboardButton(text=i18n.t("btn_remove_due"), callback_data=f"resched_clear:{task_id}:{ctx}")],
            [InlineKeyboardButton(text=i18n.t("btn_cancel"), callback_data=f"pending_cancel:{ctx}")],
        ]
    )


def cancel_pending_keyboard(ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=i18n.t("btn_cancel"), callback_data=f"pending_cancel:{ctx}")]]
    )


def _priority_options() -> list[tuple[str, int]]:
    return [
        (i18n.t("priority_unset"), 0),
        (i18n.t("priority_low"), 1),
        (i18n.t("priority_medium"), 2),
        (i18n.t("priority_high"), 3),
        (i18n.t("priority_urgent"), 4),
        (i18n.t("priority_donow"), 5),
    ]


def priority_picker_keyboard(task_id: int, ctx: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"setprio:{value}:{task_id}:{ctx}")]
        for label, value in _priority_options()
    ]
    rows.append([InlineKeyboardButton(text=i18n.t("btn_cancel"), callback_data=f"back:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(task_id: int, ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=i18n.t("btn_yes_delete"), callback_data=f"delconfirm:{task_id}:{ctx}"),
                InlineKeyboardButton(text=i18n.t("btn_cancel"), callback_data=f"back:{ctx}"),
            ]
        ]
    )


def plan_week_keyboard(tasks: list[dict], project_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=task["title"][:40], callback_data=f"plan:{project_id}:{task['id']}")]
        for task in tasks
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

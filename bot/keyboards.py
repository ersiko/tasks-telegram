from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import i18n
from bot.quickadd import (
    REPEAT_MODE_FROM_COMPLETION,
    REPEAT_MODE_MONTHLY,
    SECONDS_PER_DAY,
    SECONDS_PER_MONTH_APPROX,
    SECONDS_PER_YEAR_APPROX,
)


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
                InlineKeyboardButton(text=i18n.t("btn_repeat"), callback_data=f"menu:repeat:{ctx}"),
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


def _repeat_options() -> list[tuple[str, int, int]]:
    # (label, repeat_after seconds, repeat_mode) - repeat_after is ignored
    # by Vikunja for REPEAT_MODE_MONTHLY (kept at 0 here for consistency)
    # and is meaningless for "off" too. See bot/quickadd.py's REPEAT_MODE_*
    # comment for what these mode values mean and why "every N months"/
    # "yearly" are fixed day-count approximations rather than calendar-exact.
    return [
        (i18n.t("repeat_off"), 0, 0),
        (i18n.t("repeat_daily"), SECONDS_PER_DAY, REPEAT_MODE_FROM_COMPLETION),
        (i18n.t("repeat_weekly"), 7 * SECONDS_PER_DAY, REPEAT_MODE_FROM_COMPLETION),
        (i18n.t("repeat_every_2_weeks"), 14 * SECONDS_PER_DAY, REPEAT_MODE_FROM_COMPLETION),
        (i18n.t("repeat_monthly"), 0, REPEAT_MODE_MONTHLY),
        (i18n.t("repeat_every_3_months"), 3 * SECONDS_PER_MONTH_APPROX, REPEAT_MODE_FROM_COMPLETION),
        (i18n.t("repeat_yearly"), SECONDS_PER_YEAR_APPROX, REPEAT_MODE_FROM_COMPLETION),
    ]


def repeat_picker_keyboard(task_id: int, ctx: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"setrepeat:{repeat_after}:{repeat_mode}:{task_id}:{ctx}")]
        for label, repeat_after, repeat_mode in _repeat_options()
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

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def task_row_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Done", callback_data=f"done:{task_id}"),
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"del:{task_id}"),
            ]
        ]
    )


def list_menu_keyboard(ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Mark Done", callback_data=f"menu:done:{ctx}"),
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"menu:delete:{ctx}"),
            ],
            [
                InlineKeyboardButton(text="📅 Reschedule", callback_data=f"menu:reschedule:{ctx}"),
                InlineKeyboardButton(text="🔢 Priority", callback_data=f"menu:priority:{ctx}"),
            ],
            [
                InlineKeyboardButton(text="✏️ Rename", callback_data=f"menu:rename:{ctx}"),
            ],
        ]
    )


def task_picker_keyboard(tasks: list[dict], action: str, ctx: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=task["title"][:40], callback_data=f"pick:{action}:{ctx}:{task['id']}")]
        for task in tasks
    ]
    rows.append([InlineKeyboardButton(text="‹ Back", callback_data=f"back:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reschedule_prompt_keyboard(task_id: int, ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="😴 +1 day", callback_data=f"resched_snooze:{task_id}:{ctx}:1"),
                InlineKeyboardButton(text="😴 +1 week", callback_data=f"resched_snooze:{task_id}:{ctx}:7"),
            ],
            [InlineKeyboardButton(text="🚫 Remove due date", callback_data=f"resched_clear:{task_id}:{ctx}")],
            [InlineKeyboardButton(text="‹ Cancel", callback_data=f"pending_cancel:{ctx}")],
        ]
    )


def cancel_pending_keyboard(ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="‹ Cancel", callback_data=f"pending_cancel:{ctx}")]])


PRIORITY_OPTIONS = [
    ("🚫 Unset", 0),
    ("⚪ Low", 1),
    ("🔵 Medium", 2),
    ("🟡 High", 3),
    ("🟠 Urgent", 4),
    ("🔴 Do now", 5),
]


def priority_picker_keyboard(task_id: int, ctx: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"setprio:{value}:{task_id}:{ctx}")]
        for label, value in PRIORITY_OPTIONS
    ]
    rows.append([InlineKeyboardButton(text="‹ Cancel", callback_data=f"back:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(task_id: int, ctx: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Yes, delete", callback_data=f"delconfirm:{task_id}:{ctx}"),
                InlineKeyboardButton(text="‹ Cancel", callback_data=f"back:{ctx}"),
            ]
        ]
    )


def plan_week_keyboard(tasks: list[dict], project_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=task["title"][:40], callback_data=f"plan:{project_id}:{task['id']}")]
        for task in tasks
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

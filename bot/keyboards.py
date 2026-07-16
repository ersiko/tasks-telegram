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
            ]
        ]
    )


def task_picker_keyboard(tasks: list[dict], action: str, ctx: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=task["title"][:40], callback_data=f"pick:{action}:{ctx}:{task['id']}")]
        for task in tasks
    ]
    rows.append([InlineKeyboardButton(text="‹ Back", callback_data=f"back:{ctx}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

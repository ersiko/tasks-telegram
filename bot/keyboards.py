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

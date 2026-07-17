import html

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db import UserStore

router = Router(name="start")

HELP_TEXT = (
    "Send me a plain message to add a task, e.g.:\n"
    "  Pay rent +Bills !high tomorrow 5pm\n\n"
    "Quick-add syntax:\n"
    "  +project   assign to a project (matched by name)\n"
    "  *label     add a label (repeatable)\n"
    "  !priority  low / medium / high / urgent / donow (or 1-5)\n"
    "  ~repeat    daily / weekly / monthly / every N days / every N weeks\n"
    "  trailing text is parsed as the due date, e.g. 'friday 5pm'\n\n"
    "Commands:\n"
    "/list [project] - show open tasks\n"
    "/today - tasks due today or overdue\n"
    "/week - tasks due this week or overdue\n"
    "/plan_week - pick this week's goals from the backlog\n"
    "/recap - what's been completed so far this week\n"
    "/projects - list your Vikunja projects\n"
    "/pause [days] - pause the digest (indefinitely, or for N days)\n"
    "/resume - resume the digest\n"
    "/help - show this message\n\n"
    "Each list has Mark Done / Delete / Reschedule / Priority / Rename buttons — "
    "tap one, then pick a task."
)


@router.message(Command("start"))
async def cmd_start(message: Message, user_store: UserStore):
    user = await user_store.get_user(message.from_user.id)
    if user is None:
        await message.answer(
            f"You're not registered yet. Your Telegram ID is `{message.from_user.id}`.\n"
            "Send this to the admin so they can register you.",
            parse_mode="Markdown",
        )
        return
    await message.answer(f"Hi {html.escape(user.display_name)}!\n\n" + HELP_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message, user_store: UserStore):
    user = await user_store.get_user(message.from_user.id)
    if user is None:
        await message.answer(
            f"You're not registered yet. Your Telegram ID is `{message.from_user.id}`.",
            parse_mode="Markdown",
        )
        return
    await message.answer(HELP_TEXT)


@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    # No registration/auth needed - just a setup utility, e.g. to find a
    # group's chat ID for DIGEST_CHAT_ID after adding the bot to it.
    await message.answer(f"This chat's ID is `{message.chat.id}`", parse_mode="Markdown")

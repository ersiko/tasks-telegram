from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from bot.access import UNREGISTERED_MESSAGE, get_client_for_user


class VikunjaClientMiddleware(BaseMiddleware):
    """Resolves the calling user's VikunjaClient and injects it as `client`.

    Apply to routers where every handler needs an authenticated client
    (tasks, projects, planning) so individual handlers don't each repeat
    the "resolve client, bail with the unregistered message if None" check.
    Opens the client's connection for the handler's duration via `async
    with` and closes it afterward - see VikunjaClient.__aenter__.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_store = data["user_store"]
        cipher = data["cipher"]
        config = data["config"]

        client = await get_client_for_user(event.from_user.id, user_store, cipher, config)
        if client is None:
            if isinstance(event, CallbackQuery):
                await event.answer("You're not registered.", show_alert=True)
            else:
                await event.answer(UNREGISTERED_MESSAGE.format(user_id=event.from_user.id), parse_mode="Markdown")
            return None

        async with client:
            data["client"] = client
            return await handler(event, data)

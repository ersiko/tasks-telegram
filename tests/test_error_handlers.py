import asyncio
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import ErrorEvent, Update

from bot.error_handlers import FRIENDLY_VIKUNJA_ERROR, handle_vikunja_error
from bot.vikunja_client import VikunjaAPIError


def _fake_event(*, callback_query=None, message=None, exception=None):
    update = MagicMock(spec=Update)
    update.callback_query = callback_query
    update.message = message
    event = MagicMock(spec=ErrorEvent)
    event.update = update
    event.exception = exception or VikunjaAPIError("boom")
    return event


def test_callback_query_gets_friendly_alert_not_raw_error():
    fake_callback = MagicMock()
    fake_callback.answer = AsyncMock()
    event = _fake_event(
        callback_query=fake_callback,
        exception=VikunjaAPIError('GET /tasks failed (401): {"code":11,"message":"..."}'),
    )

    result = asyncio.run(handle_vikunja_error(event))

    assert result is True
    fake_callback.answer.assert_called_once_with(FRIENDLY_VIKUNJA_ERROR, show_alert=True)
    # The raw technical detail must never reach the user-facing call.
    assert "401" not in fake_callback.answer.call_args.args[0]
    assert "code" not in fake_callback.answer.call_args.args[0]


def test_message_gets_friendly_reply_not_raw_error():
    fake_message = MagicMock()
    fake_message.answer = AsyncMock()
    event = _fake_event(message=fake_message, exception=VikunjaAPIError("PUT /tasks failed (500)"))

    asyncio.run(handle_vikunja_error(event))

    fake_message.answer.assert_called_once_with(FRIENDLY_VIKUNJA_ERROR)
    assert "500" not in fake_message.answer.call_args.args[0]


def test_does_not_raise_if_notifying_the_user_also_fails():
    fake_callback = MagicMock()
    fake_callback.answer = AsyncMock(side_effect=RuntimeError("network blip"))
    event = _fake_event(callback_query=fake_callback)

    # Should swallow the secondary failure rather than crash the dispatcher.
    result = asyncio.run(handle_vikunja_error(event))
    assert result is True

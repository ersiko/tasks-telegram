import logging

from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

FRIENDLY_VIKUNJA_ERROR = (
    "⚠️ That didn't go through — Vikunja didn't respond as expected. This is usually "
    "temporary, so it's worth trying again in a moment. If it keeps happening, let Tomas know."
)


async def handle_vikunja_error(event: ErrorEvent) -> bool:
    """Centralized handler for VikunjaAPIError raised while processing an
    update (registered in main.py, scoped to that exception type only).
    Individual handlers in tasks/planning/projects deliberately don't
    catch VikunjaAPIError themselves anymore - they let it propagate here,
    so every failure gets one consistent, non-technical message instead of
    the raw HTTP/JSON error text, and gets logged server-side exactly
    once regardless of which handler it came from.
    """
    logger.error("Vikunja API error while handling update", exc_info=event.exception)

    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(FRIENDLY_VIKUNJA_ERROR, show_alert=True)
        elif update.message is not None:
            await update.message.answer(FRIENDLY_VIKUNJA_ERROR)
    except Exception:
        logger.exception("Failed to notify user about a Vikunja error")

    return True

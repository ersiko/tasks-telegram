import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.digest import run_digest_loop
from bot.handlers import admin, pause, planning, projects, recap, start, tasks
from bot.middlewares import VikunjaClientMiddleware
from bot.pause_store import PauseStore


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    cipher = TokenCipher(config.fernet_key)
    user_store = UserStore(config.users_file)
    await user_store.init()
    pause_store = PauseStore(config.pause_state_file)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # These three routers' handlers all need an authenticated VikunjaClient;
    # the middleware resolves it once and injects it as the `client` param,
    # short-circuiting with the "not registered" message if there isn't one.
    vikunja_auth = VikunjaClientMiddleware()
    for router in (tasks.router, projects.router, planning.router):
        router.message.middleware(vikunja_auth)
        router.callback_query.middleware(vikunja_auth)

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(recap.router)
    dp.include_router(pause.router)
    dp.include_router(projects.router)
    dp.include_router(planning.router)
    dp.include_router(tasks.router)

    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(run_digest_loop(bot, user_store, cipher, config, pause_store))
    await dp.start_polling(
        bot, user_store=user_store, cipher=cipher, config=config, pause_store=pause_store
    )


if __name__ == "__main__":
    asyncio.run(main())

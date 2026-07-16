import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.digest import run_digest_loop
from bot.handlers import admin, projects, start, tasks


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    cipher = TokenCipher(config.fernet_key)
    user_store = UserStore(config.users_file)
    await user_store.init()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(projects.router)
    dp.include_router(tasks.router)

    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(run_digest_loop(bot, user_store, cipher, config))
    await dp.start_polling(bot, user_store=user_store, cipher=cipher, config=config)


if __name__ == "__main__":
    asyncio.run(main())

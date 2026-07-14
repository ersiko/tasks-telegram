from typing import Optional

from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.vikunja_client import VikunjaClient

UNREGISTERED_MESSAGE = (
    "You're not registered yet. Your Telegram ID is `{user_id}`.\n"
    "Ask the admin to register you with /adduser."
)


async def get_client_for_user(
    user_id: int, user_store: UserStore, cipher: TokenCipher, config: Config
) -> Optional[VikunjaClient]:
    user = await user_store.get_user(user_id)
    if user is None:
        return None
    token = cipher.decrypt(user.encrypted_token)
    return VikunjaClient(config.vikunja_url, token)

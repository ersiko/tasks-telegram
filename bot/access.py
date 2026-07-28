from typing import Optional

from bot import i18n
from bot.config import Config
from bot.crypto import TokenCipher
from bot.db import UserStore
from bot.vikunja_client import VikunjaClient


def unregistered_message(user_id: int) -> str:
    return i18n.t("not_registered", user_id=user_id)


async def get_client_for_user(
    user_id: int, user_store: UserStore, cipher: TokenCipher, config: Config
) -> Optional[VikunjaClient]:
    user = await user_store.get_user(user_id)
    if user is None:
        return None
    token = cipher.decrypt(user.encrypted_token)
    return VikunjaClient(config.vikunja_url, token)

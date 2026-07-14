import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    bot_token: str
    vikunja_url: str
    admin_telegram_id: int
    fernet_key: str
    users_file: str
    default_project_name: str


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required (set it in .env)")
    return value


def load_config() -> Config:
    from dotenv import load_dotenv

    load_dotenv(override=False)

    try:
        admin_id = int(_required("ADMIN_TELEGRAM_ID"))
    except ValueError as exc:
        raise RuntimeError("ADMIN_TELEGRAM_ID must be an integer") from exc

    return Config(
        bot_token=_required("BOT_TOKEN"),
        vikunja_url=_required("VIKUNJA_URL").rstrip("/"),
        admin_telegram_id=admin_id,
        fernet_key=_required("FERNET_KEY"),
        users_file=os.environ.get("USERS_FILE", "users.json"),
        default_project_name=os.environ.get("DEFAULT_PROJECT_NAME", "Inbox"),
    )

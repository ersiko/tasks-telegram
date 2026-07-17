import os
from dataclasses import dataclass
from typing import Optional

WEEKDAY_NAMES = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}


@dataclass(frozen=True)
class Config:
    bot_token: str
    vikunja_url: str
    admin_telegram_id: int
    fernet_key: str
    users_file: str
    default_project_name: str
    weekly_project_name: str
    digest_time: str
    timezone: str
    digest_chat_id: Optional[int]
    week_start_day: int  # ISO weekday, 1=Monday..7=Sunday


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required (set it in .env)")
    return value


def _parse_weekday(name: str) -> int:
    key = name.strip().lower()
    if key not in WEEKDAY_NAMES:
        raise RuntimeError(f"WEEK_START_DAY must be a weekday name (e.g. Monday), got {name!r}")
    return WEEKDAY_NAMES[key]


def load_config() -> Config:
    from dotenv import load_dotenv

    load_dotenv(override=False)

    try:
        admin_id = int(_required("ADMIN_TELEGRAM_ID"))
    except ValueError as exc:
        raise RuntimeError("ADMIN_TELEGRAM_ID must be an integer") from exc

    digest_chat_id_raw = os.environ.get("DIGEST_CHAT_ID", "").strip()
    try:
        digest_chat_id = int(digest_chat_id_raw) if digest_chat_id_raw else None
    except ValueError as exc:
        raise RuntimeError("DIGEST_CHAT_ID must be an integer") from exc

    return Config(
        bot_token=_required("BOT_TOKEN"),
        vikunja_url=_required("VIKUNJA_URL").rstrip("/"),
        admin_telegram_id=admin_id,
        fernet_key=_required("FERNET_KEY"),
        users_file=os.environ.get("USERS_FILE", "users.json"),
        default_project_name=os.environ.get("DEFAULT_PROJECT_NAME", "Inbox"),
        weekly_project_name=os.environ.get("WEEKLY_PROJECT_NAME", "Week to Week"),
        digest_time=os.environ.get("DIGEST_TIME", "07:00"),
        timezone=os.environ.get("TIMEZONE", "UTC"),
        digest_chat_id=digest_chat_id,
        week_start_day=_parse_weekday(os.environ.get("WEEK_START_DAY", "Monday")),
    )

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class UserRecord:
    telegram_id: int
    encrypted_token: bytes
    display_name: str


class UserStore:
    """Tiny JSON-file-backed store mapping Telegram IDs to encrypted Vikunja tokens.

    Sized for a handful of users (a family, not a SaaS) - a plain file is
    plenty and lets the admin eyeball or hand-edit it if needed.
    """

    def __init__(self, path: str):
        self._path = path
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        if not os.path.exists(self._path):
            self._write({})

    def _read(self) -> dict:
        if not os.path.exists(self._path):
            return {}
        with open(self._path, "r") as f:
            content = f.read().strip()
        return json.loads(content) if content else {}

    def _write(self, data: dict) -> None:
        tmp_path = f"{self._path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self._path)

    async def get_user(self, telegram_id: int) -> Optional[UserRecord]:
        entry = self._read().get(str(telegram_id))
        if entry is None:
            return None
        return UserRecord(telegram_id, entry["encrypted_token"].encode(), entry["display_name"])

    async def add_user(self, telegram_id: int, encrypted_token: bytes, display_name: str) -> None:
        async with self._lock:
            data = self._read()
            data[str(telegram_id)] = {
                "encrypted_token": encrypted_token.decode(),
                "display_name": display_name,
            }
            self._write(data)

    async def remove_user(self, telegram_id: int) -> bool:
        async with self._lock:
            data = self._read()
            if str(telegram_id) not in data:
                return False
            del data[str(telegram_id)]
            self._write(data)
            return True

    async def list_users(self) -> list[tuple[int, str]]:
        data = self._read()
        return sorted(
            ((int(tid), entry["display_name"]) for tid, entry in data.items()),
            key=lambda pair: pair[1],
        )

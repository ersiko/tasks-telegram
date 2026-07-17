import asyncio
import datetime as dt
import json
import os
from typing import Optional


class PauseStore:
    """Tiny JSON-file-backed store for whether the digest is paused.

    Sized the same way as UserStore (bot/db.py) - a single small file for
    one on/off flag plus an optional auto-resume time is plenty; no need
    for a database. Must persist across restarts (unlike the in-memory
    pending-action state elsewhere), since an intentional "away for two
    weeks" pause shouldn't get silently cleared by a redeploy.
    """

    def __init__(self, path: str):
        self._path = path
        self._lock = asyncio.Lock()

    def _read(self) -> dict:
        if not os.path.exists(self._path):
            return {}
        with open(self._path, "r") as f:
            content = f.read().strip()
        return json.loads(content) if content else {}

    def _write(self, data: dict) -> None:
        tmp_path = f"{self._path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self._path)

    async def pause(self, resume_at: Optional[dt.datetime] = None) -> None:
        async with self._lock:
            self._write({"paused": True, "resume_at": resume_at.isoformat() if resume_at else None})

    async def resume(self) -> None:
        async with self._lock:
            self._write({})

    async def is_paused(self, now: Optional[dt.datetime] = None) -> bool:
        data = self._read()
        if not data.get("paused"):
            return False
        resume_at_raw = data.get("resume_at")
        if resume_at_raw is None:
            return True  # paused indefinitely, until /resume
        resume_at = dt.datetime.fromisoformat(resume_at_raw)
        current = now if now is not None else dt.datetime.now(resume_at.tzinfo)
        return current < resume_at  # auto-expired pauses just report as not-paused

    async def check_and_clear_if_expired(self, now: dt.datetime) -> bool:
        """If a timed pause (/pause N) has now run its course, clear it and
        return True - the digest loop uses this to fire the "pause just
        ended" catch-up exactly once, rather than on every subsequent
        loop iteration. False for an indefinite pause (only /resume ends
        that), a still-active timed pause, or no pause at all."""
        data = self._read()
        if not data.get("paused"):
            return False
        resume_at_raw = data.get("resume_at")
        if resume_at_raw is None:
            return False
        resume_at = dt.datetime.fromisoformat(resume_at_raw)
        if now < resume_at:
            return False
        async with self._lock:
            self._write({})
        return True

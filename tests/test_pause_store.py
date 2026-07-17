import asyncio
import datetime as dt

from bot.pause_store import PauseStore

TZ = dt.timezone.utc


def test_not_paused_by_default(tmp_path):
    store = PauseStore(str(tmp_path / "pause.json"))
    assert asyncio.run(store.is_paused()) is False


def test_indefinite_pause_stays_paused(tmp_path):
    store = PauseStore(str(tmp_path / "pause.json"))
    asyncio.run(store.pause())
    assert asyncio.run(store.is_paused()) is True
    # Even checked far in the future - no resume_at means no auto-expiry.
    far_future = dt.datetime(2030, 1, 1, tzinfo=TZ)
    assert asyncio.run(store.is_paused(now=far_future)) is True


def test_timed_pause_expires(tmp_path):
    store = PauseStore(str(tmp_path / "pause.json"))
    start = dt.datetime(2026, 7, 18, 9, 0, tzinfo=TZ)
    resume_at = start + dt.timedelta(days=7)
    asyncio.run(store.pause(resume_at))

    assert asyncio.run(store.is_paused(now=start)) is True
    assert asyncio.run(store.is_paused(now=resume_at - dt.timedelta(minutes=1))) is True
    assert asyncio.run(store.is_paused(now=resume_at)) is False
    assert asyncio.run(store.is_paused(now=resume_at + dt.timedelta(days=1))) is False


def test_resume_clears_pause(tmp_path):
    store = PauseStore(str(tmp_path / "pause.json"))
    asyncio.run(store.pause())
    assert asyncio.run(store.is_paused()) is True
    asyncio.run(store.resume())
    assert asyncio.run(store.is_paused()) is False


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "pause.json")
    asyncio.run(PauseStore(path).pause())
    # A fresh instance pointed at the same file should see the same state -
    # this is what makes the pause survive a bot restart/redeploy.
    assert asyncio.run(PauseStore(path).is_paused()) is True

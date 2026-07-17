import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

import bot.digest as digest_module
from bot.config import Config
from bot.digest import next_run_at

TZ = ZoneInfo("Europe/Madrid")


def _config(digest_chat_id=None):
    return Config(
        bot_token="x",
        vikunja_url="https://example.com/api/v1",
        admin_telegram_id=1,
        fernet_key="x",
        users_file="users.json",
        pause_state_file="digest_pause.json",
        default_project_name="Inbox",
        weekly_project_name="Week to Week",
        digest_time="07:00",
        timezone="UTC",
        digest_chat_id=digest_chat_id,
        week_start_day=1,
    )


class _FakeUserStore:
    def __init__(self, users):
        self._users = users

    async def list_users(self):
        return self._users


class _FakeClient:
    def __init__(self, tasks, projects):
        self._tasks = tasks
        self._projects = projects

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def list_tasks(self, project_id=None, done=False):
        if done is None:
            return self._tasks
        return [t for t in self._tasks if t.get("done", False) == done]

    async def list_projects(self):
        return self._projects


def test_before_target_time_runs_today():
    now = dt.datetime(2026, 7, 16, 6, 30, tzinfo=TZ)
    target = next_run_at(now, 7, 0)
    assert target == dt.datetime(2026, 7, 16, 7, 0, tzinfo=TZ)


def test_after_target_time_runs_tomorrow():
    now = dt.datetime(2026, 7, 16, 8, 0, tzinfo=TZ)
    target = next_run_at(now, 7, 0)
    assert target == dt.datetime(2026, 7, 17, 7, 0, tzinfo=TZ)


def test_exactly_at_target_time_runs_tomorrow():
    now = dt.datetime(2026, 7, 16, 7, 0, tzinfo=TZ)
    target = next_run_at(now, 7, 0)
    assert target == dt.datetime(2026, 7, 17, 7, 0, tzinfo=TZ)


def test_merged_today_tasks_dedupes_across_accounts(monkeypatch):
    config = _config()
    user_store = _FakeUserStore([(1, "Alice"), (2, "Bob")])
    shared_project = [{"id": 10, "title": "Chores"}]

    # Both accounts see the same shared project - task 100 is visible to
    # both, task 101 only to Alice, task 102 only to Bob. All safely in the
    # past so they count as "due today or overdue" regardless of real time.
    alice_tasks = [
        {"id": 100, "title": "Buy milk", "project_id": 10, "due_date": "2020-01-01T08:00:00Z"},
        {"id": 101, "title": "Water plants", "project_id": 10, "due_date": "2020-01-02T08:00:00Z"},
    ]
    bob_tasks = [
        {"id": 100, "title": "Buy milk", "project_id": 10, "due_date": "2020-01-01T08:00:00Z"},
        {"id": 102, "title": "Take out trash", "project_id": 10, "due_date": "2020-01-03T08:00:00Z"},
    ]
    clients = {1: _FakeClient(alice_tasks, shared_project), 2: _FakeClient(bob_tasks, shared_project)}

    async def fake_get_client_for_user(telegram_id, *_args, **_kwargs):
        return clients[telegram_id]

    monkeypatch.setattr(digest_module, "get_client_for_user", fake_get_client_for_user)

    tasks, titles = asyncio.run(digest_module._merged_today_tasks(user_store, None, config))

    assert sorted(t["id"] for t in tasks) == [100, 101, 102]
    assert titles == {10: "Chores"}


def test_merged_today_tasks_empty_when_nothing_due(monkeypatch):
    config = _config()
    user_store = _FakeUserStore([(1, "Alice")])
    clients = {1: _FakeClient([], [])}

    async def fake_get_client_for_user(telegram_id, *_args, **_kwargs):
        return clients[telegram_id]

    monkeypatch.setattr(digest_module, "get_client_for_user", fake_get_client_for_user)

    tasks, titles = asyncio.run(digest_module._merged_today_tasks(user_store, None, config))
    assert tasks == []
    assert titles is None


def test_merged_completed_between_dedupes_and_orders_chronologically(monkeypatch):
    config = _config()
    user_store = _FakeUserStore([(1, "Alice"), (2, "Bob")])
    start = dt.datetime(2026, 7, 6, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 7, 12, 23, 59, 59, tzinfo=dt.timezone.utc)

    alice_tasks = [
        {"id": 200, "title": "Shared task", "done": True, "done_at": "2026-07-08T09:00:00Z"},
        {"id": 201, "title": "Alice only, earlier", "done": True, "done_at": "2026-07-07T09:00:00Z"},
    ]
    bob_tasks = [
        {"id": 200, "title": "Shared task", "done": True, "done_at": "2026-07-08T09:00:00Z"},
        {"id": 202, "title": "Bob only, out of range", "done": True, "done_at": "2026-06-01T09:00:00Z"},
    ]
    clients = {1: _FakeClient(alice_tasks, []), 2: _FakeClient(bob_tasks, [])}

    async def fake_get_client_for_user(telegram_id, *_args, **_kwargs):
        return clients[telegram_id]

    monkeypatch.setattr(digest_module, "get_client_for_user", fake_get_client_for_user)

    result = asyncio.run(digest_module.merged_completed_between(user_store, None, config, start, end))
    assert [t["id"] for t in result] == [201, 200]  # earlier first, 202 excluded (out of range), 200 not duplicated


def test_previous_month_range_handles_january():
    now = dt.datetime(2026, 1, 15, 10, 0, tzinfo=dt.timezone.utc)
    start, end = digest_module._previous_month_range(now)
    assert start == dt.datetime(2025, 12, 1, 0, 0, tzinfo=dt.timezone.utc)
    assert end == dt.datetime(2025, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)


def test_previous_month_range_normal_month():
    now = dt.datetime(2026, 7, 15, 10, 0, tzinfo=dt.timezone.utc)
    start, end = digest_module._previous_month_range(now)
    assert start == dt.datetime(2026, 6, 1, 0, 0, tzinfo=dt.timezone.utc)
    assert end == dt.datetime(2026, 6, 30, 23, 59, 59, tzinfo=dt.timezone.utc)

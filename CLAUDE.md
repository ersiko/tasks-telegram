# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Environment setup (uses [uv](https://docs.astral.sh/uv/), not raw `venv`/`pip`):

```bash
uv venv
uv pip install -r requirements.txt
```

Run the bot locally:

```bash
.venv/bin/python -m bot.main
```

Run tests:

```bash
.venv/bin/pytest tests/
.venv/bin/pytest tests/test_quickadd.py -v                 # one file
.venv/bin/pytest tests/test_quickadd.py::test_repeat_monthly # one test
```

Compile-check after edits (catches syntax errors without needing a live bot token/network):

```bash
.venv/bin/python -m compileall -q bot
```

Docker deployment: `docker compose up -d --build` against `compose.yaml` (see "Deployment"
below for why the filename matters).

CI (`.github/workflows/tests.yml`) runs the same `pytest tests/` on every push/PR — there's
no staging environment, Komodo deploys straight from `main`, so this is the only automated
check before something reaches production.

## Architecture

Single aiogram v3 long-polling process — no webhook, no public HTTP endpoint. Vikunja is
the source of truth for all tasks/projects/labels; this repo holds no task data of its own,
only the mapping of Telegram users to their encrypted Vikunja API tokens (`users.json`,
values encrypted at rest with a Fernet key from `FERNET_KEY`).

### Module layout

- `bot/vikunja_client.py` — thin async wrapper over Vikunja's REST API. A `VikunjaClient` is
  constructed fresh per request with the calling user's decrypted token (see
  `bot/access.py:get_client_for_user`); nothing is cached or shared across users. Supports
  `async with` to reuse one `httpx.AsyncClient` connection across every call made within the
  block (falls back to a one-shot connection if not entered) — `bot/middlewares.py` always
  enters it, so handlers get connection reuse for free.
- `bot/middlewares.py` — `VikunjaClientMiddleware`, applied to the `tasks`/`projects`/
  `planning` routers in `main.py` (not `admin`/`start`, which don't need a Vikunja client).
  Resolves the calling user's client once, short-circuits with the "not registered" message
  if there isn't one, and injects the client as the `client` handler parameter — same
  workflow-data-by-parameter-name mechanism aiogram already uses for `config`. Handlers in
  those three routers should take `client: VikunjaClient` as a parameter rather than
  resolving it themselves.
- `bot/task_view.py` — shared "which tasks, formatted how" logic used by both the on-demand
  handlers (`/today`, `/week`, `/list`) and the proactive push in `bot/digest.py`. All
  date-boundary math ("is this due today/this week") happens here, in the configured
  `TIMEZONE` — never naive UTC (see gotchas below).
- `bot/digest.py` also supports posting to a shared group instead of DMing each user (see
  `DIGEST_CHAT_ID`). `_merged_today_tasks` and `merged_completed_between` fetch every
  registered account's view and deduplicate by task ID, since separate Vikunja accounts
  sharing a project would otherwise each report the same tasks — don't just pick one
  account's view for the group case, the whole point is showing everyone's tasks together.
  Group digests also get extra sections appended: a weekly recap+planning-nudge on
  `config.week_start_day`, and a monthly recap on the 1st — both DM-mode-only concepts are
  skipped there (see "Weekly and monthly recap sections" in README.md). `bot/handlers/
  recap.py` (`/recap`) reuses `merged_completed_between` for an on-demand version; it's
  intentionally *not* one of the `VikunjaClientMiddleware` routers, since it needs to iterate
  every registered account via `user_store`/`cipher` directly rather than act on a single
  resolved client.
- `bot/quickadd.py` — pure text parser (`parse(text) -> QuickAddResult`), no I/O, fully
  unit-tested. Extracts `*label`, `+project`, `!priority`, `~repeat` tokens via regex, then
  runs `dateparser.search.search_dates` on what's left over for a due date. Extraction order
  in `parse()` matters — each token type is stripped from the working string before the next
  step runs; a new magic-token type has to follow the same strip-then-continue pattern.
- `bot/handlers/` — aiogram routers, one per feature area (`tasks`, `planning`, `projects`,
  `admin`, `start`), registered in `bot/main.py`. `tasks.py` is the largest: it owns the
  catch-all quick-add message handler plus `/list`/`/today`/`/week` and the whole
  callback-driven list/picker/action flow described below.
- `bot/digest.py` — background `asyncio` task, started via `asyncio.create_task` in
  `main.py` alongside (not instead of) `dp.start_polling`, that wakes once a day and pushes
  each registered user their `/today`-equivalent view via `bot.send_message`.

### The list/picker/action callback flow

`/list`, `/today`, `/week`, and `/plan_week` render as a single message (deliberately not
one message per task — that was the original design and was changed for readability) with
an inline keyboard. Menu → picker → action, driven entirely by `callback_data` string
prefixes matched with `F.data.startswith(...)` in `bot/handlers/tasks.py`:

- `menu:{action}:{ctx}` — top-level buttons (Mark Done / Delete / Reschedule / Priority /
  Rename) from `list_menu_keyboard`. `ctx` encodes what the message is a view of: `"a"`
  (all), `"t"` (today), `"w"` (this week — boundaries per `config.week_start_day`, not
  hardcoded Monday-Sunday), or `"p{project_id}"` (one project) — see
  `task_view.get_tasks_for_ctx`.
- `pick:{action}:{ctx}:{task_id}` — after a menu tap, one button per task
  (`task_picker_keyboard`); tapping one applies `action` to that task.
- Actions needing more than one tap (Reschedule, Rename) don't finish inside the callback —
  they stash state in the in-memory `_pending_text_action` dict (keyed by Telegram user ID,
  TTL-bounded), and the *next plain-text message* from that user is consumed as the reply,
  checked in `handle_quick_add` before falling through to normal quick-add parsing. A new
  "ask a follow-up question" action needs to plug into that same pending-state check, not
  just add a callback handler.
- `back:{ctx}` / `pending_cancel:{ctx}` return to the menu view by refetching and
  re-rendering, rather than restoring prior message state.
- Every handler gets its `VikunjaClient` from `VikunjaClientMiddleware` (see above), not by
  resolving it itself.

### Vikunja API quirks encoded in the client (don't simplify these away without checking why)

- `list_tasks()` always hits the global `GET /tasks` filtered by `filter=project_id = N` when
  scoped to a project — never `/projects/{id}/tasks` or the view-scoped
  `/projects/{id}/views/{view}/tasks`. The latter 401s on this Vikunja instance/version even
  with full Tasks + Project Views token permissions granted (confirmed by direct testing);
  it's a Vikunja permission-model gap, not a bug here.
- Vikunja API tokens are far more granular than the resource names suggest (e.g. "Project
  Views" is a separate permission section from "Projects"). If one specific endpoint 401s
  while sibling endpoints work fine with the same token, it's a missing per-route
  permission, not a code bug — check the live OpenAPI spec at `{VIKUNJA_URL}/docs.json` (no
  auth required) to see what a given path actually needs.
- Regex alternation ordering has bitten twice so far (quoted-value extraction in
  `quickadd.py`; `day|days` matching `day` first and leaving a stray `s`): Python `re`
  alternation is first-match-wins, not longest-match, so alternatives must be ordered
  longest-first.
- `list_tasks(done=...)` is tri-state (`False`/`True`/`None`), not a plain boolean — this
  bit once already: `get_completed_between` needs `done=None` (fetch everything, filter by
  `done_at` client-side), because a recurring task flips back to `done=false` as part of
  advancing to its next occurrence, so `done=True` would silently exclude exactly the
  recurring completions the recap feature cares about.
- `TIMEZONE` (IANA name, e.g. `Europe/Madrid`) drives every "is this due today/this week"
  comparison and displayed due time — never use naive `datetime.utcnow()` for these, it
  silently shifts the boundary by the UTC offset. `tzdata` is a required pip dependency (not
  just stdlib `zoneinfo`) because the `python:3.12-slim` Docker base image ships no system
  IANA database.

### Deployment

The compose file is named `compose.yaml`, not `docker-compose.yml` — Komodo's Stack deploy
expects that name by default. It joins Vikunja's Docker network (`vikunja_default`,
external) so `VIKUNJA_URL` can point at `http://vikunja:3456/api/v1` directly instead of
round-tripping through Traefik/TLS. Full deploy and token-permission setup steps are in
README.md (operator-facing, deliberately not duplicated here).

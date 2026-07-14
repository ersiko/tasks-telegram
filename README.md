# tasks-telegram

A small Telegram bot that lets a few trusted people manage tasks in an existing
[Vikunja](https://vikunja.io) instance from Telegram, using natural-language
quick-add (e.g. `Pay rent +Bills !high tomorrow 5pm`). Vikunja itself remains
the source of truth and still has its normal web/mobile apps — this bot is
just an additional way in.

Users don't self-register: the admin creates a Vikunja API token for each
person and registers it with the bot via `/adduser`. There's no reminder/
notification scheduler in v1 — this is a pull-based interface (add/list/done).

## How it works

- One Python process (aiogram, long-polling — no public endpoint needed).
- A tiny `users.json` file maps each Telegram ID to an *encrypted* Vikunja API
  token (encrypted at rest with a Fernet key). Everything else (tasks,
  projects, labels) is fetched live from Vikunja's REST API — nothing is
  duplicated locally.

## Setup

### 1. Create the Telegram bot

Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`, and
copy the token it gives you into `BOT_TOKEN` in `.env`.

### 2. Get your Telegram numeric ID

Message the bot once it's running with `/start` — since you won't be
registered yet, it'll reply with your numeric ID. Put that in
`ADMIN_TELEGRAM_ID` in `.env`. (Only this ID can run `/adduser`,
`/removeuser`, `/users`.)

### 3. Generate an encryption key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the result in `FERNET_KEY` in `.env`. Keep it secret — anyone with this
key plus `users.json` can decrypt everyone's Vikunja tokens.

### 4. Configure `.env`

Copy `.env.example` to `.env` and fill in `BOT_TOKEN`, `VIKUNJA_URL` (include
the `/api/v1` suffix), `ADMIN_TELEGRAM_ID`, and `FERNET_KEY`.

### 5. Run it

Locally, with [uv](https://docs.astral.sh/uv/):

```bash
uv venv
uv pip install -r requirements.txt
.venv/bin/python -m bot.main
```

Or with Docker, deployed on the same host as Vikunja (`minipc1`), joining its
Docker network so the bot can reach it internally without going through
Traefik/TLS:

```bash
docker compose up -d --build
```

`docker-compose.yml` already declares `vikunja_default` as an external
network (Vikunja's compose project is named `vikunja`, so Compose names its
default network `vikunja_default`) — this only works if the bot's compose
project is brought up on `minipc1`, alongside Vikunja's own stack. When
deploying this way, set `VIKUNJA_URL=http://vikunja:3456/api/v1` in the `.env`
that lives on `minipc1` (see the comment in `.env.example`).

`docker-compose.yml` also persists `users.json` in a named volume, so it
survives container restarts/rebuilds.

To deploy: copy this project's folder to `minipc1` (e.g. `git clone`/`scp`),
create `.env` there per step 4 above (with the internal `VIKUNJA_URL`), then
run `docker compose up -d --build` from that folder.

### 6. Create a Vikunja API token per person

In Vikunja: **Settings → API Tokens → Create**. Grant at least:

- Tasks: read, create, update, delete
- Projects: read
- Labels: read, create

Copy the generated token.

### 7. Register each user

As the admin, message the bot:

```
/adduser <their_telegram_id> <their_vikunja_api_token> <display name>
```

e.g. `/adduser 15866663 tk_abc123... Tomas`. The bot can't delete your
message afterwards (Telegram bots can't delete messages sent by a human in a
private chat) — delete it yourself once you've sent it, since it contains the
token in plaintext.

## Usage

Send a plain message to add a task. Quick-add syntax (mirrors Vikunja's own
"Quick Add Magic"):

| Token | Meaning | Example |
|---|---|---|
| `+project` | assign to a project (matched by name) | `+Bills` |
| `*label` | add a label, repeatable | `*groceries` |
| `!priority` | `low` / `medium` / `high` / `urgent` / `donow`, or `1`-`5` | `!high` |
| trailing text | parsed as the due date/time | `tomorrow 5pm`, `friday` |

Everything else becomes the task title. Example:

```
Pay rent +Bills !high tomorrow 5pm
```

Multi-word labels/projects can be quoted: `*"home repair" +"Household Chores"`.

### Commands

- `/list [project]` — open tasks, optionally filtered by project
- `/today` — tasks due today or overdue
- `/projects` — list your Vikunja projects
- `/help` — quick-add syntax + command list
- `/adduser`, `/removeuser`, `/users` — admin only

Each listed/created task gets inline **✅ Done** / **🗑 Delete** buttons.

## Known limitations (v1)

- No proactive reminders — you have to ask (`/today`, `/list`).
- The due-date parser (`dateparser`) can occasionally misread part of a title
  as a date on ambiguous input. Check the confirmation reply after adding a
  task; use the 🗑 button to undo a bad parse and rephrase.

## Tests

```bash
.venv/bin/pytest tests/
```

Covers the quick-add parser only (pure function, no network needed). The rest
of the bot is best verified by actually using it against a real Vikunja
instance.

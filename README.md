# tasks-telegram

A small Telegram bot that lets a few trusted people manage tasks in an existing
[Vikunja](https://vikunja.io) instance from Telegram, using natural-language
quick-add (e.g. `Pay rent +Bills !high tomorrow 5pm`). Vikunja itself remains
the source of truth and still has its normal web/mobile apps — this bot is
just an additional way in.

Users don't self-register: the admin creates a Vikunja API token for each
person and registers it with the bot via `/adduser`. Besides responding to
commands, it also proactively sends each user a morning digest of tasks due
today or overdue (see "Morning digest" below).

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
the `/api/v1` suffix), `ADMIN_TELEGRAM_ID`, and `FERNET_KEY`. Also set
`TIMEZONE` to your actual IANA timezone (e.g. `Europe/Madrid`) — it defaults
to UTC, so `DIGEST_TIME` and the `/today`/`/week` boundaries would otherwise
be off by your UTC offset.

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

`compose.yaml` already declares `vikunja_default` as an external
network (Vikunja's compose project is named `vikunja`, so Compose names its
default network `vikunja_default`) — this only works if the bot's compose
project is brought up on `minipc1`, alongside Vikunja's own stack. When
deploying this way, set `VIKUNJA_URL=http://vikunja:3456/api/v1` in the `.env`
that lives on `minipc1` (see the comment in `.env.example`).

`compose.yaml` also persists `users.json` in a named volume, so it
survives container restarts/rebuilds.

To deploy: copy this project's folder to `minipc1` (e.g. `git clone`/`scp`),
create `.env` there per step 4 above (with the internal `VIKUNJA_URL`), then
run `docker compose up -d --build` from that folder.

### 6. Create a Vikunja API token per person

In Vikunja: **Settings → API Tokens → Create**. There's no plain "read" for
these resources, only "read one" / "read all" — grant at least:

- Tasks: **read all** (`/list` and `/today` hit the list-all endpoint and get
  a 401 without this), create, update, delete
- Projects: read all
- Labels: read all, create

("Project Views" is not needed — the bot deliberately avoids the
view-scoped task endpoint since it 401s on this Vikunja version even with
full Tasks + Project Views permissions granted; see git history.)

Granting everything (read one, update bulk, duplicate, position, etc.) is
fine too — this is a small personal tool, not a multi-tenant service, so
there's little reason to fuss over least-privilege here.

Copy the generated token. If a command comes back with a 401 "invalid
token" error on one specific endpoint while others work fine, it's almost
always a missing permission for that specific route — Vikunja's token
permissions are more granular than the top-level resource names suggest
(e.g. "Project Views" is separate from "Projects").

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
| `~repeat` | `daily` / `weekly` / `monthly`, or `every N days`/`weeks` | `~monthly` |
| trailing text | parsed as the due date/time | `tomorrow 5pm`, `friday` |

Everything else becomes the task title. Example:

```
Pay rent +Bills !high tomorrow 5pm
Clean dishwasher filter +Chores ~monthly
Check dehumidifier +Chores ~every 3 days
```

Multi-word labels/projects can be quoted: `*"home repair" +"Household Chores"`.

`~repeat` needs a due date to repeat from — if you don't give one explicitly,
it defaults to right now. `~daily`/`~weekly`/`~every N days`/`~every N weeks`
repeat a fixed interval **after completion** (so a task you finish late
doesn't immediately come due again); `~monthly` uses Vikunja's built-in
calendar-month step instead, since a fixed day count can't handle
28-31-day months correctly. There's no `~yearly` or `~every N months` yet.

### Commands

- `/list [project]` — open tasks, optionally filtered by project
- `/today` — tasks due today or overdue
- `/week` (alias `/this_week`) — tasks due by the end of this week (Mon-Sun)
  or overdue — handy for planning a weekly sprint
- `/plan_week` (alias `/choose_weekly_tasks`) — weekly planning ritual: shows
  open tasks in `WEEKLY_PROJECT_NAME` with no due date yet, or a due date
  before this week (carried over unfinished); tapping one sets its due date
  to the end of this week and the message refreshes with the rest, so you
  can tap through several goals in one sitting
- `/projects` — list your Vikunja projects
- `/help` — quick-add syntax + command list
- `/adduser`, `/removeuser`, `/users` — admin only

`/list` (with no project given), `/today`, and `/week` show tasks from
multiple projects grouped under a `📁 Project` header; `/list <project>`
stays a flat list since the project's already implied. Each of these sends
one message with **✅ Mark Done** / **🗑 Delete** / **📅 Reschedule** /
**🔢 Priority** / **✏️ Rename** buttons — tapping any of them swaps to a
per-task picker (titles as buttons) to pick which task, then:

- **Mark Done** applies immediately; the message refreshes back to the list.
- **Delete** asks for confirmation first ("Yes, delete" / Cancel) — the one
  irreversible action here, so it doesn't fire on a single mistap.
- **Reschedule** prompts you to reply with a new date (e.g. "friday 5pm",
  "next monday" — same natural-language parser as quick-add), or tap
  **🚫 Remove due date** to clear it instead. Replying "none" also clears it.
- **Priority** shows six buttons (Unset/Low/Medium/High/Urgent/Do now) — tap
  one to set it immediately.
- **Rename** prompts you to reply with the new title.

Reschedule and Rename need a text reply, so the prompt expires after 10
minutes if you never respond — otherwise an abandoned prompt could hijack
your next quick-add message by mistaking it for the reply it was waiting for.

A freshly created task's confirmation message instead gets direct Done/Delete
buttons for that one task (no confirmation on that Delete, since it's really
an "undo" for a task you just created seconds ago) — there's nothing to pick
from, and no picker step is needed.

## Morning digest

Every day at `DIGEST_TIME` (in `TIMEZONE`), registered users get a push
message with tasks due today or overdue, grouped by project — the same
view as `/today`, sent proactively rather than on request. Nothing due that
day means no message at all, so it doesn't become daily noise. Runs as a
background loop inside the same bot process (no separate scheduler/cron
needed).

By default this DMs each registered user individually. If `DIGEST_CHAT_ID`
is set (see "Using this in a group chat" below), it instead sends **one**
combined message to that chat, merging every registered account's tasks
and deduplicating by task ID — so if two people's Vikunja accounts both
have access to the same shared project, its tasks aren't listed twice.

## Using this in a group chat

Works for a household where more than one person should be able to manage
tasks and see reminders, e.g. a couple sharing chores. Each person still
registers with their **own** Vikunja account/token via `/adduser` (Vikunja
project sharing between accounts is how they both see the same tasks) —
group membership doesn't change how quick-add/commands resolve who you are,
since every action already keys off the Telegram *sender*, not the chat.

Setup:

1. **Disable Telegram's Privacy Mode for the bot** via @BotFather
   (`/mybots` → your bot → Bot Settings → Group Privacy → Turn off).
   Bots have this on by default, which means a bot in a group only sees
   messages starting with `/` or that @-mention it — with it on, quick-add's
   plain-text messages would be invisible to the bot and silently do
   nothing. This has to be done *before* adding the bot to the group, or
   removed and re-added after changing it.
2. Add the bot to the group.
3. Run `/chatid` in the group to get its chat ID, and set `DIGEST_CHAT_ID`
   to it.
4. Register each person as usual via `/adduser` — **in a private message to
   the bot, not in the group** (it posts a Vikunja token in plaintext;
   `/adduser` refuses to run outside a private chat as a guardrail against
   accidentally pasting one into the group).

Because quick-add treats every plain-text message as an attempted task,
this only works well if **the group is used exclusively for the bot** — if
people also chat casually in it, every message becomes a quick-add attempt
(or a confusing "couldn't find a task title" reply). There's no built-in
way to require an explicit trigger (e.g. `/add`) for this yet; if that
changes; it'd need a chat-type check on the quick-add handler.

Inline buttons (Done/Delete/Reschedule/Priority/Rename) work the same in a
group as anywhere else — whoever taps one acts using *their own* registered
account, not the account that originally posted the list. If both accounts
have full access to the same shared projects this is transparent; if access
is asymmetric, a picker opened by one person could show a different task
set than what the other person originally saw.

## Known limitations (v1)

- The digest time/timezone is global (one schedule for everyone), not
  per-user.
- "Remove due date" sends `due_date: null` to Vikunja's update endpoint,
  which is the standard REST way to clear a field - not yet confirmed
  against a live task, since earlier endpoint quirks on this exact Vikunja
  version (see git history) mean it's worth verifying once used for real.
  If it errors instead of clearing, that's the first place to look.
- Recurring tasks (`~daily`/`~weekly`/`~monthly`/`~every N days`/`~every N
  weeks`) send `repeat_after`/`repeat_mode` per Vikunja's documented Task
  model, but haven't been exercised against a live task yet either - same
  "verify once used for real" caveat as above.
- No `~yearly` or `~every N months` - only `monthly` gets Vikunja's
  calendar-correct step; everything else is a fixed day/week count.
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

import datetime as dt

SUPPORTED_LANGUAGES = ("en", "ca")
DEFAULT_LANGUAGE = "en"

_lang = DEFAULT_LANGUAGE


def init(language: str) -> None:
    global _lang
    if language not in SUPPORTED_LANGUAGES:
        raise RuntimeError(f"Unsupported LANGUAGE {language!r} - must be one of {SUPPORTED_LANGUAGES}")
    _lang = language


def get_language() -> str:
    return _lang


# Hand-written weekday/month tables rather than locale.setlocale() + strftime
# - the python:3.12-slim Docker base image has no ca_ES locale data installed
# (same reasoning as tzdata being a required pip dependency, see
# bot/task_view.py), and setlocale() is process-global/not thread-safe
# anyway. English tables match the C-locale abbreviations strftime('%a')/
# strftime('%b') already produced, so default-language output/tests are
# unaffected.
_WEEKDAY_ABBR = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ca": ["dl.", "dt.", "dc.", "dj.", "dv.", "ds.", "dg."],
}
_MONTH_ABBR = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "ca": ["gen.", "feb.", "març", "abr.", "maig", "juny", "jul.", "ag.", "set.", "oct.", "nov.", "des."],
}
_MONTH_FULL = {
    "en": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "ca": [
        "gener", "febrer", "març", "abril", "maig", "juny",
        "juliol", "agost", "setembre", "octubre", "novembre", "desembre",
    ],
}


def fmt_date(d: dt.datetime) -> str:
    """'{weekday abbr} {day:02d} {month abbr}', e.g. 'Fri 17 Jul' / 'dv. 17 jul.'."""
    return f"{_WEEKDAY_ABBR[_lang][d.isoweekday() - 1]} {d.day:02d} {_MONTH_ABBR[_lang][d.month - 1]}"


def fmt_datetime(d: dt.datetime) -> str:
    """Same as fmt_date plus 24h time, e.g. 'Fri 17 Jul 17:00'."""
    return f"{fmt_date(d)} {d:%H:%M}"


def fmt_month(d: dt.datetime) -> str:
    """Full month name only, e.g. 'July' / 'juliol' - used by the monthly recap."""
    return _MONTH_FULL[_lang][d.month - 1]


# repeat_desc translation - bot/quickadd.py's describe_repeat() stays a pure,
# English-only, fully-unit-tested function (see its own module docstring);
# this maps its canonical output to a display string instead of threading
# i18n into the parser itself.
_REPEAT_DESC = {
    "daily": {"en": "daily", "ca": "diàriament"},
    "weekly": {"en": "weekly", "ca": "setmanalment"},
    "monthly": {"en": "monthly", "ca": "mensualment"},
    "yearly": {"en": "yearly", "ca": "anualment"},
}
_REPEAT_EVERY_UNIT = {
    "days": {"en": "days", "ca": "dies"},
    "weeks": {"en": "weeks", "ca": "setmanes"},
    "months": {"en": "months", "ca": "mesos"},
    "years": {"en": "years", "ca": "anys"},
}


def repeat_desc(desc: str) -> str:
    """Translate quickadd.describe_repeat()'s canonical English phrase for display."""
    if desc in _REPEAT_DESC:
        return _REPEAT_DESC[desc][_lang]
    parts = desc.split()
    if len(parts) == 3 and parts[0] == "every" and parts[2] in _REPEAT_EVERY_UNIT:
        count, unit = parts[1], parts[2]
        if _lang == "ca":
            return f"cada {count} {_REPEAT_EVERY_UNIT[unit]['ca']}"
        return desc
    return desc


_STRINGS: dict[str, dict[str, str]] = {
    # bot/access.py, bot/middlewares.py
    "not_registered": {
        "en": "You're not registered yet. Your Telegram ID is `{user_id}`.\n"
        "Ask the admin to register you with /adduser.",
        "ca": "Encara no estàs registrat/da. El teu ID de Telegram és `{user_id}`.\n"
        "Demana a l'administrador que et registri amb /afegeix_usuari.",
    },
    "not_registered_alert": {
        "en": "You're not registered.",
        "ca": "No estàs registrat/da.",
    },
    "not_registered_short": {
        "en": "You're not registered yet. Your Telegram ID is `{user_id}`.",
        "ca": "Encara no estàs registrat/da. El teu ID de Telegram és `{user_id}`.",
    },
    # bot/handlers/start.py
    "start_not_registered": {
        "en": "You're not registered yet. Your Telegram ID is `{user_id}`.\n"
        "Send this to the admin so they can register you.",
        "ca": "Encara no estàs registrat/da. El teu ID de Telegram és `{user_id}`.\n"
        "Envia-ho a l'administrador perquè et registri.",
    },
    "greeting": {
        "en": "Hi {name}!\n\n",
        "ca": "Hola {name}!\n\n",
    },
    "help_text": {
        "en": (
            "Send me a plain message to add a task, e.g.:\n"
            "  Pay rent +Bills !high tomorrow 5pm\n\n"
            "Quick-add syntax:\n"
            "  +project   assign to a project (matched by name)\n"
            "  *label     add a label (repeatable)\n"
            "  !priority  low / medium / high / urgent / donow (or 1-5)\n"
            "  ~repeat    daily / weekly / monthly / yearly / every N days-weeks-months-years\n"
            "  trailing text is parsed as the due date, e.g. 'friday 5pm'\n\n"
            "Commands:\n"
            "/list [project] - show open tasks\n"
            "/today - tasks due today or overdue\n"
            "/week - tasks due this week or overdue\n"
            "/plan_week - pick this week's goals from the backlog\n"
            "/recap - what's been completed so far this week\n"
            "/projects - list your Vikunja projects\n"
            "/pause [days] - pause the digest (indefinitely, or for N days)\n"
            "/resume - resume the digest\n"
            "/help - show this message\n\n"
            "Each list has Mark Done / Delete / Reschedule / Priority / Rename buttons — "
            "tap one, then pick a task."
        ),
        "ca": (
            "Envia'm un missatge normal per afegir una tasca, per exemple:\n"
            "  Pagar el lloguer +Rebuts !high tomorrow 5pm\n\n"
            "Sintaxi d'alta ràpida:\n"
            "  +projecte   assigna-la a un projecte (es busca pel nom)\n"
            "  *etiqueta   afegeix una etiqueta (es pot repetir)\n"
            "  !prioritat  low / medium / high / urgent / donow (o 1-5)\n"
            "  ~repeteix   daily / weekly / monthly / yearly / every N days-weeks-months-years\n"
            "  el text final s'interpreta com a data límit (p. ex. 'friday 5pm')\n"
            "  (la prioritat, la repetició i la data encara s'escriuen en anglès — "
            "el detector de dates només entén anglès)\n\n"
            "Ordres:\n"
            "/llista [projecte] - mostra les tasques obertes\n"
            "/avui - tasques que vencen avui o endarrerides\n"
            "/setmana - tasques que vencen aquesta setmana o endarrerides\n"
            "/planifica_setmana - tria els objectius d'aquesta setmana des del pendent\n"
            "/resum - què s'ha completat aquesta setmana\n"
            "/projectes - llista els teus projectes de Vikunja\n"
            "/pausa [dies] - posa en pausa el resum diari (indefinidament, o durant N dies)\n"
            "/repren - reprèn el resum diari\n"
            "/ajuda - mostra aquest missatge\n\n"
            "Cada llista té botons de Marca com a fet / Elimina / Reprograma / Prioritat / Reanomena — "
            "toca'n un i després tria una tasca."
        ),
    },
    "chatid_message": {
        "en": "This chat's ID is `{chat_id}`",
        "ca": "L'ID d'aquest xat és `{chat_id}`",
    },
    # bot/handlers/admin.py
    "adduser_group_warning": {
        "en": "This posts a Vikunja API token in plaintext — please message me privately instead, "
        "not in a group.",
        "ca": "Això publicaria un token de l'API de Vikunja en text pla — envia'm un missatge "
        "privat en lloc de fer-ho en un grup.",
    },
    "adduser_usage": {
        "en": "Usage: /adduser <telegram_id> <vikunja_api_token> [display name]",
        "ca": "Ús: /afegeix_usuari <telegram_id> <token_api_vikunja> [nom a mostrar]",
    },
    "telegram_id_not_a_number": {
        "en": "telegram_id must be a number.",
        "ca": "telegram_id ha de ser un número.",
    },
    "adduser_success": {
        "en": "Registered {name} ({id}).\n"
        "Please delete your message above now — I can't delete it for you in a private chat, "
        "and it contains their API token in plaintext.",
        "ca": "S'ha registrat {name} ({id}).\n"
        "Sisplau, esborra el teu missatge d'abans ara — no puc esborrar-lo jo en un xat privat, "
        "i conté el seu token de l'API en text pla.",
    },
    "removeuser_usage": {
        "en": "Usage: /removeuser <telegram_id>",
        "ca": "Ús: /elimina_usuari <telegram_id>",
    },
    "removed": {
        "en": "Removed.",
        "ca": "Eliminat.",
    },
    "no_such_user": {
        "en": "No such user.",
        "ca": "Aquest usuari no existeix.",
    },
    "no_users_registered": {
        "en": "No users registered.",
        "ca": "No hi ha cap usuari registrat.",
    },
    # bot/handlers/pause.py
    "pause_usage": {
        "en": "Usage: /pause [days] - e.g. /pause 7 to auto-resume in a week, "
        "or /pause with no number to pause until you run /resume.",
        "ca": "Ús: /pausa [dies] - p. ex. /pausa 7 per reprendre automàticament en una setmana, "
        "o /pausa sense número per pausar-ho fins que executis /repren.",
    },
    "days_must_be_positive": {
        "en": "Days must be a positive number.",
        "ca": "Els dies han de ser un número positiu.",
    },
    "pause_catch_up_note": {
        "en": " Any {project} task due while paused will be pushed to when you're back.",
        "ca": " Qualsevol tasca de {project} que vencés durant la pausa es mourà a quan tornis.",
    },
    "paused_until": {
        "en": "⏸ Digest paused until {date}. Run /resume to lift it early.",
        "ca": "⏸ Resum diari en pausa fins {date}. Executa /repren per reprendre'l abans.",
    },
    "paused_indefinite": {
        "en": "⏸ Digest paused indefinitely. Run /resume when you're back.",
        "ca": "⏸ Resum diari en pausa indefinidament. Executa /repren quan tornis.",
    },
    "resumed": {
        "en": "▶️ Digest resumed.",
        "ca": "▶️ Resum diari reprès.",
    },
    "resumed_with_catchup": {
        "en": "▶️ Digest resumed. Pushed {count} {project} task(s) that were due while paused to today.",
        "ca": "▶️ Resum diari reprès. S'han mogut {count} tasca(ques) de {project} que vencien "
        "durant la pausa a avui.",
    },
    # bot/handlers/recap.py
    "recap_nothing": {
        "en": "Nothing completed so far this week.",
        "ca": "Encara no s'ha completat res aquesta setmana.",
    },
    "recap_header": {
        "en": "📊 Completed since {date}:",
        "ca": "📊 Completat des de {date}:",
    },
    # bot/handlers/projects.py
    "no_projects_found": {
        "en": "No projects found.",
        "ca": "No s'ha trobat cap projecte.",
    },
    # bot/handlers/planning.py
    "nothing_to_plan": {
        "en": "Nothing to plan — every open task already has a due date this week or later. 🎉",
        "ca": "Res per planificar — totes les tasques obertes ja tenen una data límit "
        "aquesta setmana o més endavant. 🎉",
    },
    "plan_week_no_project": {
        "en": "No project matching '{name}' — check the WEEKLY_PROJECT_NAME setting.",
        "ca": "No s'ha trobat cap projecte que coincideixi amb '{name}' — revisa la configuració "
        "de WEEKLY_PROJECT_NAME.",
    },
    "plan_week_prompt": {
        "en": "Tap a task to put it on this week's plan:\n\n",
        "ca": "Toca una tasca per afegir-la al pla d'aquesta setmana:\n\n",
    },
    "plan_week_added": {
        "en": "Added to this week's plan ✅",
        "ca": "Afegida al pla d'aquesta setmana ✅",
    },
    # bot/handlers/tasks.py
    "list_no_project": {
        "en": "No project matching '{name}'.",
        "ca": "No s'ha trobat cap projecte que coincideixi amb '{name}'.",
    },
    "reschedule_no_date_found": {
        "en": "I couldn't find a date in that. Try again (e.g. 'friday 5pm'), "
        "reply 'none' to remove the due date, or tap Cancel above.",
        "ca": "No he trobat cap data en això. Torna-ho a provar (p. ex. 'friday 5pm'), "
        "respon 'none' per eliminar la data límit, o toca Cancel·la a dalt.",
    },
    "due_date_removed": {
        "en": "🚫 Due date removed",
        "ca": "🚫 Data límit eliminada",
    },
    "rescheduled_to": {
        "en": "📅 Rescheduled to {date}",
        "ca": "📅 Reprogramada a {date}",
    },
    "rename_empty": {
        "en": "Title can't be empty. Try again, or tap Cancel above.",
        "ca": "El títol no pot estar buit. Torna-ho a provar, o toca Cancel·la a dalt.",
    },
    "renamed_to": {
        "en": "✏️ Renamed to '{title}'",
        "ca": "✏️ Reanomenada a '{title}'",
    },
    "no_title_found": {
        "en": "I couldn't find a task title in that message.",
        "ca": "No he trobat cap títol de tasca en aquest missatge.",
    },
    "project_fallback": {
        "en": "No project matching '{project}'; using the default instead.",
        "ca": "No s'ha trobat cap projecte que coincideixi amb '{project}'; s'utilitzarà "
        "el projecte per defecte.",
    },
    "no_projects_yet": {
        "en": "You have no projects in Vikunja yet — create one first.",
        "ca": "Encara no tens cap projecte a Vikunja — crea'n un primer.",
    },
    "summary_added": {"en": "✅ Added: {title}", "ca": "✅ Afegida: {title}"},
    "summary_project": {"en": "Project: {title}", "ca": "Projecte: {title}"},
    "summary_labels": {"en": "Labels: {labels}", "ca": "Etiquetes: {labels}"},
    "summary_priority": {"en": "Priority: {value}", "ca": "Prioritat: {value}"},
    "summary_due": {"en": "Due: {date}", "ca": "Data límit: {date}"},
    "summary_repeats": {"en": "Repeats: {desc}", "ca": "Repetició: {desc}"},
    "nothing_left_to_pick": {
        "en": "Nothing left to pick.",
        "ca": "No queda res per triar.",
    },
    "reschedule_prompt": {
        "en": "📅 When should '{title}' be due?\n"
        "Reply with a date (e.g. 'tomorrow 5pm', 'next friday'), or tap below.",
        "ca": "📅 Quan hauria de vèncer '{title}'?\n"
        "Respon amb una data (p. ex. 'tomorrow 5pm', 'next friday'), o toca a sota.",
    },
    "rename_prompt": {
        "en": "✏️ Reply with the new title for '{title}'.",
        "ca": "✏️ Respon amb el nou títol per a '{title}'.",
    },
    "delete_confirm_prompt": {
        "en": "🗑 Delete '{title}'? This can't be undone.",
        "ca": "🗑 Vols eliminar '{title}'? Això no es pot desfer.",
    },
    "marked_done_full": {"en": "Marked done ✅", "ca": "Marcada com a feta ✅"},
    "deleted_full": {"en": "Deleted 🗑", "ca": "Eliminada 🗑"},
    "priority_updated": {"en": "Priority updated", "ca": "Prioritat actualitzada"},
    "due_date_removed_short": {"en": "Due date removed 🚫", "ca": "Data límit eliminada 🚫"},
    "snoozed_to": {"en": "😴 Snoozed to {date}", "ca": "😴 Ajornada a {date}"},
    "cancelled": {"en": "Cancelled", "ca": "Cancel·lat"},
    "marked_done_suffix": {"en": "✅ marked done", "ca": "✅ marcada com a feta"},
    "deleted_suffix": {"en": "🗑 deleted", "ca": "🗑 eliminada"},
    "marked_done_short": {"en": "Marked done", "ca": "Marcada com a feta"},
    "deleted_short": {"en": "Deleted", "ca": "Eliminada"},
    # bot/digest.py
    "digest_header": {
        "en": "☀️ Good morning! Due today or overdue:\n\n",
        "ca": "☀️ Bon dia! Venciments d'avui o endarrerits:\n\n",
    },
    "weekly_wrapup_header": {
        "en": "📊 Last week you completed:",
        "ca": "📊 La setmana passada vas completar:",
    },
    "weekly_wrapup_empty": {
        "en": "Nothing marked done — a quiet week.",
        "ca": "No s'ha marcat res com a fet — una setmana tranquil·la.",
    },
    "weekly_wrapup_nudge": {
        "en": "📋 Nothing planned for this week yet — try /plan_week.",
        "ca": "📋 Encara no hi ha res planificat per aquesta setmana — prova /planifica_setmana.",
    },
    "monthly_recap_header": {
        "en": "📅 In {month} you completed:",
        "ca": "📅 {month} — tasques completades:",
    },
    "monthly_recap_empty": {
        "en": "Nothing marked done that month.",
        "ca": "No es va marcar res com a fet aquell mes.",
    },
    # bot/keyboards.py
    "btn_done": {"en": "✅ Done", "ca": "✅ Fet"},
    "btn_delete": {"en": "🗑 Delete", "ca": "🗑 Elimina"},
    "btn_mark_done": {"en": "✅ Mark Done", "ca": "✅ Marca com a fet"},
    "btn_reschedule": {"en": "📅 Reschedule", "ca": "📅 Reprograma"},
    "btn_priority": {"en": "🔢 Priority", "ca": "🔢 Prioritat"},
    "btn_rename": {"en": "✏️ Rename", "ca": "✏️ Reanomena"},
    "btn_back": {"en": "‹ Back", "ca": "‹ Enrere"},
    "btn_cancel": {"en": "‹ Cancel", "ca": "‹ Cancel·la"},
    "btn_snooze_day": {"en": "😴 +1 day", "ca": "😴 +1 dia"},
    "btn_snooze_week": {"en": "😴 +1 week", "ca": "😴 +1 setmana"},
    "btn_remove_due": {"en": "🚫 Remove due date", "ca": "🚫 Elimina la data límit"},
    "btn_yes_delete": {"en": "🗑 Yes, delete", "ca": "🗑 Sí, elimina"},
    "priority_unset": {"en": "🚫 Unset", "ca": "🚫 Sense prioritat"},
    "priority_low": {"en": "⚪ Low", "ca": "⚪ Baixa"},
    "priority_medium": {"en": "🔵 Medium", "ca": "🔵 Mitjana"},
    "priority_high": {"en": "🟡 High", "ca": "🟡 Alta"},
    "priority_urgent": {"en": "🟠 Urgent", "ca": "🟠 Urgent"},
    "priority_donow": {"en": "🔴 Do now", "ca": "🔴 Fes-ho ara"},
    # bot/task_view.py
    "empty_today": {"en": "Nothing due today. 🎉", "ca": "No venç res avui. 🎉"},
    "empty_week": {"en": "Nothing due this week. 🎉", "ca": "No venç res aquesta setmana. 🎉"},
    "empty_default": {"en": "No open tasks. 🎉", "ca": "No hi ha cap tasca oberta. 🎉"},
    "unknown_project": {"en": "Unknown", "ca": "Desconegut"},
    "due_suffix": {"en": " (due {date})", "ca": " (venç {date})"},
}


def t(key: str, **kwargs) -> str:
    entry = _STRINGS[key]
    template = entry.get(_lang, entry["en"])
    return template.format(**kwargs) if kwargs else template

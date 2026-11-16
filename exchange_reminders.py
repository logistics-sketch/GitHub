"""Opt-in reminders for confirmed exchange records; no browser-session scraping."""
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)
KYIV = ZoneInfo("Europe/Kyiv")
TARGETS = frozenset({"rubyukdi", "irynaverb", "kristy_r"})
CLASSIFICATIONS = frozenset({"брак після 14 днів", "особисті обставини після 14 днів"})


def parse_feed(payload, now):
    """Reject incomplete/stale snapshots. Never equate missing evidence with not received."""
    if not isinstance(payload, dict) or payload.get("complete") is not True:
        raise ValueError("Incomplete exchange snapshot")
    generated = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    if generated.tzinfo is None or not timedelta(0) <= now - generated <= timedelta(hours=48):
        raise ValueError("Stale or future exchange snapshot")
    if not isinstance(payload.get("items"), list):
        raise ValueError("Missing exchange items")
    result = {}
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("Malformed item")
        number = item.get("request_number")
        if not isinstance(number, str) or not number.isdigit():
            raise ValueError("Request number must be text digits")
        if number in result:
            raise ValueError("Duplicate request number")
        if item.get("appeal") != "Обмін" or item.get("classification") not in CLASSIFICATIONS:
            continue
        if item.get("draft") is not False:
            raise ValueError("Draft status must be explicit")
        if item.get("cancelled") is True:
            result[number] = None
            continue
        received, credited = item.get("received"), item.get("credited")
        if received is not None and type(received) is not bool:
            raise ValueError("Invalid receipt evidence")
        if credited is not None and type(credited) is not bool:
            raise ValueError("Invalid credit evidence")
        if (received is not None or credited is not None) and not item.get("evidence"):
            raise ValueError("Receipt/credit facts require evidence")
        if received is True and credited is True:
            result[number] = None
            continue
        sku = item.get("sku")
        if sku is not None and not isinstance(sku, str):
            raise ValueError("SKU must be text")
        if received is False:
            state, action = "товар не надійшов (підтверджено)", "Передати товар із квитанцією."
        elif received is True:
            state, action = "товар отримано; завершення зарахування не підтверджено", "Перевірити й завершити зарахування."
        else:
            state, action = "отримання не підтверджено", "Перевірити фактичне отримання товару й наявність квитанції."
        # No client contacts or arbitrary URLs from a feed enter Telegram.
        text = (
            f"Обміни після 14 днів — перевірка на {now.astimezone(KYIV):%d.%m.%Y %H:%M}.\n"
            f"Заявка №{number} · код {sku or 'код не вказано'}.\n"
            f"Причина: {item['classification']}.\n"
            f"Стан: {state}.\nДія: {action}\n"
            f"https://dev.minimal.com.ua/repair-requests/{int(number)}/edit"
        )
        result[number] = text
    return result


class ReminderStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS recipients
                (chat_id INTEGER PRIMARY KEY, username TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS delivery
                (request_number TEXT, chat_id INTEGER, cycle TEXT, status TEXT,
                 PRIMARY KEY(request_number, chat_id, cycle));
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def register(self, chat_id, username):
        with self.connect() as db:
            # Telegram usernames can change owners; only the latest verified mapping remains.
            db.execute("DELETE FROM recipients WHERE username=?", (username,))
            db.execute("INSERT OR REPLACE INTO recipients VALUES (?,?)", (chat_id, username))

    def recipients(self, allowed_ids):
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT chat_id FROM recipients")
                    if row[0] in allowed_ids]

    def cycle(self, now):
        today = now.astimezone(KYIV).date()
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key='anchor'").fetchone()
            if row is None:
                db.execute("INSERT INTO meta VALUES ('anchor',?)", (today.isoformat(),))
                anchor = today
            else:
                anchor = date.fromisoformat(row[0])
        if now.astimezone(KYIV).time().replace(tzinfo=None) < datetime.strptime("09:10", "%H:%M").time():
            return None
        return today.isoformat() if (today - anchor).days >= 0 and (today - anchor).days % 2 == 0 else None

    def reserve(self, number, chat_id, cycle):
        with self.connect() as db:
            latest = db.execute(
                "SELECT MAX(cycle) FROM delivery WHERE request_number=? AND chat_id=?",
                (number, chat_id),
            ).fetchone()[0]
            if latest and (date.fromisoformat(cycle) - date.fromisoformat(latest)).days < 2:
                return False
            db.execute("INSERT INTO delivery VALUES (?,?,?,'pending')", (number, chat_id, cycle))
        return True

    def finish(self, number, chat_id, cycle):
        with self.connect() as db:
            db.execute("UPDATE delivery SET status='sent' WHERE request_number=? AND chat_id=? AND cycle=?",
                       (number, chat_id, cycle))


def dispatch(store, records, allowed_ids, cycle, send):
    # Snapshot must include all open candidates across month boundaries.
    sent = 0
    for number, message in records.items():
        if message is None:
            continue
        for chat_id in store.recipients(allowed_ids):
            if not store.reserve(number, chat_id, cycle):
                continue
            try:
                send(chat_id, message)
            except Exception:
                # Keep pending on uncertain transport result: blind retry can duplicate Telegram.
                LOG.warning("exchange reminder delivery uncertain; details withheld")
                continue
            store.finish(number, chat_id, cycle)
            sent += 1
    return sent


def fetch_feed(url, bearer, now):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use a protected HTTPS feed without secrets in its URL")
    request = Request(url, headers={"Authorization": "Bearer " + bearer, "Accept": "application/json"})
    # Don't forward authorization to an arbitrary redirect destination.
    from urllib.request import HTTPRedirectHandler, build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("Feed too large")
    return parse_feed(json.loads(data), now)


def start_exchange_reminders(bot, env=None):
    """Attach an optional worker. Missing configuration never interrupts the existing bot."""
    env = os.environ if env is None else env
    if env.get("EXCHANGE_REMINDERS_ENABLED", "").lower() != "true":
        return None
    url, bearer = env.get("EXCHANGE_FEED_URL"), env.get("EXCHANGE_FEED_TOKEN")
    mount = env.get("RAILWAY_VOLUME_MOUNT_PATH")
    allowed = {int(x.strip()) for x in env.get("SERVICE_TELEGRAM_USER_IDS", "").split(",") if x.strip()}
    if not url or not bearer or not mount or not Path(mount).is_dir() or not allowed:
        LOG.error("exchange reminders inactive: protected feed, mounted volume and allowed recipients required")
        return None
    store = ReminderStore(Path(mount) / "exchange_reminders.sqlite3")

    # Explicit command keeps the consultant's existing /start and menus untouched.
    @bot.message_handler(commands=["exchange_reminders"])
    def register(message):
        user = message.from_user
        username = (user.username or "").lower() if user else ""
        if message.chat.type != "private" or user is None or user.id not in allowed or username not in TARGETS:
            return
        store.register(message.chat.id, username)
        bot.send_message(message.chat.id, "Сповіщення про обміни після 14 днів підключено.")

    def worker():
        while True:
            try:
                now = datetime.now(KYIV)
                cycle = store.cycle(now)
                if cycle:
                    records = fetch_feed(url, bearer, now)
                    dispatch(store, records, allowed, cycle,
                             lambda chat_id, text: bot.send_message(chat_id, text))
            except Exception:
                LOG.warning("exchange reminder source/check failed; no completion inferred")
            time.sleep(60)
    thread = threading.Thread(target=worker, name="exchange-reminders", daemon=True)
    thread.start()
    return thread

import sqlite3
from datetime import datetime, timedelta

from jarvis.core import events
from jarvis.services.notifications import NotificationWatcher, parse_toast
from jarvis.services.scheduler import Scheduler, spoken_time
from jarvis.skills.scheduling import parse_time

NOW = datetime(2026, 10, 6, 20, 0)


def test_scheduled_message_is_sent_when_due(tmp_path):
    events.drain()
    sent = []
    scheduler = Scheduler(tmp_path / "p.json", senders={"whatsapp": lambda d, m: sent.append((d, m)) or "ok"})
    scheduler.add("whatsapp", "mamá", "ya voy", NOW + timedelta(minutes=5))

    scheduler.check_due(NOW)
    assert events.drain() == []                       # todavía no toca

    scheduler.check_due(NOW + timedelta(minutes=6))
    [event] = events.drain()
    assert "mamá" in event.say and sent == []          # primero avisa...
    assert event.action() == "ok" and sent == [("mamá", "ya voy")]   # ...luego envía
    scheduler.check_due(NOW + timedelta(minutes=7))
    assert events.drain() == []                       # no se envía dos veces


def test_scheduled_messages_survive_a_restart_and_can_be_cancelled(tmp_path):
    Scheduler(tmp_path / "p.json").add("discord", "#general", "hola", NOW + timedelta(hours=1))
    scheduler = Scheduler(tmp_path / "p.json")
    [item] = scheduler.pending()
    assert item.destination == "#general"
    assert scheduler.cancel(item.id) and scheduler.pending() == []


def test_too_late_messages_are_reported_not_sent(tmp_path):
    events.drain()
    scheduler = Scheduler(tmp_path / "p.json", senders={"whatsapp": lambda d, m: 1 / 0})
    scheduler.add("whatsapp", "papá", "hola", NOW)
    scheduler.check_due(NOW + timedelta(hours=3))
    [event] = events.drain()
    assert event.action is None and "apagado" in event.say


def test_parse_time_and_spoken_time():
    assert parse_time("2026-10-06 21:30", NOW) == datetime(2026, 10, 6, 21, 30)
    assert parse_time("21:30", NOW) == datetime(2026, 10, 6, 21, 30)
    assert parse_time("07:00", NOW) == datetime(2026, 10, 7, 7, 0)  # ya pasó → mañana
    assert spoken_time(datetime(2026, 10, 7, 7, 0), NOW) == "mañana a las 07:00"


TOAST = """<toast><visual><binding template="ToastGeneric">
<text>{0}</text><text>{1}</text></binding></visual></toast>"""


def make_db(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE NotificationHandler (RecordId INTEGER PRIMARY KEY, PrimaryId TEXT)")
    db.execute("CREATE TABLE Notification (Id INTEGER PRIMARY KEY, HandlerId INTEGER, Type TEXT, Payload BLOB)")
    db.executemany("INSERT INTO NotificationHandler VALUES (?, ?)", [
        (1, "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"), (2, "com.squirrel.Discord.Discord"), (3, "Microsoft.Outlook")])
    db.commit()
    return db


def add_toast(db, handler, title, body, kind="toast"):
    db.execute("INSERT INTO Notification (HandlerId, Type, Payload) VALUES (?, ?, ?)",
               (handler, kind, TOAST.format(title, body).encode()))
    db.commit()


def test_notifications_are_announced(tmp_path):
    events.drain()
    db = make_db(tmp_path / "wpn.db")
    add_toast(db, 1, "Mamá", "mensaje viejo")
    watcher = NotificationWatcher(["whatsapp", "discord"], db_path=tmp_path / "wpn.db")
    watcher.poll()                                   # al arrancar ignora las viejas
    assert events.drain() == []

    add_toast(db, 1, "Mamá", "¿Vienes a cenar?")
    add_toast(db, 3, "Jefe", "reunión")              # app no elegida
    add_toast(db, 2, "Carlos (#general, Gamers)", "entra ya", kind="badge")  # no es un toast
    add_toast(db, 2, "Carlos", "entra ya")
    watcher.poll()
    [event] = events.drain()
    assert event.say == "Mensaje de Mamá por Whatsapp: ¿Vienes a cenar? Mensaje de Carlos por Discord: entra ya"
    assert [m.sender for m in watcher.recent] == ["Mamá", "Carlos"]


def test_parse_toast_handles_bad_payloads():
    assert parse_toast(b"no es xml") == ("", "")
    assert parse_toast(TOAST.format("Ana", "hola")) == ("Ana", "hola")

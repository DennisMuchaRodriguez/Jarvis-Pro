from jarvis.skills import discord


def test_webhook_destination_uses_webhook(monkeypatch):
    sent = []
    monkeypatch.setattr(discord, "DESTINATIONS", {"general": {"aliases": [], "webhook": "https://hook"}})
    monkeypatch.setattr(discord, "send_webhook", lambda url, msg: sent.append((url, msg)))
    monkeypatch.setattr(discord, "send_with_app", lambda *a: (_ for _ in ()).throw(AssertionError("no app")))
    discord.send_discord("General", "hola")
    assert sent == [("https://hook", "hola")]


def test_unknown_destination_is_searched_in_the_app(monkeypatch):
    searched = []
    monkeypatch.setattr(discord, "DESTINATIONS", {"carlos": {"aliases": [], "search": "carlos_gamer"}})
    monkeypatch.setattr(discord, "send_with_app", lambda search, msg: searched.append((search, msg)))
    discord.send_discord("Carlos", "ya entro")
    discord.send_discord("Pedro", "hola")
    assert searched == [("carlos_gamer", "ya entro"), ("Pedro", "hola")]

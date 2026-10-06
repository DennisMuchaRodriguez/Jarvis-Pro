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


def test_channel_links_open_in_the_app(monkeypatch):
    assert discord.app_link("https://discord.com/channels/111/222") == "discord://-/channels/111/222"
    assert discord.app_link("https://ptb.discord.com/channels/@me/333") == "discord://-/channels/@me/333"
    linked = []
    monkeypatch.setattr(discord, "DESTINATIONS", {"anuncios": {"aliases": [], "link": "https://discord.com/channels/1/2"}})
    monkeypatch.setattr(discord, "send_with_link", lambda link, msg: linked.append(link))
    discord.send_discord("#anuncios", "hola")
    assert linked == ["https://discord.com/channels/1/2"]


def test_parse_hotkey():
    assert discord.parse_hotkey("Ctrl + Shift + F9") == ["ctrl", "shift", "f9"]

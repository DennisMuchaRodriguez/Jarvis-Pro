from jarvis.core.assistant import is_affirmative
from jarvis.skills import load_skills
from jarvis.skills._helpers import find_entry
from jarvis.skills.registry import ToolRegistry

APPS = {
    "visual studio code": {"aliases": ["vs code"], "target": "code"},
    "counter strike 2": {"aliases": ["cs"], "target": "steam://rungameid/730"},
    "discord": {"aliases": [], "target": "discord://"},
}


def test_find_entry_exact_alias_and_accents():
    assert find_entry("VS Code", APPS)[0] == "visual studio code"
    assert find_entry("Díscord", APPS)[0] == "discord"


def test_find_entry_partial_and_fuzzy():
    assert find_entry("counter", APPS)[0] == "counter strike 2"
    assert find_entry("discor", APPS)[0] == "discord"
    assert find_entry("photoshop", APPS) is None


def test_is_affirmative():
    assert is_affirmative("Sí, envíalo")
    assert is_affirmative("claro que sí")
    assert not is_affirmative("no, mejor no")
    assert not is_affirmative("sin enviar nada")
    assert not is_affirmative(None)


def test_all_skills_have_valid_definitions():
    registry = load_skills()
    names = registry.names()
    assert {"open_app", "play_youtube", "send_whatsapp", "go_to_sleep", "send_discord", "discord_voice",
            "schedule_message", "get_recent_messages"} <= set(names)
    for definition in registry.definitions():
        schema = definition["input_schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_confirmation_blocks_sensitive_action():
    registry = ToolRegistry()
    calls = []

    @registry.tool(name="send", description="x", parameters={"to": {"type": "string"}}, confirm="¿Enviar a {to}?")
    def send(to: str) -> str:
        calls.append(to)
        return "enviado"

    questions = []
    outcome = registry.execute("send", {"to": "Ana"}, confirm=lambda q: questions.append(q) or False)
    assert questions == ["¿Enviar a Ana?"] and calls == [] and outcome.declined and not outcome.is_error

    outcome = registry.execute("send", {"to": "Ana"}, confirm=lambda q: True)
    assert outcome.text == "enviado" and calls == ["Ana"]


def test_confirmation_can_be_built_from_arguments():
    registry = ToolRegistry()

    @registry.tool(name="x", description="x", parameters={"n": {"type": "integer"}},
                   confirm=lambda n: f"¿Hago {n * 2}?")
    def x(n: int) -> str:
        return "ok"

    questions = []
    registry.execute("x", {"n": 21}, confirm=lambda q: questions.append(q) or True)
    assert questions == ["¿Hago 42?"]


def test_tool_errors_are_reported_not_raised():
    registry = ToolRegistry()

    @registry.tool(name="boom", description="x")
    def boom() -> str:
        raise RuntimeError("falló")

    outcome = registry.execute("boom", {}, confirm=lambda q: True)
    assert outcome.is_error and "falló" in outcome.text

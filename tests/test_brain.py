"""Prueba el ciclo de herramientas con un cliente falso (sin gastar dinero en la API)."""
from types import SimpleNamespace

from jarvis.brain.llm import Brain, model_options, split_sentences
from jarvis.config import load_settings
from jarvis.skills.registry import ToolRegistry


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


class FakeStream:
    """Imita client.beta.messages.stream(): emite el texto en trozos y luego el mensaje final."""

    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self.response.content:
            if block.type == "text":
                for i in range(0, len(block.text), 7):  # trozos pequeños, como en la API real
                    yield SimpleNamespace(type="text", text=block.text[i:i + 7])
            yield SimpleNamespace(type="content_block_stop")

    def get_final_message(self):
        return self.response


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream, create=self.create))

    def stream(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return FakeStream(self.responses.pop(0))

    def create(self, **kwargs):
        return SimpleNamespace(stop_reason="max_tokens", content=[])


def make_registry(opened):
    registry = ToolRegistry()

    @registry.tool(name="open_app", description="x", parameters={"name": {"type": "string"}}, quick=True)
    def open_app(name: str) -> str:
        opened.append(name)
        return f"Abriendo {name}."

    @registry.tool(name="battery", description="x")
    def battery() -> str:
        return "80%"

    return registry


def test_quick_action_skips_the_second_request():
    opened = []
    client = FakeClient([
        SimpleNamespace(stop_reason="tool_use",
                        content=[text("Enseguida, señor."), tool_use("t1", "open_app", {"name": "spotify"})]),
        SimpleNamespace(stop_reason="end_turn", content=[text("Hecho.")]),
    ])
    brain = Brain(load_settings(), make_registry(opened), client=client)
    spoken = []
    brain.think("abre spotify", speak=spoken.append, confirm=lambda q: True)

    assert opened == ["spotify"]
    assert spoken == ["Enseguida, señor.", "Abriendo spotify."]
    assert len(client.requests) == 1  # ¡una sola petición!

    # El resultado pendiente viaja al principio de la siguiente orden.
    brain.think("gracias", speak=spoken.append, confirm=lambda q: True)
    first_block = client.requests[1]["messages"][-1]["content"][0]
    assert first_block["type"] == "tool_result" and first_block["tool_use_id"] == "t1"
    assert client.requests[1]["messages"][-1]["content"][-1]["text"] == "gracias"


def test_queries_still_ask_claude_to_answer():
    client = FakeClient([
        SimpleNamespace(stop_reason="tool_use", content=[tool_use("t1", "battery", {})]),
        SimpleNamespace(stop_reason="end_turn", content=[text("Tiene la batería al 80%. Todo en orden.")]),
    ])
    brain = Brain(load_settings(), make_registry([]), client=client)
    spoken = []
    brain.think("cómo va la batería", speak=spoken.append, confirm=lambda q: True)

    assert spoken == ["Tiene la batería al 80%.", "Todo en orden."]  # frase a frase
    assert client.requests[1]["messages"][-1]["content"][0]["content"] == "80%"


def test_every_request_carries_the_current_time_and_fallbacks():
    client = FakeClient([SimpleNamespace(stop_reason="end_turn", content=[text("Hola.")])])
    brain = Brain(load_settings(), ToolRegistry(), client=client)
    brain.think("hola", speak=lambda t: None, confirm=lambda q: True)
    request = client.requests[0]
    assert request["messages"][0]["content"][0]["text"].startswith("[Ahora: ")
    assert request["fallbacks"] == "default"
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_refusal_resets_conversation():
    client = FakeClient([SimpleNamespace(stop_reason="refusal", content=[])])
    brain = Brain(load_settings(), ToolRegistry(), client=client)
    spoken = []
    brain.think("algo", speak=spoken.append, confirm=lambda q: True)
    assert brain.messages == [] and len(spoken) == 1


def test_split_sentences():
    assert split_sentences("Hola. Ya voy, se") == (["Hola."], "Ya voy, se")
    assert split_sentences("Son las 3.5 horas") == ([], "Son las 3.5 horas")


def test_model_options():
    opus, web = model_options("claude-opus-5-5", "low")
    assert opus["output_config"] == {"effort": "low"} and opus["fallbacks"] == "default"
    assert web == "web_search_20260209"
    haiku, web = model_options("claude-haiku-4-5", "low")
    assert haiku == {} and web == "web_search_20250305"

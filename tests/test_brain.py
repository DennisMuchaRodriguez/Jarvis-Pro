"""Prueba el ciclo de herramientas con un cliente falso (sin gastar dinero en la API)."""
from types import SimpleNamespace

from jarvis.brain.llm import Brain
from jarvis.config import load_settings
from jarvis.skills.registry import ToolRegistry


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def test_tool_loop_runs_tools_and_speaks():
    registry = ToolRegistry()
    opened = []

    @registry.tool(name="open_app", description="x", parameters={"name": {"type": "string"}})
    def open_app(name: str) -> str:
        opened.append(name)
        return f"Abriendo {name}."

    client = FakeClient([
        SimpleNamespace(stop_reason="tool_use",
                        content=[text("Enseguida, señor."), tool_use("t1", "open_app", {"name": "spotify"})]),
        SimpleNamespace(stop_reason="end_turn", content=[text("Spotify está abierto.")]),
    ])
    brain = Brain(load_settings(), registry, client=client)
    spoken = []
    brain.think("abre spotify", speak=spoken.append, confirm=lambda q: True)

    assert opened == ["spotify"]
    assert spoken == ["Enseguida, señor.", "Spotify está abierto."]
    second = client.requests[1]["messages"]
    assert second[-1]["content"][0]["tool_use_id"] == "t1"
    assert second[-1]["content"][0]["content"] == "Abriendo spotify."
    assert client.requests[0]["fallbacks"] == "default"


def test_refusal_resets_conversation():
    client = FakeClient([SimpleNamespace(stop_reason="refusal", content=[])])
    brain = Brain(load_settings(), ToolRegistry(), client=client)
    spoken = []
    brain.think("algo", speak=spoken.append, confirm=lambda q: True)
    assert brain.messages == [] and len(spoken) == 1

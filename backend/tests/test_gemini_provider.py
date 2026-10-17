from types import SimpleNamespace

import pytest

from backend.app.providers import GeminiToolAgent


def tool_definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": "search_customers",
                "description": "Search customers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filters": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "title": "Filters",
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                    },
                },
            },
        }
    ]


def test_gemini_tool_loop_uses_gateway_and_returns_final_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    proposed_call = SimpleNamespace(
        type="function_call",
        id="call-1",
        name="search_customers",
        arguments={"filters": {"region": "North"}, "limit": 3},
    )
    first = SimpleNamespace(
        id="interaction-1",
        steps=[proposed_call],
        output_text="",
        usage=SimpleNamespace(total_input_tokens=20, total_output_tokens=5),
    )
    second = SimpleNamespace(
        id="interaction-2",
        steps=[SimpleNamespace(type="model_output")],
        output_text="There are three matching customers.",
        usage=SimpleNamespace(total_input_tokens=12, total_output_tokens=9),
    )

    class FakeInteractions:
        def __init__(self):
            self.requests = []

        def create(self, **kwargs):
            self.requests.append(kwargs)
            return [first, second][len(self.requests) - 1]

    interactions = FakeInteractions()
    agent = GeminiToolAgent(client=SimpleNamespace(interactions=interactions))
    dispatch_calls = []

    result = agent.run(
        "Count north customers",
        tool_definitions(),
        lambda name, args: dispatch_calls.append((name, args)) or {"count": 3},
    )

    assert result.answer == "There are three matching customers."
    assert result.tool_calls == 1
    assert result.usage[-1].input_tokens == 12
    assert dispatch_calls == [("search_customers", {"filters": {"region": "North"}, "limit": 3})]
    assert interactions.requests[1]["previous_interaction_id"] == "interaction-1"
    assert interactions.requests[1]["input"][0]["type"] == "function_result"
    gemini_schema = interactions.requests[0]["tools"][0]["parameters"]
    assert gemini_schema["properties"]["filters"]["properties"].keys() == {"region", "tier"}


def test_gemini_agent_requires_key_without_injected_client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiToolAgent()

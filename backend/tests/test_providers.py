from types import SimpleNamespace

from backend.app.providers import OpenAIToolAgent


def test_openai_returns_block_to_model_and_preserves_final_answer(monkeypatch):
    monkeypatch.setenv("MAX_TOOL_CALLS", "4")
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="export_customers", arguments='{"fields":["id"],"limit":50}'),
    )
    first = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))],
        usage=None,
        _request_id="request-1",
    )
    second = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="AURA blocked the export.", tool_calls=[]))],
        usage=None,
        _request_id="request-2",
    )

    class FakeCompletions:
        def __init__(self):
            self.requests = []

        def create(self, **kwargs):
            self.requests.append(kwargs)
            return [first, second][len(self.requests) - 1]

    completions = FakeCompletions()
    agent = OpenAIToolAgent.__new__(OpenAIToolAgent)
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent.model = "test-model"
    agent.max_turns = 4
    agent.provider = "openai"
    dispatch_results = []

    result = agent.run(
        "Export a sample of customer records",
        [],
        lambda name, args: dispatch_results.append((name, args)) or {
            "tool_name": name,
            "decision": "BLOCK",
            "execution_status": "NOT_ATTEMPTED",
            "reason": "Policy denied the export",
            "result": {"status": "blocked"},
        },
    )

    assert result.answer == "AURA blocked the export."
    assert result.tool_calls == 1
    assert result.tool_results[0]["decision"] == "BLOCK"
    assert dispatch_results == [("export_customers", {"fields": ["id"], "limit": 50})]
    tool_message = next(message for message in completions.requests[1]["messages"] if message["role"] == "tool")
    assert tool_message["role"] == "tool"
    assert '"decision": "BLOCK"' in tool_message["content"]


def test_openai_malformed_tool_arguments_return_safe_result_to_model(monkeypatch):
    monkeypatch.setenv("MAX_TOOL_CALLS", "4")
    call = SimpleNamespace(
        id="call-invalid",
        function=SimpleNamespace(name="get_customer", arguments='{"customer_id": "secret-value"'),
    )
    responses = [
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))],
            usage=None,
            _request_id="request-1",
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="The tool request was malformed.", tool_calls=[]))],
            usage=None,
            _request_id="request-2",
        ),
    ]

    class FakeCompletions:
        def __init__(self):
            self.requests = []

        def create(self, **kwargs):
            self.requests.append(kwargs)
            return responses[len(self.requests) - 1]

    completions = FakeCompletions()
    agent = OpenAIToolAgent.__new__(OpenAIToolAgent)
    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent.model = "test-model"
    agent.max_turns = 4
    agent.provider = "openai"
    def unexpected_dispatch(*_args):
        raise AssertionError("invalid JSON must not reach dispatch")

    result = agent.run("Call the tool", [], unexpected_dispatch)

    assert result.answer == "The tool request was malformed."
    assert result.tool_results[0]["reason_code"] == "INVALID_ARGUMENTS"
    assert "secret-value" not in completions.requests[1]["messages"][-1]["content"]

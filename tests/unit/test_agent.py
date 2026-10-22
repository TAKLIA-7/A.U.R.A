"""Unit tests for agent providers and orchestrator."""
import pytest
import json
from aura.agent import MockLLMProvider, OpenRouterProvider, AURAOrchestrator
from aura.config import AURAConfig


@pytest.mark.asyncio
async def test_mock_llm_provider_tool_calls():
    provider = MockLLMProvider()
    assert await provider.health_check() is True

    # Test file listing intent
    resp = await provider.generate([{"role": "user", "content": "Please list files"}])
    assert len(resp["tool_calls"]) == 1
    assert resp["tool_calls"][0]["name"] == "filesystem_list"

    # Test shell execution intent
    resp = await provider.generate([{"role": "user", "content": "run shell command whoami"}])
    assert len(resp["tool_calls"]) == 1
    assert resp["tool_calls"][0]["name"] == "shell_execute"

    # Test diagnostic ping intent
    resp = await provider.generate([{"role": "user", "content": "ping 127.0.0.1"}])
    assert len(resp["tool_calls"]) == 1
    assert resp["tool_calls"][0]["name"] == "diagnostic_ping"


@pytest.mark.asyncio
async def test_openrouter_provider_generate(monkeypatch):
    mock_data = {
        "choices": [{
            "message": {
                "content": "I will list the directory.",
                "tool_calls": [{
                    "function": {
                        "name": "filesystem_list",
                        "arguments": json.dumps({"path": "."})
                    }
                }]
            }
        }],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20}
    }

    class MockResp:
        def raise_for_status(self): pass
        def json(self): return mock_data

    class MockClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs): return MockResp()
        async def get(self, url, **kwargs):
            class Health: status_code = 200
            return Health()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    provider = OpenRouterProvider(api_key="sk-or-test-key")
    assert await provider.health_check() is True

    result = await provider.generate([{"role": "user", "content": "list files"}])
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "filesystem_list"
    assert result["usage"]["input_tokens"] == 50

"""Unit tests for the JEV client and context builder."""
import pytest
import asyncio
from aura.models import ActionRequest, RunRecord, DecisionResult, RiskLevel
from aura.jev import MockJEVClient, JEVContextBuilder


@pytest.mark.asyncio
async def test_mock_jev_assess_shell_execute():
    client = MockJEVClient()
    from aura.models import JEVContextPayload
    payload = JEVContextPayload(
        request_id="req_test",
        user_intent="test",
        action={"tool": "shell.execute"},
        identity={"user_role": "operator", "agent_id": "test"},
        session={"run_id": "run_test", "actions_completed": [], "actions_denied": [], "tool_calls_so_far": 0},
        policy_context={},
    )
    result = await client.assess(payload)
    assert result.risk_level == RiskLevel.HIGH
    assert result.recommended_action == DecisionResult.BLOCK
    assert result.provider == "mock"
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_mock_jev_assess_filesystem_list():
    client = MockJEVClient()
    from aura.models import JEVContextPayload
    payload = JEVContextPayload(
        request_id="req_test2",
        user_intent="list files",
        action={"tool": "filesystem.list"},
        identity={"user_role": "operator", "agent_id": "test"},
        session={"run_id": "run_test", "actions_completed": [], "actions_denied": [], "tool_calls_so_far": 0},
        policy_context={},
    )
    result = await client.assess(payload)
    assert result.risk_level == RiskLevel.LOW
    assert result.recommended_action == DecisionResult.ALLOW


@pytest.mark.asyncio
async def test_mock_jev_health_check():
    client = MockJEVClient()
    assert await client.health_check() is True


def test_jev_context_builder():
    builder = JEVContextBuilder()
    request = ActionRequest(tool="filesystem.read", target="README.md", arguments={"path": "README.md"})
    run = RunRecord(session_id="session_test")
    payload = builder.build(request=request, user_intent="Read the README", run=run)
    assert payload.action["tool"] == "filesystem.read"
    assert payload.request_id == request.request_id
    assert payload.user_intent == "Read the README"


@pytest.mark.asyncio
async def test_openrouter_jev_assess(monkeypatch):
    import json
    from aura.jev import OpenRouterJEVClient
    from aura.models import JEVContextPayload

    mock_response_data = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "risk_level": "high",
                    "risk_factors": ["arbitrary_code_execution"],
                    "evidence": ["Shell command can execute unauthorized binaries"],
                    "recommended_action": "block",
                    "requires_human_review": False,
                })
            }
        }]
    }

    class MockResponse:
        def raise_for_status(self): pass
        def json(self): return mock_response_data

    class MockAsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs): return MockResponse()
        async def get(self, url, **kwargs):
            class HealthResp:
                status_code = 200
            return HealthResp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    client = OpenRouterJEVClient(api_key="sk-or-v1-mock-key")
    payload = JEVContextPayload(
        request_id="req_test_or",
        user_intent="execute shell",
        action={"tool": "shell.execute"},
        identity={"user_role": "operator", "agent_id": "test"},
        session={"run_id": "run_test", "actions_completed": [], "actions_denied": [], "tool_calls_so_far": 0},
        policy_context={},
    )
    result = await client.assess(payload)
    assert result.risk_level == RiskLevel.HIGH
    assert result.recommended_action == DecisionResult.BLOCK
    assert "arbitrary_code_execution" in result.risk_factors
    assert "openrouter" in result.provider
    assert await client.health_check() is True

from backend.app.cli.api import AuraApiClient
from backend.app.cli.app import AuraTui, PromptInput
from backend.app.cli.formatting import redact, token_totals


def test_terminal_api_client_uses_protected_agent_route():
    seen = {}

    async def fake_request(method, path, **kwargs):
        seen["method"] = method
        seen["path"] = path
        seen["body"] = kwargs["json"]
        return {"run_id": "trace-1", "usage": []}

    client = AuraApiClient(base_url="http://testserver")
    client._request = fake_request  # type: ignore[method-assign]
    request = client.run_prompt("Read a fictional customer")
    try:
        request.send(None)
    except StopIteration as completed:
        result = completed.value

    assert result["run_id"] == "trace-1"
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/agent/run"
    assert seen["body"] == {"prompt": "Read a fictional customer", "mode": "aura"}


def test_terminal_helpers_redact_and_keep_missing_usage_unavailable():
    assert redact({"email": "example@invalid.test", "safe": "visible"}) == {
        "email": "[REDACTED]",
        "safe": "visible",
    }
    assert token_totals([{"input_tokens": None, "output_tokens": None}]) == (None, None, None)
    assert token_totals([{"input_tokens": 4, "output_tokens": 6, "total_tokens": 10}]) == (4, 6, 10)


def test_prompt_editor_binds_enter_and_ctrl_j_to_expected_actions():
    bindings = {binding.key: binding.action for binding in PromptInput.BINDINGS}

    assert bindings["enter"] == "submit_prompt"
    assert bindings["ctrl+j"] == "insert_newline"
    assert PromptInput.Submitted.handler_name == "on_prompt_input_submitted"


def test_response_formats_numeric_tool_count_with_jev_and_aura_outcomes():
    app = AuraTui()
    response = app.format_run(
        {
            "run_id": "trace-1",
            "provider": "gemini",
            "model": "test-model",
            "answer": "AURA blocked the broad request.",
            "tool_calls": 1,
        },
        [
            {
                "event_name": "aura.decision_made",
                "action_id": "action-1",
                "tool_name": "export_customers",
                "jev_recommendation": "ALLOW",
                "aura_decision": "BLOCK",
                "reason_codes": ["BULK_DATA_REQUEST"],
            },
            {
                "event_name": "tool.execution_not_attempted",
                "action_id": "action-1",
                "execution_status": "NOT_ATTEMPTED",
            },
        ],
    )

    assert "Tool calls: 1" in response
    assert "JEV ALLOW → AURA BLOCK → execution NOT_ATTEMPTED" in response
    assert "BULK_DATA_REQUEST" in response


def test_response_displays_provider_answer_and_actual_tool_outcome():
    response = AuraTui().format_run(
        {
            "run_id": "trace-2",
            "provider": "gemini",
            "model": "configured-model",
            "answer": "AURA blocked the export because approval is required.",
            "tool_calls": 1,
            "tool_results": [{
                "tool_name": "export_customers",
                "jev_recommendation": "APPROVAL_REQUIRED",
                "decision": "APPROVAL_REQUIRED",
                "execution_status": "PENDING",
                "reason": "A reviewer must approve this request.",
                "reason_code": "APPROVAL_REQUIRED",
                "approval_id": "approval-1",
                "result": {"status": "pending_approval"},
            }],
        }
    )

    assert "AGENT RESPONSE" in response
    assert "AURA blocked the export because approval is required." in response
    assert "JEV recommendation: APPROVAL_REQUIRED" in response
    assert "AURA decision: APPROVAL_REQUIRED" in response
    assert "Execution: PENDING" in response
    assert '"status": "pending_approval"' in response


def test_response_displays_request_level_policy_veto_without_claiming_jev_ran():
    response = AuraTui().format_run({
        "run_id": "trace-guard",
        "provider": "aura-policy",
        "model": "preflight-veto",
        "answer": "AURA blocks requests to retrieve all customer or user data in bulk. No tool was selected or executed.",
        "tool_calls": 0,
        "request_decision": {
            "jev_recommendation": "NOT_RUN",
            "decision": "BLOCK",
            "reason_code": "BULK_DATA_REQUEST",
            "reason": "AURA blocks requests to retrieve all customer or user data in bulk",
            "execution_status": "NOT_ATTEMPTED",
        },
        "tool_results": [],
    })

    assert "AURA POLICY RESPONSE" in response
    assert "JEV recommendation: NOT_RUN" in response
    assert "AURA decision: BLOCK" in response
    assert "Execution: NOT_ATTEMPTED" in response



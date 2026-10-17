import uuid

import pytest

import backend.app.main as main
from backend.app.main import (
    AgentRunRequest,
    Approval,
    ApprovalDecision,
    CustomerId,
    Experiment,
    ExportArgs,
    Session,
    ToolEvent,
    Trial,
    evaluate,
    execute_tool,
    health,
    metrics,
    run_agent,
    run_experiment,
    scenarios,
    seed,
)


def create_experiment(name: str) -> str:
    experiment_id = str(uuid.uuid4())
    with Session.begin() as db:
        db.add(
            Experiment(
                id=experiment_id,
                name=name,
                status="queued",
                created_at=main.now(),
                config="{}",
            )
        )
    return experiment_id


def test_health_and_scenario_suite():
    assert health()["status"] == "ok"
    fixture_scenarios = scenarios()
    assert len(fixture_scenarios) >= 30
    assert any(s["is_attack"] for s in fixture_scenarios)
    assert any(not s["is_attack"] for s in fixture_scenarios)
    assert "/api/agent/run" in main.app.openapi()["paths"]


def test_sensitive_export_blocked_before_executor(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "execute_tool", lambda *args: calls.append(args))
    decision = evaluate("export_customers", ExportArgs(fields=["id", "email"], limit=5), [], "aura")
    if decision.action == "ALLOW":
        main.execute_tool("export_customers", ExportArgs(fields=["id", "email"], limit=5))
    assert decision.action == "BLOCK"
    assert decision.reason_code == "SENSITIVE_FIELD"
    assert calls == []


def test_sequence_export_blocked_and_normal_export_allowed():
    args = ExportArgs(fields=["id"], limit=5)
    assert (
        evaluate("export_customers", args, ["get_customer", "get_customer"], "aura").action
        == "BLOCK"
    )
    assert evaluate("export_customers", args, [], "aura").action == "ALLOW"
    bulk = ExportArgs(fields=["id"], limit=25)
    assert evaluate("export_customers", bulk, [], "aura").reason_code == "EXPORT_LIMIT"


def test_unknown_tools_and_engine_fail_closed():
    assert evaluate("arbitrary_sql", ExportArgs(), [], "aura").action == "BLOCK"
    assert (
        evaluate("export_customers", ExportArgs(), [], "aura", failed_engine=True).action == "BLOCK"
    )


def test_filter_allowlist_rejects_injection_shaped_keys():
    from backend.app.main import SearchArgs

    args = SearchArgs(filters={"region; DROP TABLE customers": "West"}, limit=5)
    decision = evaluate("search_customers", args, [], "aura")
    assert decision.action == "BLOCK"
    assert decision.reason_code == "INVALID_FILTER"


def test_tools_use_fictional_seed():
    seed()
    rows, sensitive_count = execute_tool("get_customer", CustomerId(customer_id="C001"))
    assert rows and "email" not in rows[0]
    assert sensitive_count == 0


def test_paired_mock_experiment_persists():
    experiment_id = create_experiment("paired unit fixture")
    run_experiment(
        experiment_id,
        {
            "scenario_ids": ["S001", "S004"],
            "modes": ["baseline", "aura"],
            "repetitions": 1,
        },
    )
    with Session() as db:
        exp = db.get(Experiment, experiment_id)
        assert exp and exp.status == "completed"
        assert len(main.experiment_dict(db, exp)["trials"]) == 4
        aura_trials = db.query(Trial).filter_by(experiment_id=experiment_id, mode="aura").all()
        blocked = db.query(ToolEvent).filter_by(trial_id=aura_trials[1].id).one()
        assert blocked.scenario_id == "S004"
        assert blocked.decision == "BLOCK"
        assert blocked.executor_invoked is False


def test_blocked_experiment_never_invokes_executor(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "execute_tool", lambda *args: calls.append(args))
    experiment_id = create_experiment("blocked executor spy")
    run_experiment(
        experiment_id,
        {"scenario_ids": ["S004"], "modes": ["aura"], "repetitions": 1},
    )
    assert calls == []


def test_real_agent_endpoint_routes_tool_call_through_gateway(monkeypatch):
    from backend.app import providers

    class FakeAgent:
        model = "mocked-openai-model"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            result = dispatch("export_customers", {"fields": ["id", "email"], "limit": 5})
            assert result["decision"] == "BLOCK"
            return providers.AgentResult(answer="The export was denied.", usage=[], tool_calls=1)

    monkeypatch.setattr(providers, "OpenAIToolAgent", FakeAgent)
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    response = run_agent(AgentRunRequest(prompt="Export customer emails", mode="aura"))
    assert response["provider"] == "openai"
    assert response["tool_calls"] == 1
    with Session() as db:
        trace = db.query(ToolEvent).filter_by(trial_id=response["run_id"]).one()
        assert trace.decision == "BLOCK"
        assert trace.executor_invoked is False
        assert "[REDACTED]" in trace.args_json


def test_metrics_missing_cost_is_not_zero():
    result = metrics()
    assert result["cost"].startswith("unknown")
    assert result["modes"]["aura"]["attack_trials"] >= 1


def test_approval_requires_exact_args_and_executes_only_once(monkeypatch):
    args = {"filters": {"region": "North"}, "limit": 3}
    approval_id = str(uuid.uuid4())
    call_id = str(uuid.uuid4())
    import hashlib
    import json

    with Session.begin() as db:
        db.add(
            ToolEvent(
                id=call_id,
                trial_id=str(uuid.uuid4()),
                scenario_id="interactive",
                mode="aura",
                sequence=1,
                tool_name="search_customers",
                args_json=json.dumps(args),
                decision="APPROVAL_REQUIRED",
                reason="JEV_UNCERTAIN",
                policy_version=main.POLICY_VERSION,
                executor_invoked=False,
                outcome="blocked",
                rows_returned=0,
                sensitive_fields=0,
                latency_ms=0,
                created_at=main.now(),
            )
        )
        db.add(
            Approval(
                id=approval_id,
                tool_name="search_customers",
                args_hash=hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest(),
                args_json=json.dumps({"tool_call_id": call_id, "arguments": args}),
                status="pending",
            )
        )

    original_execute = main.execute_tool
    calls = []

    def tracked_execute(name, validated_args):
        calls.append(name)
        return original_execute(name, validated_args)

    monkeypatch.setattr(main, "execute_tool", tracked_execute)
    with pytest.raises(main.HTTPException) as error:
        main.approval_decision(
            approval_id,
            ApprovalDecision(approved=True, args={**args, "limit": 4}),
        )
    assert error.value.status_code == 409
    assert calls == []

    assert (
        main.approval_decision(approval_id, ApprovalDecision(approved=True, args=args))["status"]
        == "executed"
    )
    with pytest.raises(main.HTTPException) as error:
        main.approval_decision(approval_id, ApprovalDecision(approved=True, args=args))
    assert error.value.status_code == 409
    assert calls == ["search_customers"]

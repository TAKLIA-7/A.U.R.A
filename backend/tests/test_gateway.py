import json
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


def test_structured_agent_logs_filter_paginate_and_trace_detail():
    action_id, trace_id = str(uuid.uuid4()), str(uuid.uuid4())
    with Session.begin() as db:
        main.add_audit_event(db, "ENFORCEMENT_DECISION_MADE", action_id, trace_id,
                             tool="get_customer", agent_id="local-agent", decision="BLOCK",
                             jev_recommendation="ALLOW", risk_level="high", reason_code="POLICY_VETO")
        main.add_audit_event(db, "EXECUTION_NOT_ATTEMPTED", action_id, trace_id, tool="get_customer")
    result = main.agent_logs(limit=1, offset=0, time_range="all", decision="BLOCK", tool_name="get_customer",
                             agent_id="local-agent", search=trace_id, sort="asc")
    assert result["total"] == 1
    item = result["items"][0]
    assert item["event_name"] == "aura.decision_made"
    assert item["severity"] == "WARN"
    assert item["jev_recommendation"] == "ALLOW"
    assert item["aura_decision"] == "BLOCK"
    assert item["reason_codes"] == ["POLICY_VETO"]
    detail = main.agent_log_detail(item["event_id"])
    assert len(detail["timeline"]) == 2
    assert detail["timeline"][1]["execution_status"] == "NOT_ATTEMPTED"


def test_query_test_catalog_and_outcome_comparison():
    catalog = main.query_test_scenarios()
    assert len(catalog) >= 25
    assert {entry["category"][0] for entry in catalog} == set("ABCDEFGH")
    assert all(main.QueryScenario.model_validate(entry) for entry in catalog)
    scenario = main.SCENARIO_BY_ID["A-001"]
    actual = {"decision": "ALLOW", "execution_status": "SUCCESS", "audit_complete": True,
              "alerts": [], "tool_calls": [{"tool": "get_customer", "decision": "ALLOW",
              "execution_status": "SUCCESS", "executor_invoked": True, "sensitive_fields": 0,
              "reason_code": "JEV_LOW_RISK", "action_id": "a-1"}]}
    assert all(main._compare_query_test(scenario, actual).values())
    denied_scenario = main.SCENARIO_BY_ID["B-004"]
    unsafe = {"decision": "BLOCK", "execution_status": "SUCCESS", "audit_complete": True,
              "alerts": [], "tool_calls": [{"tool": "export_customers", "decision": "BLOCK",
              "execution_status": "SUCCESS", "executor_invoked": True, "sensitive_fields": 0,
              "reason_code": "SENSITIVE_FIELD", "action_id": "a-2"}]}
    checks = main._compare_query_test(denied_scenario, unsafe)
    assert checks["decision"] is True
    assert checks["executor_never_runs_on_denial"] is False
    assert checks["execution_status"] is False


def test_query_test_metrics_are_derived_from_saved_scenarios():
    def row(scenario_id, expected, actual, decision, execution, *, prohibited=False,
            legitimate=False, status="PASSED", jev_status="completed", latency=10):
        return main.QueryTestResult(
            id=str(uuid.uuid4()), test_run_id="run-1", scenario_id=scenario_id,
            category="test", name=scenario_id, user_query="synthetic query",
            expected_json=json.dumps({"expected_decision": expected}), actual_json=json.dumps(actual),
            status=status, passed=status == "PASSED", failure_explanation=None, action_id="a-1",
            trace_id="t-1", actual_decision=decision, execution_status=execution,
            latency_ms=latency, jev_status=jev_status, audit_complete=True,
            legitimate=legitimate, prohibited=prohibited,
        )

    prohibited = row("B-004", ["BLOCK"], {"tool_calls": [{"decision": "BLOCK", "executor_invoked": False,
        "jev_status": "completed"}], "assertions": {"execution_status": True}}, "BLOCK", "NOT_ATTEMPTED", prohibited=True)
    false_positive = row("A-001", ["ALLOW"], {"tool_calls": [{"decision": "BLOCK", "executor_invoked": False,
        "jev_status": "failed"}], "assertions": {"execution_status": False}}, "BLOCK", "NOT_ATTEMPTED", legitimate=True, status="FAILED", jev_status="failed", latency=30)
    pending = row("G-001", ["APPROVAL_REQUIRED"], {"tool_calls": [{"decision": "APPROVAL_REQUIRED",
        "executor_invoked": False, "jev_status": "completed"}], "assertions": {"execution_status": True}},
        "APPROVAL_REQUIRED", "PENDING")
    result = main._query_test_metrics([prohibited, false_positive, pending])
    assert result["detection_rate"] == 1
    assert result["detection_sample_size"] == 1
    assert result["false_positive_rate"] == 1
    assert result["approval_correctness"] == 1
    assert result["unauthorized_execution_count"] == 0
    assert result["mean_latency_ms"] == pytest.approx(50 / 3)
    assert result["p95_latency_ms"] == 30
    assert result["jev_failure_rate"] == pytest.approx(1 / 3)


def test_query_test_execution_requires_configured_token(monkeypatch):
    monkeypatch.delenv("AURA_TEST_RUN_TOKEN", raising=False)
    request = main.QueryTestStartRequest(suite_kind="scenario", scenario_id="A-001")
    with pytest.raises(main.HTTPException) as disabled:
        main.start_query_test_run(request, main.BackgroundTasks(), "invalid")
    assert disabled.value.status_code == 503
    monkeypatch.setenv("AURA_TEST_RUN_TOKEN", "synthetic-test-secret")
    with pytest.raises(main.HTTPException) as unauthorized:
        main.start_query_test_run(request, main.BackgroundTasks(), "wrong-token")
    assert unauthorized.value.status_code == 401
    with pytest.raises(main.HTTPException) as forbidden_read:
        main.query_test_run_detail("missing", "wrong-token")
    assert forbidden_read.value.status_code == 401
    with pytest.raises(main.HTTPException) as forbidden_results:
        main.query_test_metrics("all", "wrong-token")
    assert forbidden_results.value.status_code == 401
    main._authorize_query_tests("synthetic-test-secret")


def test_jev_timeout_fails_closed_without_executor(monkeypatch):
    class TimeoutEngine:
        def assess(self, _state):
            raise TimeoutError("simulated provider timeout")

    monkeypatch.setenv("DECISION_ENGINE", "jev")
    decision = main.evaluate_protected("get_customer", CustomerId(customer_id="C001"), [],
                                       "Read customer C001", engine=TimeoutEngine())
    assert decision.action == "BLOCK"
    assert decision.reason_code == "JEV_FAILURE"


def test_explicit_bulk_request_is_vetoed_after_jev_allow(monkeypatch):
    from backend.app.jev import JevAssessment

    class AllowEngine:
        def assess(self, _state):
            return JevAssessment(
                request_id="jev-1", model="test-model", outside_user_request=0.01,
                exfiltration_sequence=0.02,
            )

    monkeypatch.setenv("DECISION_ENGINE", "jev")
    decision = main.evaluate_protected(
        "export_customers", ExportArgs(limit=10), [], "give me all users data", engine=AllowEngine()
    )

    assert decision.jev_recommendation == "ALLOW"
    assert decision.action == "BLOCK"
    assert decision.reason_code == "BULK_DATA_REQUEST"


def test_broad_get_all_users_request_is_blocked_before_model_call(monkeypatch):
    from backend.app import providers

    class AgentMustNotRun:
        def __init__(self, **_kwargs):
            raise AssertionError("obvious bulk-data requests must be vetoed before model use")

    monkeypatch.setattr(providers, "OpenAIToolAgent", AgentMustNotRun)
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    trace_id = str(uuid.uuid4())

    response = run_agent(
        AgentRunRequest(prompt="get all the users data", mode="aura"),
        x_aura_trace_id=uuid.UUID(trace_id),
    )

    assert response["provider"] == "aura-policy"
    assert response["tool_calls"] == 0
    assert response["request_decision"]["jev_recommendation"] == "NOT_RUN"
    assert response["request_decision"]["decision"] == "BLOCK"
    assert response["request_decision"]["reason_code"] == "BULK_DATA_REQUEST"
    with Session() as db:
        event = db.query(main.AuditEvent).filter_by(trace_id=trace_id).one()
    assert event.event_name == "aura.request_guard_blocked"
    assert "get all the users data" not in event.detail


def test_jev_logs_keep_recommendation_and_final_aura_reason(monkeypatch):
    trace_id, action_id = str(uuid.uuid4()), str(uuid.uuid4())
    with Session.begin() as db:
        main.add_audit_event(
            db, "JEV_ASSESSMENT_COMPLETED", action_id, trace_id,
            tool="export_customers", recommendation="ALLOW", assessment_status="completed",
        )
        main.add_audit_event(
            db, "ENFORCEMENT_DECISION_MADE", action_id, trace_id,
            tool="export_customers", jev_recommendation="ALLOW", aura_decision="BLOCK",
            reason="BULK_DATA_REQUEST",
        )

    try:
        logs = main.agent_logs(limit=20, offset=0, time_range="all", search=trace_id, sort="asc")
        jev_log = next(item for item in logs["items"] if item["event_name"] == "jev.assessment_completed")
        aura_log = next(item for item in logs["items"] if item["event_name"] == "aura.decision_made")
        assert jev_log["jev_recommendation"] == "ALLOW"
        assert jev_log["jev_status"] == "completed"
        assert aura_log["jev_recommendation"] == "ALLOW"
        assert aura_log["aura_decision"] == "BLOCK"
        assert aura_log["reason_codes"] == ["BULK_DATA_REQUEST"]
    finally:
        with Session.begin() as db:
            db.query(main.AuditEvent).filter_by(trace_id=trace_id).delete()


def test_query_test_events_are_tagged_and_excluded_from_production_monitoring(monkeypatch):
    test_run_id, event_id = f"test-{uuid.uuid4()}", str(uuid.uuid4())
    context_token = main.CURRENT_QUERY_TEST_RUN.set(test_run_id)
    try:
        engine_token = main.CURRENT_QUERY_TEST_ENGINE.set(main.query_test_engine)
        with main.QueryTestSession.begin() as db:
            main.add_audit_event(db, "REQUEST_RECEIVED", str(uuid.uuid4()), str(uuid.uuid4()),
                                 tool="get_customer", customer_id="C001")
            db.add(ToolEvent(
                id=event_id, action_id=str(uuid.uuid4()), trace_id=test_run_id,
                test_run_id=test_run_id, trial_id=test_run_id, scenario_id="interactive", mode="aura",
                sequence=1, tool_name="get_customer", args_json=json.dumps({"customer_id": "[REDACTED]"}),
                decision="ALLOW", jev_decision="ALLOW", risk_level="low", decision_latency_ms=2,
                reason="JEV_LOW_RISK", policy_version=main.POLICY_VERSION,
                executor_invoked=True, outcome="returned", rows_returned=1, sensitive_fields=0,
                latency_ms=2, created_at=main.now(),
            ))
        with main.QueryTestSession() as db:
            audit = db.query(main.AuditEvent).filter_by(test_run_id=test_run_id).one()
        assert audit.test_run_id == test_run_id
        assert "[REDACTED]" in audit.detail
        assert event_id not in {event.id for event in main._monitoring_events("all")}
        monkeypatch.setenv("AURA_TEST_RUN_TOKEN", "trace-token")
        displayed = next(item for item in main.tool_calls(limit=1000, test_run_id=test_run_id,
                                                         x_aura_test_token="trace-token") if item["id"] == event_id)
        assert displayed["test_run_id"] == test_run_id
    finally:
        main.CURRENT_QUERY_TEST_ENGINE.reset(engine_token)
        main.CURRENT_QUERY_TEST_RUN.reset(context_token)
        with main.QueryTestSession.begin() as db:
            db.query(ToolEvent).filter_by(id=event_id).delete()
            db.query(main.AuditEvent).filter_by(test_run_id=test_run_id).delete()


def test_query_test_detail_api_matches_separately_persisted_records(monkeypatch):
    monkeypatch.setenv("AURA_TEST_RUN_TOKEN", "read-token")
    run_id, result_id = str(uuid.uuid4()), str(uuid.uuid4())
    expected = {"expected_decision": ["ALLOW"], "initial_conditions": [], "required_permissions": []}
    actual = {"tool_calls": [], "assertions": {"execution_status": True}}
    with main.QueryTestSession.begin() as db:
        db.add(main.QueryTestRun(id=run_id, created_at=main.now(), completed_at=main.now(),
            status="completed", suite_kind="scenario", selected_category=None,
            environment="synthetic-test", run_mode="natural-language-integration",
            provider="gemini", decision_engine="jev", components="{}"))
        db.add(main.QueryTestResult(id=result_id, test_run_id=run_id, scenario_id="A-001",
            category="A: Legitimate operations", name="Read synthetic row", user_query="Read C001",
            expected_json=json.dumps(expected), actual_json=json.dumps(actual), status="PASSED",
            passed=True, failure_explanation=None, action_id=None, trace_id="trace-1",
            actual_decision="ALLOW", execution_status="SUCCESS", latency_ms=10,
            jev_status="completed", audit_complete=True, legitimate=True, prohibited=False))
    try:
        detail = main.query_test_run_detail(run_id, "read-token")
        assert detail["results"][0]["scenario_id"] == "A-001"
        assert detail["metrics"]["passed_scenarios"] == 1
        assert detail["environment"] == "synthetic-test"
    finally:
        with main.QueryTestSession.begin() as db:
            db.query(main.QueryTestResult).filter_by(test_run_id=run_id).delete()
            db.query(main.QueryTestRun).filter_by(id=run_id).delete()


def test_query_agent_sequence_keeps_tool_history_in_one_session(monkeypatch):
    from backend.app import providers

    class SequenceAgent:
        model = "test-agent"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            dispatch("get_customer", {"customer_id": "C001"})
            dispatch("get_customer", {"customer_id": "C002"})
            blocked = dispatch("export_customers", {"fields": ["id"], "limit": 5})
            assert blocked["decision"] == "BLOCK"
            return providers.AgentResult(answer="Sequence evaluated", usage=[], tool_calls=3)

    monkeypatch.setattr(providers, "OpenAIToolAgent", SequenceAgent)
    monkeypatch.setattr(main, "evaluate_protected", lambda name, args, history, prompt: evaluate(name, args, history, "aura"))
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    response = run_agent(AgentRunRequest(prompt="Read two records then export", mode="aura"))
    with Session() as db:
        events = db.query(ToolEvent).filter_by(trace_id=response["run_id"]).order_by(ToolEvent.sequence).all()
    assert [event.decision for event in events] == ["ALLOW", "ALLOW", "BLOCK"]
    assert [event.executor_invoked for event in events] == [True, True, False]
    assert events[-1].reason == "SEQUENCE_EXPORT"


def test_audit_persistence_failure_prevents_protected_execution(monkeypatch):
    from backend.app import providers

    class OneCallAgent:
        model = "test-agent"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            dispatch("get_customer", {"customer_id": "C001"})
            return providers.AgentResult(answer="done", usage=[], tool_calls=1)

    monkeypatch.setattr(providers, "OpenAIToolAgent", OneCallAgent)
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    monkeypatch.setattr(main, "add_audit_event", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    executions = []
    monkeypatch.setattr(main, "execute_tool", lambda *args: executions.append(args))
    with pytest.raises(main.HTTPException) as error:
        run_agent(AgentRunRequest(prompt="Read C001", mode="aura"))
    assert error.value.status_code == 502
    assert executions == []


def test_model_internal_server_error_is_reported_as_upstream_500(monkeypatch):
    from backend.app import providers

    class InternalServerError(RuntimeError):
        code = 500

    class FailingAgent:
        model = "test-agent"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            raise InternalServerError("Internal server error")

    monkeypatch.setattr(providers, "OpenAIToolAgent", FailingAgent)
    monkeypatch.setenv("AGENT_PROVIDER", "openai")

    with pytest.raises(main.HTTPException) as error:
        run_agent(AgentRunRequest(prompt="Hello", mode="aura"))

    assert error.value.status_code == 502
    assert "openai model provider returned HTTP 500" in error.value.detail
    assert "No final answer was generated" in error.value.detail


def test_model_timeout_is_not_mislabeled_as_connection_failure(monkeypatch):
    from backend.app import providers

    class FailingAgent:
        model = "test-agent"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            raise TimeoutError("provider request timed out")

    monkeypatch.setattr(providers, "OpenAIToolAgent", FailingAgent)
    monkeypatch.setenv("AGENT_PROVIDER", "openai")

    with pytest.raises(main.HTTPException) as error:
        run_agent(AgentRunRequest(prompt="Read one record", mode="aura"))

    assert "openai model request timed out" in error.value.detail
    assert "connection failed" not in error.value.detail


def test_database_executor_failure_is_recorded_as_an_attempt(monkeypatch):
    from backend.app import providers

    class OneCallAgent:
        model = "test-agent"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            dispatch("get_customer", {"customer_id": "C001"})
            return providers.AgentResult(answer="Execution attempted", usage=[], tool_calls=1)

    monkeypatch.setattr(providers, "OpenAIToolAgent", OneCallAgent)
    monkeypatch.setattr(main, "evaluate_protected", lambda *args, **kwargs: main.Decision(
        action="ALLOW", reason_code="JEV_LOW_RISK", human_readable_reason="allowed",
        policy_id="jev", risk_level="low", decision_engine="openrouter-jev+local-invariants",
        jev_recommendation="ALLOW"))
    monkeypatch.setattr(main, "execute_tool", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic executor failure")))
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    response = run_agent(AgentRunRequest(prompt="Read customer C001", mode="aura"))
    with Session() as db:
        event = db.query(ToolEvent).filter_by(trace_id=response["run_id"]).one()
        audit = db.query(main.AuditEvent).filter_by(action_id=event.action_id, event_type="EXECUTION_FAILED").one()
    assert event.executor_invoked is True
    assert event.outcome == "execution_failed"
    assert audit.execution_status == "FAILED"


def test_query_test_runs_reject_concurrent_start(monkeypatch):
    monkeypatch.setenv("AURA_TEST_RUN_TOKEN", "test-token")
    active_id = str(uuid.uuid4())
    with main.QueryTestSession.begin() as db:
        db.add(main.QueryTestRun(id=active_id, created_at=main.now(), completed_at=None,
            status="running", suite_kind="scenario", selected_category=None,
            environment="synthetic-test", run_mode="natural-language-integration",
            provider="gemini", decision_engine="jev", components="{}"))
    try:
        with pytest.raises(main.HTTPException) as error:
            main.start_query_test_run(main.QueryTestStartRequest(suite_kind="scenario", scenario_id="A-001"),
                                      main.BackgroundTasks(), "test-token")
        assert error.value.status_code == 409
    finally:
        with main.QueryTestSession.begin() as db:
            db.query(main.QueryTestRun).filter_by(id=active_id).delete()


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
            return providers.AgentResult(
                answer="The export was denied.", usage=[], tool_calls=1, tool_results=[result]
            )

    monkeypatch.setattr(providers, "OpenAIToolAgent", FakeAgent)
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    response = run_agent(AgentRunRequest(prompt="Export customer emails", mode="aura"))
    assert response["provider"] == "openai"
    assert response["tool_calls"] == 1
    assert response["tool_results"][0]["decision"] == "BLOCK"
    assert response["tool_results"][0]["execution_status"] == "NOT_ATTEMPTED"
    with Session() as db:
        trace = db.query(ToolEvent).filter_by(trial_id=response["run_id"]).one()
        assert trace.decision == "BLOCK"
        assert trace.executor_invoked is False
        assert "[REDACTED]" in trace.args_json


def test_allowed_agent_action_persists_correlated_lifecycle(monkeypatch):
    from backend.app import providers

    class FakeAgent:
        model = "test-agent"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            response = dispatch("get_customer", {"customer_id": "C001"})
            assert response["decision"] == "ALLOW"
            return providers.AgentResult(answer="Read complete", usage=[], tool_calls=1)

    monkeypatch.setattr(providers, "OpenAIToolAgent", FakeAgent)
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    response = run_agent(AgentRunRequest(prompt="Read customer C001", mode="aura"))
    with Session() as db:
        event = db.query(ToolEvent).filter_by(trial_id=response["run_id"]).one()
        audit = [json.loads(row.detail) | {"type": row.event_type} for row in db.query(main.AuditEvent).all()]
    assert event.action_id and event.trace_id == response["run_id"]
    assert event.executor_invoked is True and event.outcome == "returned"
    assert "C001" not in event.args_json and "[REDACTED]" in event.args_json
    correlated = [item for item in audit if item.get("action_id") == event.action_id]
    assert {"REQUEST_RECEIVED", "VALIDATION_COMPLETED", "ENFORCEMENT_DECISION_MADE", "EXECUTION_STARTED", "EXECUTION_SUCCEEDED"} <= {x["type"] for x in correlated}


def test_monitoring_filters_metrics_and_export_use_persisted_actions():
    from backend.app.main import export_audit, monitoring_actions, monitoring_summary

    experiment_id = create_experiment("monitoring API fixture")
    run_experiment(experiment_id, {"scenario_ids": ["S001", "S004"], "modes": ["aura"], "repetitions": 1})
    summary = monitoring_summary("all")
    actions = monitoring_actions(limit=1, offset=0, time_range="all", decision="BLOCK")
    assert summary["total_actions"] >= 2
    assert actions["total"] >= 1 and len(actions["items"]) == 1
    assert actions["items"][0]["aura_decision"] == "BLOCK"
    response = export_audit(time_range="all", decision="BLOCK")
    assert response.media_type == "text/csv"
    assert "action_id,trace_id,timestamp" in response.body.decode()


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


def test_rejected_approval_is_audited_without_executor(monkeypatch):
    args = {"customer_id": "C001"}
    approval_id, call_id, trace_id, action_id = (str(uuid.uuid4()) for _ in range(4))
    import hashlib

    with Session.begin() as db:
        db.add(ToolEvent(
            id=call_id, action_id=action_id, trace_id=trace_id, trial_id=trace_id,
            scenario_id="interactive", mode="aura", sequence=1, tool_name="get_customer",
            args_json=json.dumps({"customer_id": "[REDACTED]"}), decision="APPROVAL_REQUIRED",
            jev_decision="APPROVAL_REQUIRED", risk_level="medium", reason="JEV_UNCERTAIN",
            policy_version=main.POLICY_VERSION, executor_invoked=False, outcome="blocked",
            rows_returned=0, sensitive_fields=0, latency_ms=0, created_at=main.now(),
        ))
        db.add(Approval(
            id=approval_id, tool_name="get_customer",
            args_hash=hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest(),
            args_json=json.dumps({"tool_call_id": call_id, "arguments": args}), status="pending",
        ))
    calls = []
    monkeypatch.setattr(main, "execute_tool", lambda *args: calls.append(args))
    assert main.approval_decision(approval_id, ApprovalDecision(approved=False, args=args))["status"] == "rejected"
    with Session() as db:
        assert db.get(Approval, approval_id).status == "rejected"
        assert db.get(ToolEvent, call_id).executor_invoked is False
        audit = [json.loads(x.detail) for x in db.query(main.AuditEvent).all()]
    assert calls == []
    assert any(a.get("action_id") == action_id and a.get("approved") is False for a in audit)


def test_approval_required_agent_action_stays_pending_without_execution(monkeypatch):
    from backend.app import providers

    class FakeAgent:
        model = "test-agent"

        def __init__(self, model=None, max_turns=8):
            pass

        def run(self, prompt, tool_definitions, dispatch):
            result = dispatch("get_customer", {"customer_id": "C002"})
            assert result["decision"] == "APPROVAL_REQUIRED"
            assert "pending review" in result["result"]["error"]
            return providers.AgentResult(answer="Waiting for review", usage=[], tool_calls=1)

    monkeypatch.setattr(providers, "OpenAIToolAgent", FakeAgent)
    monkeypatch.setattr(main, "evaluate_protected", lambda *args, **kwargs: main.Decision(
        action="APPROVAL_REQUIRED", reason_code="JEV_UNCERTAIN",
        human_readable_reason="uncertain", policy_id="jev", risk_level="medium",
        decision_engine="openrouter-jev+local-invariants", jev_recommendation="APPROVAL_REQUIRED",
    ))
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    calls = []
    monkeypatch.setattr(main, "execute_tool", lambda *args: calls.append(args))
    response = run_agent(AgentRunRequest(prompt="Read customer record", mode="aura"))
    with Session() as db:
        event = db.query(ToolEvent).filter_by(trial_id=response["run_id"]).one()
        approval = db.query(Approval).filter_by(status="pending", tool_name="get_customer").first()
    assert event.decision == "APPROVAL_REQUIRED" and event.executor_invoked is False
    assert event.outcome == "pending_approval" and approval is not None
    assert calls == []

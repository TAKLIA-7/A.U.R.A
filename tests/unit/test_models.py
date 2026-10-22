"""Unit tests for AURA data models."""
import pytest
from aura.models import (
    ActionRequest, AuditEvent, EventLevel, JEVAssessment,
    PolicyDecision, RunRecord, RunStatus, DecisionResult, RiskLevel,
)


def test_action_request_defaults():
    req = ActionRequest(tool="filesystem.read")
    assert req.request_id.startswith("req_")
    assert req.reversible is True


def test_audit_event_to_jsonl():
    ev = AuditEvent(event_type="aura.test.event")
    jsonl = ev.to_jsonl()
    import json
    data = json.loads(jsonl)
    assert data["event_type"] == "aura.test.event"
    assert "event_id" in data
    assert "timestamp" in data


def test_run_record_add_event():
    run = RunRecord(session_id="session_test")
    run.add_event("aura.run.started")
    assert len(run.timeline) == 1
    assert run.timeline[0]["event_type"] == "aura.run.started"


def test_jev_assessment_defaults():
    assess = JEVAssessment(request_id="req_001")
    assert assess.assessment_id.startswith("assess_")
    assert assess.risk_level == RiskLevel.MEDIUM


def test_policy_decision_block():
    d = PolicyDecision(
        request_id="req_001",
        decision=DecisionResult.BLOCK,
        reason="Test block",
    )
    assert d.decision == DecisionResult.BLOCK
    assert not d.enforced

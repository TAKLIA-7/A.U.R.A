"""Unit tests for the AURA policy engine."""
import pytest
from pathlib import Path
from aura.models import ActionRequest, JEVAssessment, RiskLevel, DecisionResult
from aura.policies import PolicyEngine, ALLOWED_TOOLS


def make_engine(tmp_path):
    return PolicyEngine(workspace_root=tmp_path)


def test_allowlist_blocks_unknown_tool(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="os.system_call", target="/etc/passwd")
    decision = engine.pre_assessment_check(req)
    assert decision is not None
    assert decision.decision == DecisionResult.BLOCK


def test_allowlist_passes_allowed_tool(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="filesystem.list", target=".")
    decision = engine.pre_assessment_check(req)
    # Should pass allowlist; no pre-assessment block
    assert decision is None or decision.decision != DecisionResult.BLOCK


def test_path_traversal_blocked(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="filesystem.read", target="../../etc/passwd", arguments={"path": "../../etc/passwd"})
    decision = engine.pre_assessment_check(req)
    assert decision is not None
    assert decision.decision == DecisionResult.BLOCK
    assert "traversal" in decision.reason.lower()


def test_high_risk_jev_leads_to_block(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="shell.execute", target="rm -rf /")
    assessment = JEVAssessment(
        request_id=req.request_id,
        risk_level=RiskLevel.HIGH,
        recommended_action=DecisionResult.BLOCK,
    )
    decision = engine.apply_jev_assessment(req, assessment)
    assert decision.decision == DecisionResult.BLOCK


def test_low_risk_jev_leads_to_allow(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="filesystem.list", target=".")
    assessment = JEVAssessment(
        request_id=req.request_id,
        risk_level=RiskLevel.LOW,
        recommended_action=DecisionResult.ALLOW,
    )
    decision = engine.apply_jev_assessment(req, assessment)
    assert decision.decision == DecisionResult.ALLOW


def test_jev_approval_required_leads_to_approval(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="filesystem.write", target="output.txt")
    assessment = JEVAssessment(
        request_id=req.request_id,
        risk_level=RiskLevel.MEDIUM,
        recommended_action=DecisionResult.APPROVAL_REQUIRED,
        requires_human_review=True,
    )
    decision = engine.apply_jev_assessment(req, assessment)
    assert decision.decision == DecisionResult.APPROVAL_REQUIRED


def test_fast_allow_for_diagnostic(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="diagnostic.ping")
    assert engine.fast_allow(req) is True


def test_no_fast_allow_for_shell(tmp_path):
    engine = make_engine(tmp_path)
    req = ActionRequest(tool="shell.execute")
    assert engine.fast_allow(req) is False


@pytest.mark.asyncio
async def test_approval_manager_resolve_and_cancel():
    from aura.policies import ApprovalManager
    from aura.models import ActionRequest, PolicyDecision, DecisionResult

    mgr = ApprovalManager()
    req = ActionRequest(tool="sqlite.query", arguments={"query": "UPDATE employees SET salary = 100000;"})
    decision = PolicyDecision(request_id=req.request_id, decision=DecisionResult.APPROVAL_REQUIRED, reason="Mutating query")

    approval_id = await mgr.request_approval(req, decision)
    assert approval_id.startswith("approval_")
    pending = await mgr.get_pending()
    assert len(pending) == 1

    # Test resolve approve
    await mgr.resolve(approval_id, approved=True)
    res = await mgr.wait_for_resolution(approval_id)
    assert res == "approved"

    # Test resolve all pending
    approval_id2 = await mgr.request_approval(req, decision)
    await mgr.resolve_all_pending("cancelled")
    res2 = await mgr.wait_for_resolution(approval_id2)
    assert res2 == "cancelled"


@pytest.mark.asyncio
async def test_approval_modal_screen_actions():
    from aura.ui.screens.approval_modal import ApprovalModalScreen
    from aura.policies import ApprovalManager

    mgr = ApprovalManager()
    from aura.models import ActionRequest, PolicyDecision, DecisionResult
    req = ActionRequest(tool="sqlite.query", arguments={"query": "DELETE FROM employees WHERE id = 1;"})
    dec = PolicyDecision(request_id=req.request_id, decision=DecisionResult.APPROVAL_REQUIRED, reason="Delete query")
    approval_id = await mgr.request_approval(req, dec)

    modal = ApprovalModalScreen(
        approval_id=approval_id,
        tool="sqlite.query",
        args={"query": "DELETE FROM employees WHERE id = 1;"},
        reason="Mutating database statement",
        approval_manager=mgr,
    )
    # Simulate action approve
    await modal.action_approve()
    assert modal._resolved is True
    res = await mgr.wait_for_resolution(approval_id)
    assert res == "approved"

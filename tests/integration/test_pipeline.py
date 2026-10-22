"""Integration tests for the full AURA decision pipeline with mock providers."""
import asyncio
import os
import pytest
from pathlib import Path

os.environ["AURA_JEV_MOCK_MODE"] = "true"
os.environ["GOOGLE_API_KEY"] = "mock-test-key"


@pytest.mark.asyncio
async def test_mock_jev_full_pipeline_low_risk(tmp_path):
    """Test that a low-risk tool call (filesystem.list) is allowed end-to-end."""
    from aura.models import ActionRequest
    from aura.policies import PolicyEngine
    from aura.jev import MockJEVClient, JEVContextBuilder
    from aura.models import RunRecord

    engine = PolicyEngine(workspace_root=tmp_path)
    req = ActionRequest(tool="filesystem.list", target=".", arguments={"path": "."})

    # Pre-assessment check
    pre = engine.pre_assessment_check(req)
    assert pre is None  # No pre-block

    # JEV assessment
    client = MockJEVClient()
    builder = JEVContextBuilder()
    run = RunRecord(session_id="test_session")
    payload = builder.build(req, "list files", run)
    assessment = await client.assess(payload)
    assert assessment.risk_level.value == "low"

    # Policy decision
    decision = engine.apply_jev_assessment(req, assessment)
    from aura.models import DecisionResult
    assert decision.decision == DecisionResult.ALLOW


@pytest.mark.asyncio
async def test_mock_jev_full_pipeline_high_risk(tmp_path):
    """Test that shell.execute is blocked by JEV assessment."""
    from aura.models import ActionRequest, DecisionResult
    from aura.policies import PolicyEngine
    from aura.jev import MockJEVClient, JEVContextBuilder
    from aura.models import RunRecord

    engine = PolicyEngine(workspace_root=tmp_path)
    req = ActionRequest(tool="shell.execute", arguments={"command": "ls"})

    pre = engine.pre_assessment_check(req)
    # shell.execute is in ALLOWED_TOOLS, no pre-block
    client = MockJEVClient()
    builder = JEVContextBuilder()
    run = RunRecord(session_id="test_session")
    payload = builder.build(req, "run shell", run)
    assessment = await client.assess(payload)
    assert assessment.risk_level.value == "high"

    decision = engine.apply_jev_assessment(req, assessment)
    assert decision.decision == DecisionResult.BLOCK


@pytest.mark.asyncio
async def test_policy_blocks_unknown_tool(tmp_path):
    """Deterministic policy must block unknown tools regardless of JEV."""
    from aura.models import ActionRequest, DecisionResult
    from aura.policies import PolicyEngine

    engine = PolicyEngine(workspace_root=tmp_path)
    req = ActionRequest(tool="os.rm_rf", arguments={"path": "/"})
    pre = engine.pre_assessment_check(req)
    assert pre is not None
    assert pre.decision == DecisionResult.BLOCK


@pytest.mark.asyncio
async def test_filesystem_write_requires_approval(tmp_path):
    """filesystem.write should always require human approval."""
    from aura.models import ActionRequest, DecisionResult, JEVAssessment, RiskLevel
    from aura.policies import PolicyEngine

    engine = PolicyEngine(workspace_root=tmp_path)
    req = ActionRequest(tool="filesystem.write", arguments={"path": "out.txt", "content": "test"})
    assessment = JEVAssessment(
        request_id=req.request_id,
        risk_level=RiskLevel.MEDIUM,
        recommended_action=DecisionResult.APPROVAL_REQUIRED,
        requires_human_review=True,
    )
    decision = engine.apply_jev_assessment(req, assessment)
    assert decision.decision == DecisionResult.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_path_traversal_blocked(tmp_path):
    """Path traversal must be blocked by deterministic policy."""
    from aura.models import ActionRequest, DecisionResult
    from aura.policies import PolicyEngine

    engine = PolicyEngine(workspace_root=tmp_path)
    req = ActionRequest(tool="filesystem.read", arguments={"path": "../../../etc/passwd"})
    decision = engine.pre_assessment_check(req)
    assert decision is not None
    assert decision.decision == DecisionResult.BLOCK


@pytest.mark.asyncio
async def test_jsonl_persistence(tmp_path):
    """JSONL logs must be valid JSON and contain correct fields."""
    import json
    from aura.models import AuditEvent, EventLevel
    from aura.observability import JSONLLogger

    logger = JSONLLogger(tmp_path)
    ev = AuditEvent(
        event_type="aura.run.started",
        level=EventLevel.INFO,
        run_id="run_test_persist",
        session_id="session_test",
    )
    await logger.log(ev)
    log_file = tmp_path / "aura-events.jsonl"
    assert log_file.exists()
    for line in log_file.read_text().strip().split("\n"):
        data = json.loads(line)
        assert "event_id" in data
        assert "timestamp" in data
        assert data.get("run_id") == "run_test_persist"


@pytest.mark.asyncio
async def test_run_repository_save_and_retrieve():
    """Run repository must save and retrieve runs correctly."""
    from aura.observability import RunRepository
    from aura.models import RunRecord, RunStatus

    repo = RunRepository()
    run = RunRecord(session_id="session_repo_test", user_prompt="test prompt")
    await repo.save(run)
    retrieved = await repo.get(run.run_id)
    assert retrieved is not None
    assert retrieved.user_prompt == "test prompt"

    await repo.update_status(run.run_id, RunStatus.COMPLETED)
    retrieved2 = await repo.get(run.run_id)
    assert retrieved2.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_sqlite_pipeline_select_allowed(tmp_path):
    """Test that a SELECT sqlite query goes through MockJEV and is allowed."""
    from aura.models import ActionRequest, DecisionResult
    from aura.policies import PolicyEngine
    from aura.jev import MockJEVClient, JEVContextBuilder
    from aura.gateway import ToolRegistry
    from aura.models import RunRecord

    registry = ToolRegistry(tmp_path)
    engine = PolicyEngine(workspace_root=tmp_path)
    req = ActionRequest(tool="sqlite.query", arguments={"query": "SELECT * FROM employees LIMIT 2;"})
    enriched = registry.enrich_request(req)

    # Pre-assessment check: allowed
    pre = engine.pre_assessment_check(enriched)
    assert pre is None

    # Mock JEV assessment: LOW risk
    client = MockJEVClient()
    builder = JEVContextBuilder()
    run = RunRecord(session_id="test_session")
    payload = builder.build(enriched, "view employees", run)
    assessment = await client.assess(payload)
    assert assessment.risk_level.value == "low"

    # Policy decision: ALLOW
    decision = engine.apply_jev_assessment(enriched, assessment)
    assert decision.decision == DecisionResult.ALLOW


@pytest.mark.asyncio
async def test_sqlite_pipeline_update_requires_approval(tmp_path):
    """Test that an UPDATE sqlite query requires human approval and executes upon resolution."""
    from aura.models import ActionRequest, DecisionResult
    from aura.policies import PolicyEngine, ApprovalManager
    from aura.jev import MockJEVClient, JEVContextBuilder
    from aura.gateway import ToolRegistry, ToolExecutor
    from aura.models import RunRecord

    registry = ToolRegistry(tmp_path)
    executor = ToolExecutor(registry)
    engine = PolicyEngine(workspace_root=tmp_path)
    approval_mgr = ApprovalManager()

    req = ActionRequest(tool="sqlite.query", arguments={"query": "UPDATE employees SET salary = salary + 10 WHERE id = 1;"})
    enriched = registry.enrich_request(req)
    assert enriched.operation == "mutate"

    # Mock JEV assessment: MEDIUM risk, APPROVAL_REQUIRED
    client = MockJEVClient()
    builder = JEVContextBuilder()
    run = RunRecord(session_id="test_session")
    payload = builder.build(enriched, "give raise", run)
    assessment = await client.assess(payload)
    assert assessment.risk_level.value == "medium"
    assert assessment.requires_human_review is True

    # Policy decision: APPROVAL_REQUIRED
    decision = engine.apply_jev_assessment(enriched, assessment)
    assert decision.decision == DecisionResult.APPROVAL_REQUIRED

    # Approval requested
    approval_id = await approval_mgr.request_approval(enriched, decision, assessment)
    pending = await approval_mgr.get_pending()
    assert len(pending) == 1

    # Simulate operator approving via modal
    await approval_mgr.resolve(approval_id, approved=True)
    res = await approval_mgr.wait_for_resolution(approval_id, timeout=1.0)
    assert res == "approved"

    # Execute
    exec_res = await executor.execute(enriched)
    assert exec_res.success
    assert "rows_affected" in exec_res.output

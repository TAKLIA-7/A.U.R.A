"""AURA policy engine — rules, enforcement, approvals."""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from aura.models import (
    ActionRequest, JEVAssessment, PolicyDecision,
    DecisionResult, RiskLevel,
)


# ── Policy Rules ──────────────────────────────────────────────────────────────

# Tools that are unconditionally denied (cannot be overridden by JEV)
UNCONDITIONAL_DENY: Set[str] = {
    "shell.execute_unrestricted",
    "network.connect_external_unrestricted",
    "filesystem.delete_root",
    "os.system_call",
}

# Tools requiring approval regardless of JEV assessment
ALWAYS_APPROVAL: Set[str] = {
    "filesystem.write",
    "mock.external_action",
}

# Tools that are always allowed (fast path, skip JEV for low-risk)
ALWAYS_ALLOW: Set[str] = {
    "diagnostic.ping",
}

# Allowed tool names (allowlist — tools not listed are blocked by default)
ALLOWED_TOOLS: Set[str] = {
    "filesystem.list",
    "filesystem.read",
    "filesystem.write",
    "sqlite.query",
    "sqlite.execute",
    "sqlite_query",
    "sqlite_execute",
    "shell.execute",
    "diagnostic.ping",
    "mock.external_action",
}


# Risk level -> decision mapping
RISK_TO_DECISION: Dict[str, DecisionResult] = {
    RiskLevel.NONE.value: DecisionResult.ALLOW,
    RiskLevel.LOW.value: DecisionResult.ALLOW,
    RiskLevel.MEDIUM.value: DecisionResult.ALLOW,
    RiskLevel.HIGH.value: DecisionResult.BLOCK,
    RiskLevel.CRITICAL.value: DecisionResult.BLOCK,
}


class PolicyRule:
    def __init__(self, rule_id: str, description: str, enabled: bool = True) -> None:
        self.rule_id = rule_id
        self.description = description
        self.enabled = enabled

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        return None


class ToolAllowlistRule(PolicyRule):
    def __init__(self) -> None:
        super().__init__("POLICY-TOOL-001", "Tool allowlist enforcement")

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        if request.tool not in ALLOWED_TOOLS:
            return PolicyDecision(
                request_id=request.request_id,
                decision=DecisionResult.BLOCK,
                reason=f"Tool '{request.tool}' is not in the AURA tool allowlist.",
                policy_rule_id=self.rule_id,
                enforced=True,
            )
        return None


class UnconditionalDenyRule(PolicyRule):
    def __init__(self) -> None:
        super().__init__("POLICY-TOOL-002", "Unconditional deny list")

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        if request.tool in UNCONDITIONAL_DENY:
            return PolicyDecision(
                request_id=request.request_id,
                decision=DecisionResult.BLOCK,
                reason=f"Tool '{request.tool}' is unconditionally denied by AURA policy.",
                policy_rule_id=self.rule_id,
                enforced=True,
            )
        return None


class PathTraversalRule(PolicyRule):
    def __init__(self, workspace_root: Path) -> None:
        super().__init__("POLICY-FS-001", "Filesystem path traversal prevention")
        self.workspace_root = workspace_root.resolve()

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        if request.tool not in ("filesystem.list", "filesystem.read", "filesystem.write"):
            return None
        target = request.arguments.get("path") or request.target
        if not target:
            return None
        try:
            resolved = (self.workspace_root / target).resolve()
            if not str(resolved).startswith(str(self.workspace_root)):
                return PolicyDecision(
                    request_id=request.request_id,
                    decision=DecisionResult.BLOCK,
                    reason=f"Path traversal detected: '{target}' escapes the workspace root.",
                    policy_rule_id=self.rule_id,
                    enforced=True,
                )
        except Exception:
            return PolicyDecision(
                request_id=request.request_id,
                decision=DecisionResult.BLOCK,
                reason=f"Invalid path argument: '{target}'",
                policy_rule_id=self.rule_id,
                enforced=True,
            )
        return None


class AlwaysApprovalRule(PolicyRule):
    def __init__(self) -> None:
        super().__init__("POLICY-TOOL-003", "Tools requiring human approval")

    def evaluate(self, request: ActionRequest) -> Optional[PolicyDecision]:
        if request.tool in ALWAYS_APPROVAL:
            return PolicyDecision(
                request_id=request.request_id,
                decision=DecisionResult.APPROVAL_REQUIRED,
                reason=f"Tool '{request.tool}' always requires human approval.",
                policy_rule_id=self.rule_id,
                requires_human_review=True,
                enforced=False,
            )
        return None


# ── Policy Engine ─────────────────────────────────────────────────────────────

class PolicyEngine:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self._rules: List[PolicyRule] = [
            ToolAllowlistRule(),
            UnconditionalDenyRule(),
            PathTraversalRule(workspace_root),
            AlwaysApprovalRule(),
        ]

    def pre_assessment_check(self, request: ActionRequest) -> Optional[PolicyDecision]:
        """Run deterministic rules BEFORE JEV assessment."""
        for rule in self._rules:
            if not rule.enabled:
                continue
            decision = rule.evaluate(request)
            if decision and decision.decision in (DecisionResult.BLOCK,):
                decision.enforced = True
                return decision
        return None

    def fast_allow(self, request: ActionRequest) -> bool:
        """Return True for tools that are always allowed (skip JEV)."""
        return request.tool in ALWAYS_ALLOW

    def apply_jev_assessment(
        self,
        request: ActionRequest,
        assessment: JEVAssessment,
    ) -> PolicyDecision:
        """Apply AURA's final policy decision incorporating JEV assessment."""
        # Check approval-required rules first
        for rule in self._rules:
            if isinstance(rule, AlwaysApprovalRule) and rule.enabled:
                d = rule.evaluate(request)
                if d:
                    return PolicyDecision(
                        request_id=request.request_id,
                        assessment_id=assessment.assessment_id,
                        decision=DecisionResult.APPROVAL_REQUIRED,
                        reason=d.reason,
                        policy_rule_id=d.policy_rule_id,
                        requires_human_review=True,
                        enforced=False,
                    )

        # Apply risk-based decision
        risk_str = assessment.risk_level.value if hasattr(assessment.risk_level, "value") else str(assessment.risk_level)
        base_decision = RISK_TO_DECISION.get(risk_str, DecisionResult.BLOCK)

        # JEV recommends block -> AURA blocks
        if assessment.recommended_action == DecisionResult.BLOCK:
            return PolicyDecision(
                request_id=request.request_id,
                assessment_id=assessment.assessment_id,
                decision=DecisionResult.BLOCK,
                reason=f"JEV assessment recommends BLOCK. Risk: {risk_str}. Factors: {', '.join(assessment.risk_factors)}",
                policy_rule_id="POLICY-JEV-001",
                enforced=True,
            )

        # JEV recommends approval -> AURA requires approval
        if assessment.recommended_action == DecisionResult.APPROVAL_REQUIRED or assessment.requires_human_review:
            return PolicyDecision(
                request_id=request.request_id,
                assessment_id=assessment.assessment_id,
                decision=DecisionResult.APPROVAL_REQUIRED,
                reason=f"JEV requires human review. Risk: {risk_str}.",
                policy_rule_id="POLICY-JEV-002",
                requires_human_review=True,
                enforced=False,
            )

        return PolicyDecision(
            request_id=request.request_id,
            assessment_id=assessment.assessment_id,
            decision=base_decision,
            reason=f"Risk level '{risk_str}' — AURA policy: {base_decision.value}",
            policy_rule_id="POLICY-RISK-001",
            enforced=base_decision == DecisionResult.ALLOW,
        )

    def get_rules_summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_id": r.rule_id,
                "description": r.description,
                "enabled": r.enabled,
            }
            for r in self._rules
        ]


# ── Approval Manager ──────────────────────────────────────────────────────────

class ApprovalManager:
    def __init__(self) -> None:
        self._pending: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._events: Dict[str, asyncio.Event] = {}

    async def request_approval(
        self,
        request: ActionRequest,
        decision: PolicyDecision,
        assessment: Optional[JEVAssessment] = None,
    ) -> str:
        async with self._lock:
            approval_id = f"approval_{request.request_id}"
            self._pending[approval_id] = {
                "approval_id": approval_id,
                "request": request.model_dump(),
                "decision": decision.model_dump(),
                "assessment": assessment.model_dump() if assessment else None,
                "status": "pending",
                "resolution": None,
            }
            self._events[approval_id] = asyncio.Event()
        return approval_id

    async def resolve(self, approval_id: str, approved: bool) -> None:
        async with self._lock:
            if approval_id in self._pending:
                self._pending[approval_id]["status"] = "resolved"
                self._pending[approval_id]["resolution"] = "approved" if approved else "denied"
        if approval_id in self._events:
            self._events[approval_id].set()

    async def wait_for_resolution(self, approval_id: str, timeout: float = 300.0) -> Optional[str]:
        event = self._events.get(approval_id)
        if not event:
            return None
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return "expired"
        return self._pending.get(approval_id, {}).get("resolution")

    async def get_pending(self) -> List[Dict]:
        async with self._lock:
            return [v for v in self._pending.values() if v["status"] == "pending"]

    async def cancel(self, approval_id: str) -> None:
        async with self._lock:
            if approval_id in self._pending:
                self._pending[approval_id]["status"] = "resolved"
                self._pending[approval_id]["resolution"] = "cancelled"
        if approval_id in self._events:
            self._events[approval_id].set()

    async def resolve_all_pending(self, resolution: str = "cancelled") -> None:
        """Resolve all currently pending approvals, e.g. when run is cancelled."""
        async with self._lock:
            for approval_id, data in self._pending.items():
                if data.get("status") == "pending":
                    data["status"] = "resolved"
                    data["resolution"] = resolution
                    if approval_id in self._events:
                        self._events[approval_id].set()

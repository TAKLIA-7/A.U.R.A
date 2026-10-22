"""JEV integration — client, context builder, schemas, mock client."""
from __future__ import annotations
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
import httpx
from aura.models import (
    ActionRequest, JEVAssessment, JEVContextPayload,
    DecisionResult, RiskLevel, RunRecord,
)


# ── Context Builder ───────────────────────────────────────────────────────────

class JEVContextBuilder:
    """Builds the normalized JEV context payload from AURA's trusted state."""

    def build(
        self,
        request: ActionRequest,
        user_intent: str,
        run: RunRecord,
        policy_context: Optional[Dict[str, Any]] = None,
    ) -> JEVContextPayload:
        action_dict = {
            "tool": request.tool,
            "operation": request.operation,
            "target": request.target,
            "data_classification": request.data_classification,
            "reversible": request.reversible,
        }
        identity = {
            "user_role": "operator",
            "agent_id": "aura-agent",
            "session_id": run.session_id,
        }
        actions_completed = [
            e["event_type"].replace("aura.action.", "")
            for e in run.timeline
            if e["event_type"] == "aura.action.executed"
        ]
        actions_denied = [
            e["event_type"].replace("aura.action.", "")
            for e in run.timeline
            if e["event_type"] == "aura.action.blocked"
        ]
        session = {
            "run_id": run.run_id,
            "actions_completed": actions_completed[-5:],
            "actions_denied": actions_denied[-5:],
            "tool_calls_so_far": run.total_tool_calls,
        }
        pc = policy_context or {
            "external_operations_allowed": False,
            "approval_required_for_high_risk": True,
            "shell_execution_allowed": False,
        }
        return JEVContextPayload(
            request_id=request.request_id,
            user_intent=user_intent,
            action=action_dict,
            identity=identity,
            session=session,
            policy_context=pc,
        )


# ── Mock JEV Client ───────────────────────────────────────────────────────────

MOCK_RISK_RULES: Dict[str, Dict] = {
    "shell.execute": {
        "risk_level": RiskLevel.HIGH,
        "risk_factors": ["privileged_command", "irreversible_side_effect"],
        "evidence": ["Shell execution can run arbitrary commands"],
        "recommended_action": DecisionResult.BLOCK,
        "requires_human_review": False,
    },
    "filesystem.write": {
        "risk_level": RiskLevel.MEDIUM,
        "risk_factors": ["data_modification", "filesystem_mutation"],
        "evidence": ["Writing to filesystem is a mutating operation"],
        "recommended_action": DecisionResult.APPROVAL_REQUIRED,
        "requires_human_review": True,
    },
    "email.send": {
        "risk_level": RiskLevel.HIGH,
        "risk_factors": ["external_destination", "data_exfiltration_risk"],
        "evidence": ["Sending data to external recipient"],
        "recommended_action": DecisionResult.BLOCK,
        "requires_human_review": False,
    },
    "filesystem.list": {
        "risk_level": RiskLevel.LOW,
        "risk_factors": ["read_only"],
        "evidence": ["Listing directory is a read-only operation"],
        "recommended_action": DecisionResult.ALLOW,
        "requires_human_review": False,
    },
    "filesystem.read": {
        "risk_level": RiskLevel.LOW,
        "risk_factors": ["read_only"],
        "evidence": ["Reading file is a read-only operation"],
        "recommended_action": DecisionResult.ALLOW,
        "requires_human_review": False,
    },
    "diagnostic.ping": {
        "risk_level": RiskLevel.NONE,
        "risk_factors": [],
        "evidence": ["Diagnostic ping is harmless"],
        "recommended_action": DecisionResult.ALLOW,
        "requires_human_review": False,
    },
    "mock.external_action": {
        "risk_level": RiskLevel.HIGH,
        "risk_factors": ["external_service", "data_flow"],
        "evidence": ["Interaction with external service"],
        "recommended_action": DecisionResult.APPROVAL_REQUIRED,
        "requires_human_review": True,
    },
}


class MockJEVClient:
    """Clearly labeled mock JEV client for development and testing."""

    provider_name = "mock"

    async def assess(
        self,
        payload: JEVContextPayload,
        timeout: float = 10.0,
    ) -> JEVAssessment:
        start = time.monotonic()
        await asyncio.sleep(0.05)  # Simulate network latency
        tool = payload.action.get("tool", "")
        if tool in ("sqlite.query", "sqlite.execute", "sqlite_query", "sqlite_execute"):
            op = payload.action.get("operation", "")
            if op == "mutate":
                rule = {
                    "risk_level": RiskLevel.MEDIUM,
                    "risk_factors": ["database_mutation", "data_modification"],
                    "evidence": ["Mutating SQL query modifies persistent employee database records"],
                    "recommended_action": DecisionResult.APPROVAL_REQUIRED,
                    "requires_human_review": True,
                }
            else:
                rule = {
                    "risk_level": RiskLevel.LOW,
                    "risk_factors": ["read_only_query"],
                    "evidence": ["SELECT query reads employee records without modifying state"],
                    "recommended_action": DecisionResult.ALLOW,
                    "requires_human_review": False,
                }
        else:
            rule = MOCK_RISK_RULES.get(tool, {
                "risk_level": RiskLevel.MEDIUM,
                "risk_factors": ["unknown_tool"],
                "evidence": [f"No policy rule defined for tool: {tool}"],
                "recommended_action": DecisionResult.APPROVAL_REQUIRED,
                "requires_human_review": True,
            })

        latency = (time.monotonic() - start) * 1000
        return JEVAssessment(
            assessment_id=f"mock_assess_{uuid.uuid4().hex[:8]}",
            request_id=payload.request_id,
            risk_level=rule["risk_level"],
            risk_factors=rule["risk_factors"],
            evidence=rule["evidence"],
            recommended_action=rule["recommended_action"],
            requires_human_review=rule["requires_human_review"],
            provider="mock",
            latency_ms=latency,
        )

    async def health_check(self) -> bool:
        return True


# ── Real JEV Client ───────────────────────────────────────────────────────────

class JEVClient:
    """Real JEV HTTP client adapter."""

    provider_name = "jev"

    def __init__(self, endpoint: str, api_key: str, timeout: float = 10.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-AURA-Client": "aura/0.1.0",
        }

    def _normalize(self, raw: Dict[str, Any], request_id: str, latency_ms: float) -> JEVAssessment:
        risk_map = {
            "none": RiskLevel.NONE, "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM, "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL,
        }
        action_map = {
            "allow": DecisionResult.ALLOW, "block": DecisionResult.BLOCK,
            "approve": DecisionResult.APPROVAL_REQUIRED,
            "approval_required": DecisionResult.APPROVAL_REQUIRED,
        }
        risk_str = str(raw.get("risk_level", "medium")).lower()
        action_str = str(raw.get("recommended_action", "allow")).lower()
        return JEVAssessment(
            assessment_id=raw.get("assessment_id", f"jev_{uuid.uuid4().hex[:8]}"),
            request_id=request_id,
            risk_level=risk_map.get(risk_str, RiskLevel.MEDIUM),
            risk_factors=raw.get("risk_factors", []),
            evidence=raw.get("evidence", []),
            recommended_action=action_map.get(action_str, DecisionResult.APPROVAL_REQUIRED),
            requires_human_review=bool(raw.get("requires_human_review", False)),
            provider="jev",
            latency_ms=latency_ms,
            raw_response=raw,
        )

    async def assess(
        self,
        payload: JEVContextPayload,
        timeout: Optional[float] = None,
    ) -> JEVAssessment:
        t = timeout or self.timeout
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=t) as client:
            resp = await client.post(
                f"{self.endpoint}/assess",
                headers=self._headers(),
                json=payload.model_dump(),
            )
            resp.raise_for_status()
            raw = resp.json()
        latency_ms = (time.monotonic() - start) * 1000
        return self._normalize(raw, payload.request_id, latency_ms)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.endpoint}/health",
                    headers=self._headers(),
                )
                return resp.status_code < 400
        except Exception:
            return False


# ── OpenRouter JEV Client ─────────────────────────────────────────────────────

class OpenRouterJEVClient:
    """OpenRouter-backed JEV AI risk assessment engine.

    Submits contextual action requests and security constraints to OpenRouter LLMs
    (e.g. Gemini 2.0, Claude 3.5 Haiku, Llama 3.3) and parses structured risk assessments.
    """

    provider_name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-2.0-flash-001",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 12.0,
        allow_threshold: float = 0.1,
        block_threshold: float = 0.9,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.timeout = timeout
        self.allow_threshold = allow_threshold
        self.block_threshold = block_threshold

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://aura.security",
            "X-Title": "AURA Agent Control Plane",
            "Content-Type": "application/json",
        }

    async def assess(
        self,
        payload: JEVContextPayload,
        timeout: Optional[float] = None,
    ) -> JEVAssessment:
        t = timeout or self.timeout
        start = time.monotonic()

        # Check if using OpenRouter Decisions API (e.g. typesafe/jev-1.13)
        if ("typesafe/jev" in self.model or "decisions" in (self.base_url or "")) and "mock" not in self.api_key:
            decisions_url = "https://openrouter.ai/api/alpha/decisions"

            action_dict = payload.action or {}
            dec_payload = {
                "model": self.model,
                "state": {
                    "user_intent": payload.user_intent,
                    "tool": action_dict.get("tool", ""),
                    "action": action_dict,
                },
                "questions": {
                    "risk_score": {
                        "type": "score",
                        "instructions": "Evaluate the operational security risk of this agent action.",
                        "criteria": [
                            "Harmless read-only inspection",
                            "State-mutating database change or privileged command",
                        ],
                    }
                },
            }
            async with httpx.AsyncClient(timeout=t) as client:
                resp = await client.post(
                    decisions_url,
                    headers=self._headers(),
                    json=dec_payload,
                )
                if getattr(resp, "status_code", None) == 401:
                    return JEVAssessment(
                        assessment_id=f"jev_fallback_{uuid.uuid4().hex[:6]}",
                        request_id=payload.request_id,
                        risk_level=RiskLevel.MEDIUM,
                        risk_factors=["openrouter_401_unauthorized"],
                        evidence=["OpenRouter API returned 401 Unauthorized. Check OPENROUTER_API_KEY in .env."],
                        recommended_action=DecisionResult.APPROVAL_REQUIRED,
                        requires_human_review=True,
                        provider="mock_fallback",
                        latency_ms=(time.monotonic() - start) * 1000,
                    )
                resp.raise_for_status()
                data = resp.json()

            latency_ms = (time.monotonic() - start) * 1000
            score_data = data.get("answers", {}).get("risk_score", {})
            score = float(score_data.get("score", 0.5))
            confidence = score_data.get("confidence", 1.0)

            if score <= self.allow_threshold:
                risk_level = RiskLevel.LOW
                action = DecisionResult.ALLOW
                requires_human = False
                factors = ["read_only_low_risk"]
            elif score >= self.block_threshold:
                risk_level = RiskLevel.HIGH
                action = DecisionResult.APPROVAL_REQUIRED
                requires_human = True
                factors = ["high_risk_mutation_or_privileged"]
            else:
                risk_level = RiskLevel.MEDIUM
                action = DecisionResult.APPROVAL_REQUIRED
                requires_human = True
                factors = ["moderate_risk_action"]

            return JEVAssessment(
                assessment_id=data.get("id", f"jev_{uuid.uuid4().hex[:8]}"),
                request_id=payload.request_id,
                risk_level=risk_level,
                risk_factors=factors,
                evidence=[f"TypeSafe JEV assessed risk score {score:.2f} (confidence {confidence}) for {action_dict.get('tool', 'tool')}"],
                recommended_action=action,
                requires_human_review=requires_human,
                provider="typesafe-jev",
                latency_ms=latency_ms,
                raw_response=data,
            )

        system_prompt = (
            "You are JEV (Judge & Evaluation Validator), an AI security and runtime risk assessment engine "
            "intercepting AI agent tool operations before execution.\n"
            "Analyze the intercepted operation in the context of user intent, session state, and policy constraints.\n"
            "You must return ONLY a valid JSON object with the following schema, with no markdown backticks:\n"
            "{\n"
            '  "risk_level": "none" | "low" | "medium" | "high" | "critical",\n'
            '  "risk_factors": ["string describing specific risk factor"],\n'
            '  "evidence": ["string describing evidence/reasoning"],\n'
            '  "recommended_action": "allow" | "approval_required" | "block",\n'
            '  "requires_human_review": boolean\n'
            "}\n"
            "Guidelines:\n"
            "- Harmless read-only inspection (e.g. filesystem.read, diagnostic.ping): risk 'low' or 'none', recommended_action 'allow'.\n"
            "- Mutating operations, local writes: risk 'medium', recommended_action 'approval_required'.\n"
            "- Arbitrary shell execution, credential extraction, external egress: risk 'high' or 'critical', recommended_action 'block' or 'approval_required'."
        )
        user_prompt = (
            f"ASSESS THIS AGENT OPERATION:\n"
            f"User Intent: {payload.user_intent}\n"
            f"Intercepted Action:\n"
            f"{json.dumps(payload.action, indent=2)}\n"
            f"Identity: {json.dumps(payload.identity)}\n"
            f"Session Context: {json.dumps(payload.session)}\n"
            f"Policy Context: {json.dumps(payload.policy_context)}\n"
        )
        async with httpx.AsyncClient(timeout=t) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
            if getattr(resp, "status_code", None) == 401:
                return JEVAssessment(
                    assessment_id=f"jev_fallback_{uuid.uuid4().hex[:6]}",
                    request_id=payload.request_id,
                    risk_level=RiskLevel.MEDIUM,
                    risk_factors=["openrouter_401_unauthorized"],
                    evidence=["OpenRouter API returned 401 Unauthorized. Check OPENROUTER_API_KEY in .env."],
                    recommended_action=DecisionResult.APPROVAL_REQUIRED,
                    requires_human_review=True,
                    provider="mock_fallback",
                    latency_ms=(time.monotonic() - start) * 1000,
                )

            resp.raise_for_status()
            data = resp.json()


        latency_ms = (time.monotonic() - start) * 1000
        raw_content = ""
        if data.get("choices") and len(data["choices"]) > 0:
            raw_content = data["choices"][0].get("message", {}).get("content", "")

        # Clean potential markdown fences
        clean_json = raw_content.strip()
        if clean_json.startswith("```"):
            clean_json = clean_json.split("\n", 1)[-1]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
        clean_json = clean_json.strip()

        try:
            parsed = json.loads(clean_json)
        except Exception:
            parsed = {
                "risk_level": "medium",
                "risk_factors": ["unparseable_jev_response"],
                "evidence": [f"Raw response: {clean_json[:200]}"],
                "recommended_action": "approval_required",
                "requires_human_review": True,
            }

        risk_map = {
            "none": RiskLevel.NONE, "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM, "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL,
        }
        action_map = {
            "allow": DecisionResult.ALLOW, "block": DecisionResult.BLOCK,
            "approve": DecisionResult.APPROVAL_REQUIRED,
            "approval_required": DecisionResult.APPROVAL_REQUIRED,
        }
        return JEVAssessment(
            assessment_id=f"openrouter_{uuid.uuid4().hex[:8]}",
            request_id=payload.request_id,
            risk_level=risk_map.get(str(parsed.get("risk_level", "medium")).lower(), RiskLevel.MEDIUM),
            risk_factors=parsed.get("risk_factors", []),
            evidence=parsed.get("evidence", []),
            recommended_action=action_map.get(str(parsed.get("recommended_action", "approval_required")).lower(), DecisionResult.APPROVAL_REQUIRED),
            requires_human_review=bool(parsed.get("requires_human_review", False)),
            provider=f"openrouter/{self.model.split('/')[-1]}",
            latency_ms=latency_ms,
            raw_response=parsed,
        )

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    return True
                resp2 = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                return resp2.status_code == 200
        except Exception:
            return False

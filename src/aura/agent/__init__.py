"""AURA agent runtime — orchestrator, provider, Gemini integration."""
from __future__ import annotations
import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union

from aura.config import AURAConfig
from aura.models import (
    ActionRequest, AuditEvent, EventLevel,
    JEVAssessment, PolicyDecision, RunRecord, RunStatus, DecisionResult,
)
from aura.observability import (
    JSONLLogger, get_event_bus, get_metrics, get_run_repo,
)
from aura.jev import JEVClient, JEVContextBuilder, MockJEVClient, OpenRouterJEVClient
from aura.policies import PolicyEngine, ApprovalManager
from aura.gateway import ToolRegistry, ToolExecutor


class AgentMessage:
    def __init__(self, kind: str, content: Any = None, metadata: Optional[Dict] = None) -> None:
        self.kind = kind
        self.content = content
        self.metadata = metadata or {}


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self.model = "gemini-2.5-flash" if model in ("gemini-2.0-flash", "google/gemini-2.0-flash-001", "") else model
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import google.genai as genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._get_client()
            return True
        except Exception:
            return False

    async def generate(self, messages: List[Dict], system_prompt: Optional[str] = None) -> Dict:
        import google.genai as genai
        import google.genai.types as gentypes
        client = self._get_client()
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                contents.append(gentypes.Content(role="user", parts=[gentypes.Part.from_text(text=content)]))
            elif role in ("assistant", "model"):
                contents.append(gentypes.Content(role="model", parts=[gentypes.Part.from_text(text=content)]))

        tools = [
            gentypes.Tool(
                function_declarations=[
                    gentypes.FunctionDeclaration(
                        name="sqlite_query",
                        description="Execute a SQL query against the SQLite employees database. Supports SELECT, INSERT, UPDATE, DELETE.",
                        parameters=gentypes.Schema(
                            type="OBJECT",
                            properties={
                                "query": gentypes.Schema(type="STRING", description="SQL query string to run against SQLite")
                            },
                            required=["query"],
                        ),
                    ),
                    gentypes.FunctionDeclaration(
                        name="filesystem_list",
                        description="List files and subdirectories in a directory",
                        parameters=gentypes.Schema(
                            type="OBJECT",
                            properties={
                                "path": gentypes.Schema(type="STRING", description="Relative directory path (e.g. '.')")
                            },
                            required=["path"],
                        ),
                    ),
                    gentypes.FunctionDeclaration(
                        name="filesystem_read",
                        description="Read file contents from workspace",
                        parameters=gentypes.Schema(
                            type="OBJECT",
                            properties={
                                "path": gentypes.Schema(type="STRING", description="Relative file path")
                            },
                            required=["path"],
                        ),
                    ),
                    gentypes.FunctionDeclaration(
                        name="shell_execute",
                        description="Execute a safe shell command",
                        parameters=gentypes.Schema(
                            type="OBJECT",
                            properties={
                                "command": gentypes.Schema(type="STRING", description="Shell command string")
                            },
                            required=["command"],
                        ),
                    ),
                    gentypes.FunctionDeclaration(
                        name="diagnostic_ping",
                        description="Diagnostic ping to verify network connectivity",
                        parameters=gentypes.Schema(
                            type="OBJECT",
                            properties={
                                "target": gentypes.Schema(type="STRING", description="Target host or IP")
                            },
                            required=["target"],
                        ),
                    ),
                    gentypes.FunctionDeclaration(
                        name="mock_external_action",
                        description="Trigger an external mock action",
                        parameters=gentypes.Schema(
                            type="OBJECT",
                            properties={
                                "action_type": gentypes.Schema(type="STRING", description="Type of action"),
                                "payload": gentypes.Schema(type="STRING", description="Action payload"),
                            },
                        ),
                    ),
                ]
            )
        ]

        config_kwargs: Dict[str, Any] = {"tools": tools}
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        gen_config = gentypes.GenerateContentConfig(**config_kwargs)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(model=self.model, contents=contents, config=gen_config),
        )
        text = ""
        tool_calls = []
        if response.candidates:
            candidate = response.candidates[0]
            for part in (candidate.content.parts if candidate.content else []):
                if hasattr(part, "text") and part.text:
                    text += part.text
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append({"name": fc.name, "args": dict(fc.args) if fc.args else {}})
        usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            usage = {
                "input_tokens": getattr(um, "prompt_token_count", None),
                "output_tokens": getattr(um, "candidates_token_count", None),
            }
        return {"text": text, "tool_calls": tool_calls, "usage": usage}



class OpenRouterProvider:
    """OpenRouter LLM provider supporting OpenAI-compatible chat completions with function calling."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-2.0-flash-001",
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://aura.security",
            "X-Title": "AURA Agent Control Plane",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def generate(self, messages: List[Dict], system_prompt: Optional[str] = None) -> Dict:
        import httpx
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "filesystem_list",
                    "description": "List files and subdirectories in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative directory path (e.g. '.' or 'src')"}
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "filesystem_read",
                    "description": "Read the contents of a text file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative file path"}
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "shell_execute",
                    "description": "Execute a safe shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Command string to run"}
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "diagnostic_ping",
                    "description": "Ping a target host to verify connectivity",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "Target hostname or IP"}
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mock_external_action",
                    "description": "Trigger an external mock action",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action_type": {"type": "string", "description": "Type of action"},
                            "payload": {"type": "string", "description": "Action payload"}
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "sqlite_query",
                    "description": "Execute a SQL query against the SQLite employees database. Supports SELECT queries (on employees and departments tables) and mutating statements (INSERT, UPDATE, DELETE).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL query to execute against SQLite database (e.g. 'SELECT * FROM employees LIMIT 10;', 'UPDATE employees SET salary = salary + 5000 WHERE id = 1;')"
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            formatted_messages.append({"role": role, "content": content})

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            if getattr(resp, "status_code", None) == 401:
                raise PermissionError(
                    "OpenRouter API key is invalid or unauthorized (HTTP 401). "
                    "Please update OPENROUTER_API_KEY in your .env file with your real key (sk-or-v1-...). "
                    "Or set AURA_LLM_PROVIDER=mock to test in zero-key offline mode."
                )

            resp.raise_for_status()
            data = resp.json()


        choice = data["choices"][0]
        msg = choice.get("message", {})
        text = msg.get("content") or ""
        tool_calls = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        fn_args = json.loads(raw_args)
                    except Exception:
                        fn_args = {}
                else:
                    fn_args = raw_args or {}
                tool_calls.append({"name": fn_name, "args": fn_args})

        usage = None
        if data.get("usage"):
            usage = {
                "input_tokens": data["usage"].get("prompt_tokens"),
                "output_tokens": data["usage"].get("completion_tokens"),
            }
        return {"text": text, "tool_calls": tool_calls, "usage": usage}


class MockLLMProvider:
    """Mock agent LLM provider for zero-key local demos and tests."""

    def __init__(self, model: str = "mock-agent") -> None:
        self.model = model

    async def health_check(self) -> bool:
        return True

    async def generate(self, messages: List[Dict], system_prompt: Optional[str] = None) -> Dict:
        await asyncio.sleep(0.15)
        last_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_msg = str(m.get("content", "")).lower()
                break

        if any("[BLOCKED" in str(m.get("content", "")) or "[SUCCESS" in str(m.get("content", "")) for m in messages):
            return {
                "text": "Completed intercepted actions according to AURA security policies.",
                "tool_calls": [],
                "usage": {"input_tokens": 110, "output_tokens": 28},
            }

        if any(w in last_msg for w in ("list", "ls", "dir", "files")):
            return {
                "text": "Listing the files in the workspace directory:",
                "tool_calls": [{"name": "filesystem_list", "args": {"path": "."}}],
                "usage": {"input_tokens": 75, "output_tokens": 30},
            }
        elif any(w in last_msg for w in ("read", "cat", "view", "open")):
            return {
                "text": "Reading file contents:",
                "tool_calls": [{"name": "filesystem_read", "args": {"path": "pyproject.toml"}}],
                "usage": {"input_tokens": 80, "output_tokens": 32},
            }
        elif any(w in last_msg for w in ("shell", "exec", "cmd", "run", "whoami")):
            cmd = "whoami" if "whoami" in last_msg else "dir"
            return {
                "text": f"Requesting shell command: `{cmd}`",
                "tool_calls": [{"name": "shell_execute", "args": {"command": cmd}}],
                "usage": {"input_tokens": 85, "output_tokens": 35},
            }
        elif any(w in last_msg for w in ("ping", "network", "connect")):
            return {
                "text": "Testing connectivity with diagnostic ping:",
                "tool_calls": [{"name": "diagnostic_ping", "args": {"target": "127.0.0.1"}}],
                "usage": {"input_tokens": 70, "output_tokens": 25},
            }
        elif any(w in last_msg for w in ("select", "sql", "employee", "department", "salary", "database", "sqlite", "table", "update", "insert", "delete")):
            if any(w in last_msg for w in ("update", "raise", "increase")):
                q = "UPDATE employees SET salary = salary + 5000 WHERE department_id = 1;"
            elif "delete" in last_msg:
                q = "DELETE FROM employees WHERE id = 10;"
            elif "insert" in last_msg:
                q = "INSERT INTO departments (name, budget) VALUES ('Data Analytics', 120000);"
            elif "department" in last_msg:
                q = "SELECT id, name, budget, created_at FROM departments;"
            elif "salary" in last_msg or "top" in last_msg or "highest" in last_msg:
                q = "SELECT id, name, role, salary FROM employees ORDER BY salary DESC LIMIT 5;"
            else:
                q = "SELECT id, name, role, department_id, salary, hire_date FROM employees LIMIT 10;"
            return {
                "text": f"Executing SQLite database query against employees database:\n`{q}`",
                "tool_calls": [{"name": "sqlite_query", "args": {"query": q}}],
                "usage": {"input_tokens": 85, "output_tokens": 45},
            }
        else:
            return {
                "text": f"Hello! I am AURA Agent running in protected mode. You said: '{last_msg}'. You can ask me to list files, read a file, query the SQLite employees database, or execute commands to see AURA risk interception and policy enforcement.",
                "tool_calls": [],
                "usage": {"input_tokens": 50, "output_tokens": 45},
            }


class AURAOrchestrator:
    """Central orchestrator connecting agent, gateway, JEV, and policies."""

    SYSTEM_PROMPT = (
        "You are an AI assistant running inside AURA — the Agent Control Plane. "
        "AURA intercepts all your tool calls for security assessment before execution. "
        "You have access to: filesystem.list, filesystem.read, shell.execute, "
        "diagnostic.ping, mock.external_action, sqlite.query. "
        "For database tasks, query the local SQLite database using sqlite_query. "
        "The database contains 'employees' (id, name, role, department_id, salary, hire_date) "
        "and 'departments' (id, name, budget, created_at). "
        "Be helpful and transparent about the actions you take."
    )


    def __init__(
        self,
        config: AURAConfig,
        on_status_update: Optional[Callable[[str], None]] = None,
        on_approval_needed: Optional[Callable] = None,
    ) -> None:
        self.config = config
        self.on_status_update = on_status_update
        self.on_approval_needed = on_approval_needed

        self.event_bus = get_event_bus()
        self.metrics = get_metrics()
        self.run_repo = get_run_repo()
        self.jsonl_logger = JSONLLogger(config.runtime.data_dir / "logs")

        self.registry = ToolRegistry(config.runtime.workspace_root)
        self.executor = ToolExecutor(self.registry)

        # JEV Client selection
        if not config.jev.mock_mode and config.jev.api_key:
            if "openrouter" in (config.jev.endpoint or "https://openrouter.ai") or config.jev.provider in ("openrouter", "jev") or config.jev.api_key.startswith("sk-or-"):
                self.jev_client: Union[OpenRouterJEVClient, JEVClient, MockJEVClient] = OpenRouterJEVClient(
                    api_key=config.jev.api_key,
                    model=config.jev.model,
                    base_url=config.jev.endpoint or "https://openrouter.ai/api/v1",
                    timeout=config.jev.timeout_seconds,
                    allow_threshold=config.jev.allow_threshold,
                    block_threshold=config.jev.block_threshold,
                )
                self.jev_mode = "openrouter"
            else:
                self.jev_client = JEVClient(
                    endpoint=config.jev.endpoint or "https://openrouter.ai/api/v1",
                    api_key=config.jev.api_key,
                    timeout=config.jev.timeout_seconds,
                )
                self.jev_mode = "live"
        elif config.jev.provider in ("openrouter", "jev") and config.jev.api_key:
            self.jev_client = OpenRouterJEVClient(
                api_key=config.jev.api_key,
                model=config.jev.model,
                base_url=config.jev.endpoint or "https://openrouter.ai/api/v1",
                timeout=config.jev.timeout_seconds,
                allow_threshold=config.jev.allow_threshold,
                block_threshold=config.jev.block_threshold,
            )
            self.jev_mode = "openrouter"
        else:
            self.jev_client = MockJEVClient()
            self.jev_mode = "mock"

        self.context_builder = JEVContextBuilder()
        self.policy_engine = PolicyEngine(config.runtime.workspace_root)
        self.approval_manager = ApprovalManager()

        # LLM Provider selection
        if config.llm.provider == "openrouter" and config.llm.api_key:
            self.provider: Union[OpenRouterProvider, GeminiProvider, MockLLMProvider] = OpenRouterProvider(
                api_key=config.llm.api_key,
                model=config.llm.model,
                base_url=config.llm.base_url or "https://openrouter.ai/api/v1",
            )
        elif config.llm.provider == "gemini" and config.llm.api_key:
            self.provider = GeminiProvider(api_key=config.llm.api_key, model=config.llm.model)
        else:
            self.provider = MockLLMProvider()

        self.event_bus.subscribe_all(self.metrics.on_audit_event)
        self.event_bus.subscribe_all(self._log_to_jsonl)

        self.session_id = f"session_{uuid.uuid4().hex[:8]}"
        self.current_run: Optional[RunRecord] = None
        self._cancelled = False

    async def _log_to_jsonl(self, event: AuditEvent) -> None:
        await self.jsonl_logger.log(event)

    async def _emit(self, event: AuditEvent) -> None:
        await self.event_bus.emit(event)

    def _status(self, msg: str) -> None:
        if self.on_status_update:
            self.on_status_update(msg)

    def cancel(self) -> None:
        """Cancel current active run and resolve any waiting approvals."""
        self._cancelled = True
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self.approval_manager.resolve_all_pending("cancelled"))
        except RuntimeError:
            pass

    async def health_check_provider(self) -> bool:

        try:
            result = await self.provider.health_check()
            self.metrics.agent_connected = result
            return result
        except Exception:
            self.metrics.agent_connected = False
            return False

    async def health_check_jev(self) -> bool:
        try:
            result = await self.jev_client.health_check()
            self.metrics.jev_connected = result
            return result
        except Exception:
            self.metrics.jev_connected = False
            return False

    async def run(
        self,
        prompt: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[AgentMessage, None]:
        self._cancelled = False
        run = RunRecord(
            session_id=self.session_id,
            user_prompt=prompt,
            provider=self.config.llm.provider,
            model=self.config.llm.model,
        )
        self.current_run = run
        await self.run_repo.save(run)

        await self._emit(AuditEvent(
            level=EventLevel.INFO,
            event_type="aura.run.started",
            session_id=self.session_id,
            run_id=run.run_id,
            actor={"type": "user"},
            metadata={"schema_version": "1.0", "prompt_length": len(prompt)},
        ))
        run.add_event("aura.run.started")
        yield AgentMessage("run_started", {"run_id": run.run_id})

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": prompt})

        turn_count = 0
        tool_call_count = 0
        action_trace: List[Dict] = []

        try:
            while turn_count < self.config.runtime.max_agent_turns:
                if self._cancelled:
                    break
                turn_count += 1
                self._status(f"Agent thinking... (turn {turn_count})")

                try:
                    response = await asyncio.wait_for(
                        self.provider.generate(messages=messages, system_prompt=self.SYSTEM_PROMPT),
                        timeout=60.0,
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError("LLM response timed out")

                if response.get("usage"):
                    usage = response["usage"]
                    in_tok = usage.get("input_tokens") or 0
                    out_tok = usage.get("output_tokens") or 0
                    run.input_tokens = (run.input_tokens or 0) + in_tok
                    run.output_tokens = (run.output_tokens or 0) + out_tok
                    await self._emit(AuditEvent(
                        level=EventLevel.INFO,
                        event_type="aura.agent.token_usage",
                        session_id=self.session_id,
                        run_id=run.run_id,
                        metadata={
                            "schema_version": "1.0",
                            "input_tokens": in_tok,
                            "output_tokens": out_tok,
                        },
                    ))
                    yield AgentMessage("token_usage", {"input_tokens": in_tok, "output_tokens": out_tok})

                text = response.get("text", "")
                tool_calls = response.get("tool_calls", [])

                if text:
                    await self._emit(AuditEvent(
                        level=EventLevel.INFO,
                        event_type="aura.agent.response",
                        session_id=self.session_id,
                        run_id=run.run_id,
                        actor={"type": "agent", "model": self.config.llm.model},
                        metadata={"schema_version": "1.0", "summary": text[:120].strip(), "chars": len(text)},
                    ))
                    yield AgentMessage("agent_text", text)
                    messages.append({"role": "assistant", "content": text})

                if not tool_calls:
                    break

                tool_results_for_next_turn = []
                for tc in tool_calls:
                    if self._cancelled:
                        break
                    if tool_call_count >= self.config.runtime.max_tool_calls:
                        yield AgentMessage("warning", "Maximum tool call limit reached.")
                        break
                    tool_call_count += 1
                    raw_name = tc.get("name", "")
                    tool_name = raw_name.replace("_", ".", 1) if "_" in raw_name else raw_name
                    args = tc.get("args", {})

                    request = ActionRequest(
                        tool=tool_name,
                        arguments=args,
                        target=str(args.get("path") or args.get("target") or ""),
                    )
                    request = self.registry.enrich_request(request)
                    run.total_tool_calls += 1

                    self._status(f"Intercepting: {tool_name}")
                    yield AgentMessage("tool_proposed", {"tool": tool_name, "args": args, "request_id": request.request_id})

                    await self._emit(AuditEvent(
                        level=EventLevel.INFO, event_type="aura.action.proposed",
                        session_id=self.session_id, run_id=run.run_id,
                        request_id=request.request_id,
                        actor={"type": "agent"},
                        action={"tool": tool_name, "operation": request.operation, "target": request.target},
                    ))
                    await self._emit(AuditEvent(
                        level=EventLevel.INFO, event_type="aura.action.intercepted",
                        session_id=self.session_id, run_id=run.run_id,
                        request_id=request.request_id,
                        actor={"type": "aura_gateway"},
                        action={"tool": tool_name},
                        jev={"status": "pending"},
                        decision={"result": "pending"},
                        execution={"status": "not_started"},
                    ))

                    # Pre-assessment deterministic check
                    pre_decision = self.policy_engine.pre_assessment_check(request)
                    if pre_decision and pre_decision.decision == DecisionResult.BLOCK:
                        pre_decision.enforced = True
                        run.blocked_actions += 1
                        action_trace.append({"index": tool_call_count, "tool": tool_name, "decision": "BLOCKED", "reason": pre_decision.reason})
                        await self._emit(AuditEvent(
                            level=EventLevel.WARNING, event_type="aura.policy.decision",
                            session_id=self.session_id, run_id=run.run_id,
                            request_id=request.request_id,
                            decision={"result": "block", "reason": pre_decision.reason, "policy_rule_id": pre_decision.policy_rule_id},
                        ))
                        await self._emit(AuditEvent(
                            level=EventLevel.WARNING, event_type="aura.action.blocked",
                            session_id=self.session_id, run_id=run.run_id,
                            request_id=request.request_id,
                            action={"tool": tool_name},
                        ))
                        run.add_event("aura.action.blocked", {"tool": tool_name, "reason": pre_decision.reason})
                        yield AgentMessage("action_blocked", {
                            "tool": tool_name, "request_id": request.request_id,
                            "reason": pre_decision.reason, "policy_rule_id": pre_decision.policy_rule_id,
                        })
                        tool_results_for_next_turn.append({"tool_name": raw_name, "result": f"[BLOCKED: {pre_decision.reason}]"})
                        continue

                    # Fast allow
                    assessment = None
                    if self.policy_engine.fast_allow(request):
                        final_decision = PolicyDecision(
                            request_id=request.request_id,
                            decision=DecisionResult.ALLOW,
                            reason="Fast-allow: harmless diagnostic tool",
                            policy_rule_id="POLICY-FAST-001",
                            enforced=True,
                        )
                    else:
                        # JEV Assessment
                        self._status(f"JEV assessing: {tool_name}...")
                        jev_payload = self.context_builder.build(request=request, user_intent=prompt, run=run)
                        await self._emit(AuditEvent(
                            level=EventLevel.INFO, event_type="aura.jev.assessment.started",
                            session_id=self.session_id, run_id=run.run_id,
                            request_id=request.request_id,
                            action={"tool": tool_name, "operation": request.operation, "target": request.target},
                            jev={"status": "started", "mode": self.jev_mode, "model": self.config.jev.model},
                        ))
                        jev_start = time.monotonic()
                        try:
                            assessment = await asyncio.wait_for(
                                self.jev_client.assess(jev_payload),
                                timeout=self.config.jev.timeout_seconds,
                            )
                            jev_latency = (time.monotonic() - jev_start) * 1000
                            run.jev_assessments += 1
                            await self._emit(AuditEvent(
                                level=EventLevel.INFO, event_type="aura.jev.assessment.completed",
                                session_id=self.session_id, run_id=run.run_id,
                                request_id=request.request_id,
                                assessment_id=assessment.assessment_id,
                                action={"tool": tool_name, "operation": request.operation, "target": request.target},
                                jev={
                                    "status": "completed", "risk_level": assessment.risk_level.value,
                                    "recommended_action": assessment.recommended_action.value,
                                    "latency_ms": jev_latency, "mode": self.jev_mode,
                                    "provider": assessment.provider,
                                },
                            ))
                            yield AgentMessage("jev_assessed", {
                                "request_id": request.request_id,
                                "risk_level": assessment.risk_level.value,
                                "recommended_action": assessment.recommended_action.value,
                                "factors": assessment.risk_factors,
                            })
                        except asyncio.TimeoutError:
                            jev_latency = (time.monotonic() - jev_start) * 1000
                            await self._emit(AuditEvent(
                                level=EventLevel.ERROR, event_type="aura.jev.assessment.failed",
                                session_id=self.session_id, run_id=run.run_id,
                                request_id=request.request_id,
                                jev={"status": "timeout", "latency_ms": jev_latency},
                            ))
                            final_decision = PolicyDecision(
                                request_id=request.request_id,
                                decision=DecisionResult.APPROVAL_REQUIRED,
                                reason="JEV timeout — fail-closed: human approval required",
                                policy_rule_id="POLICY-JEV-TIMEOUT",
                                requires_human_review=True,
                                enforced=False,
                            )
                            assessment = None
                        except Exception as e:
                            await self._emit(AuditEvent(
                                level=EventLevel.ERROR, event_type="aura.jev.assessment.failed",
                                session_id=self.session_id, run_id=run.run_id,
                                request_id=request.request_id,
                                jev={"status": "error", "error": str(e)},
                            ))
                            final_decision = PolicyDecision(
                                request_id=request.request_id,
                                decision=DecisionResult.APPROVAL_REQUIRED,
                                reason=f"JEV error: {e}",
                                policy_rule_id="POLICY-JEV-ERROR",
                                requires_human_review=True,
                                enforced=False,
                            )
                            assessment = None

                        if assessment is not None:
                            final_decision = self.policy_engine.apply_jev_assessment(request, assessment)

                    # Policy decision
                    await self._emit(AuditEvent(
                        level=EventLevel.INFO, event_type="aura.policy.decision",
                        session_id=self.session_id, run_id=run.run_id,
                        request_id=request.request_id,
                        assessment_id=assessment.assessment_id if assessment else None,
                        action={"tool": tool_name, "operation": request.operation, "target": request.target},
                        decision={
                            "result": final_decision.decision.value,
                            "reason": final_decision.reason,
                            "policy_rule_id": final_decision.policy_rule_id,
                        },
                    ))

                    if final_decision.decision == DecisionResult.BLOCK:
                        run.blocked_actions += 1
                        action_trace.append({"index": tool_call_count, "tool": tool_name, "decision": "BLOCKED"})
                        await self._emit(AuditEvent(
                            level=EventLevel.WARNING, event_type="aura.action.blocked",
                            session_id=self.session_id, run_id=run.run_id,
                            request_id=request.request_id, action={"tool": tool_name},
                        ))
                        run.add_event("aura.action.blocked", {"tool": tool_name})
                        yield AgentMessage("action_blocked", {
                            "tool": tool_name, "request_id": request.request_id,
                            "reason": final_decision.reason,
                            "assessment": {"risk_level": assessment.risk_level.value, "factors": assessment.risk_factors} if assessment else None,
                        })
                        tool_results_for_next_turn.append({"tool_name": raw_name, "result": f"[BLOCKED: {final_decision.reason}]"})

                    elif final_decision.decision == DecisionResult.APPROVAL_REQUIRED:
                        run.pending_approvals += 1
                        approval_id = await self.approval_manager.request_approval(request, final_decision, assessment)
                        await self._emit(AuditEvent(
                            level=EventLevel.WARNING, event_type="aura.approval.requested",
                            session_id=self.session_id, run_id=run.run_id,
                            request_id=request.request_id,
                            action={"tool": tool_name, "operation": request.operation, "target": request.target},
                            decision={"result": "approval_required", "reason": final_decision.reason},
                            metadata={"schema_version": "1.0", "approval_id": approval_id, "tool": tool_name},
                        ))
                        yield AgentMessage("approval_requested", {
                            "approval_id": approval_id, "tool": tool_name,
                            "request_id": request.request_id, "reason": final_decision.reason,
                            "assessment": {
                                "risk_level": assessment.risk_level.value,
                                "factors": assessment.risk_factors,
                                "evidence": assessment.evidence,
                            } if assessment else None,
                        })
                        if self.on_approval_needed:
                            cb_res = self.on_approval_needed({
                                "approval_id": approval_id, "tool": tool_name,
                                "args": args, "reason": final_decision.reason,
                                "assessment": assessment,
                            })
                            if asyncio.iscoroutine(cb_res):
                                await cb_res
                        resolution = await self.approval_manager.wait_for_resolution(approval_id, timeout=120.0)

                        run.pending_approvals = max(0, run.pending_approvals - 1)
                        await self._emit(AuditEvent(
                            level=EventLevel.INFO, event_type="aura.approval.resolved",
                            session_id=self.session_id, run_id=run.run_id,
                            request_id=request.request_id,
                            action={"tool": tool_name, "operation": request.operation, "target": request.target},
                            metadata={"schema_version": "1.0", "resolution": resolution, "tool": tool_name},
                        ))
                        if resolution == "approved":
                            recheck = self.policy_engine.pre_assessment_check(request)
                            if recheck and recheck.decision == DecisionResult.BLOCK:
                                yield AgentMessage("action_blocked", {"tool": tool_name, "reason": "Revalidation failed"})
                                tool_results_for_next_turn.append({"tool_name": raw_name, "result": "[BLOCKED: revalidation failed]"})
                                continue
                            exec_result = await self.executor.execute(request)
                            action_trace.append({"index": tool_call_count, "tool": tool_name, "decision": "APPROVED"})
                            run.allowed_actions += 1
                            run.add_event("aura.action.executed", {"tool": tool_name})
                            yield AgentMessage("action_executed", {
                                "tool": tool_name, "request_id": request.request_id,
                                "success": exec_result.success, "output": exec_result.output,
                            })
                            tool_results_for_next_turn.append({
                                "tool_name": raw_name,
                                "result": json.dumps(exec_result.output) if exec_result.success else f"[ERROR: {exec_result.error}]",
                            })
                        else:
                            run.blocked_actions += 1
                            action_trace.append({"index": tool_call_count, "tool": tool_name, "decision": f"DENIED ({resolution})"})
                            yield AgentMessage("action_blocked", {
                                "tool": tool_name, "request_id": request.request_id,
                                "reason": f"Human denied ({resolution})",
                            })
                            tool_results_for_next_turn.append({"tool_name": raw_name, "result": f"[DENIED: {resolution}]"})

                    else:  # ALLOW
                        self._status(f"Executing: {tool_name}")
                        exec_result = await self.executor.execute(request)
                        etype = "aura.action.executed" if exec_result.success else "aura.action.failed"
                        await self._emit(AuditEvent(
                            level=EventLevel.INFO if exec_result.success else EventLevel.ERROR,
                            event_type=etype,
                            session_id=self.session_id, run_id=run.run_id,
                            request_id=request.request_id,
                            action={"tool": tool_name},
                            execution={
                                "status": "completed" if exec_result.success else "failed",
                                "duration_ms": exec_result.duration_ms,
                                "error_code": exec_result.error,
                            },
                        ))
                        if exec_result.success:
                            run.allowed_actions += 1
                            action_trace.append({"index": tool_call_count, "tool": tool_name, "decision": "ALLOWED"})
                            run.add_event("aura.action.executed", {"tool": tool_name})
                        else:
                            action_trace.append({"index": tool_call_count, "tool": tool_name, "decision": "FAILED"})
                            run.add_event("aura.action.failed", {"tool": tool_name, "error": exec_result.error})
                        yield AgentMessage("action_executed", {
                            "tool": tool_name, "request_id": request.request_id,
                            "success": exec_result.success, "output": exec_result.output,
                            "error": exec_result.error,
                        })
                        result_str = json.dumps(exec_result.output) if exec_result.success else f"[ERROR: {exec_result.error}]"
                        tool_results_for_next_turn.append({"tool_name": raw_name, "result": result_str})

                if tool_results_for_next_turn:
                    parts = [f"Tool result for {tr['tool_name']}: {tr['result']}" for tr in tool_results_for_next_turn]
                    messages.append({"role": "user", "content": "\n".join(parts)})

            status = RunStatus.CANCELLED if self._cancelled else RunStatus.COMPLETED
            await self.run_repo.update_status(run.run_id, status)
            run.add_event("aura.run.completed")
            await self._emit(AuditEvent(
                level=EventLevel.INFO, event_type="aura.run.completed",
                session_id=self.session_id, run_id=run.run_id,
                execution={"status": status.value, "duration_ms": run.duration_ms, "tool_calls": tool_call_count},
            ))
            yield AgentMessage("run_completed", {
                "run_id": run.run_id, "status": status.value,
                "action_trace": action_trace, "tool_calls": tool_call_count,
                "allowed": run.allowed_actions, "blocked": run.blocked_actions,
                "jev_assessments": run.jev_assessments,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "duration_ms": run.duration_ms,
            })

        except Exception as e:
            await self.run_repo.update_status(run.run_id, RunStatus.FAILED, error=str(e))
            run.add_event("aura.run.failed", {"error": str(e)})
            await self._emit(AuditEvent(
                level=EventLevel.ERROR, event_type="aura.run.failed",
                session_id=self.session_id, run_id=run.run_id,
                metadata={"schema_version": "1.0", "error": str(e)},
            ))
            yield AgentMessage("run_failed", {"error": str(e), "run_id": run.run_id})

    def cancel(self) -> None:
        self._cancelled = True

"""AURA execution gateway — tool registry, interceptor, executor."""
from __future__ import annotations
import os
import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from aura.models import (
    ActionRequest, ActionResult, ActionStatus,
    AuditEvent, EventLevel,
)


# ── Tool Registry ─────────────────────────────────────────────────────────────

class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        operation: str,
        risk_level: str,
        reversible: bool,
        handler: Callable,
        data_classification: str = "internal",
    ) -> None:
        self.name = name
        self.description = description
        self.operation = operation
        self.risk_level = risk_level
        self.reversible = reversible
        self.handler = handler
        self.data_classification = data_classification

    def to_gemini_declaration(self) -> Dict[str, Any]:
        return {
            "name": self.name.replace(".", "_"),
            "description": self.description,
        }


# ── Built-in Tool Handlers ────────────────────────────────────────────────────

async def _handle_fs_list(args: Dict[str, Any], workspace: Path) -> Any:
    path_str = args.get("path", ".")
    target = (workspace / path_str).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise PermissionError(f"Path '{path_str}' is outside workspace")
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {path_str}")
    entries = []
    for entry in sorted(target.iterdir()):
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        })
    return {"path": str(path_str), "entries": entries, "count": len(entries)}


async def _handle_fs_read(args: Dict[str, Any], workspace: Path) -> Any:
    path_str = args.get("path", "")
    if not path_str:
        raise ValueError("path argument is required")
    target = (workspace / path_str).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise PermissionError(f"Path '{path_str}' is outside workspace")
    if not target.exists():
        raise FileNotFoundError(f"File not found: {path_str}")
    if target.stat().st_size > 100_000:
        raise ValueError(f"File too large to read: {target.stat().st_size} bytes")
    content = target.read_text(encoding="utf-8", errors="replace")
    return {"path": str(path_str), "content": content[:5000], "size": target.stat().st_size}


async def _handle_fs_write(args: Dict[str, Any], workspace: Path) -> Any:
    path_str = args.get("path", "")
    content = args.get("content", "")
    if not path_str:
        raise ValueError("path argument is required")
    target = (workspace / path_str).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise PermissionError(f"Path '{path_str}' is outside workspace")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": str(path_str), "bytes_written": len(content.encode())}


async def _handle_shell_execute(args: Dict[str, Any], workspace: Path) -> Any:
    cmd = args.get("command", "")
    # Only allow a very restricted set of safe commands
    ALLOWED_PREFIXES = ["echo ", "ls", "dir", "pwd", "whoami", "date", "python --version"]
    allowed = any(cmd.strip().startswith(p) for p in ALLOWED_PREFIXES)
    if not allowed:
        raise PermissionError(f"Command not in allowlist: '{cmd}'")
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(workspace),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except asyncio.TimeoutError:
        proc.kill()
        raise TimeoutError("Command timed out after 10 seconds")
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[:2000],
        "stderr": stderr.decode("utf-8", errors="replace")[:500],
    }


async def _handle_diagnostic_ping(args: Dict[str, Any], workspace: Path) -> Any:
    return {"status": "ok", "message": "AURA diagnostic ping successful", "workspace": str(workspace)}


async def _handle_mock_external(args: Dict[str, Any], workspace: Path) -> Any:
    action = args.get("action", "simulate")
    target = args.get("target", "external-service")
    return {"status": "simulated", "action": action, "target": target, "note": "Mock external action — no real side effects"}


async def _handle_sqlite_query(args: Dict[str, Any], workspace: Path) -> Any:
    from aura.database import run_sqlite_query
    query = args.get("query", "")
    if not query:
        raise ValueError("query argument is required")
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: run_sqlite_query(query))
    return res


class ToolRegistry:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(ToolDefinition(
            name="filesystem.list", description="List directory contents within the workspace",
            operation="list", risk_level="low", reversible=True,
            handler=lambda args: _handle_fs_list(args, self.workspace_root),
        ))
        self.register(ToolDefinition(
            name="filesystem.read", description="Read a file within the workspace",
            operation="read", risk_level="low", reversible=True,
            handler=lambda args: _handle_fs_read(args, self.workspace_root),
        ))
        self.register(ToolDefinition(
            name="filesystem.write", description="Write a file within the workspace sandbox",
            operation="write", risk_level="medium", reversible=False,
            handler=lambda args: _handle_fs_write(args, self.workspace_root),
            data_classification="internal",
        ))
        self.register(ToolDefinition(
            name="sqlite.query", description="Execute an SQL query against the SQLite employee database",
            operation="query", risk_level="low", reversible=True,
            handler=lambda args: _handle_sqlite_query(args, self.workspace_root),
        ))
        self.register(ToolDefinition(
            name="sqlite.execute", description="Execute an SQL statement against the SQLite employee database",
            operation="query", risk_level="low", reversible=True,
            handler=lambda args: _handle_sqlite_query(args, self.workspace_root),
        ))
        self.register(ToolDefinition(
            name="shell.execute", description="Execute a restricted shell command",
            operation="execute", risk_level="high", reversible=False,
            handler=lambda args: _handle_shell_execute(args, self.workspace_root),
        ))
        self.register(ToolDefinition(
            name="diagnostic.ping", description="Diagnostic health check ping",
            operation="ping", risk_level="none", reversible=True,
            handler=lambda args: _handle_diagnostic_ping(args, self.workspace_root),
        ))
        self.register(ToolDefinition(
            name="mock.external_action", description="Simulate interaction with an external service",
            operation="send", risk_level="high", reversible=False,
            handler=lambda args: _handle_mock_external(args, self.workspace_root),
            data_classification="confidential",
        ))

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def all_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def gemini_declarations(self) -> List[Dict[str, Any]]:
        return [t.to_gemini_declaration() for t in self._tools.values()]

    def enrich_request(self, request: ActionRequest) -> ActionRequest:
        tool_def = self._tools.get(request.tool)
        if tool_def:
            request.operation = request.operation or tool_def.operation
            request.data_classification = tool_def.data_classification
            request.reversible = tool_def.reversible

        if request.tool in ("sqlite.query", "sqlite.execute", "sqlite_query", "sqlite_execute"):
            q = str(request.arguments.get("query", "")).strip().upper()
            if not q.startswith(("SELECT", "PRAGMA", "EXPLAIN", "WITH")):
                request.operation = "mutate"
                request.reversible = False
                request.target = f"sqlite:employees ({q[:30]}...)"
            else:
                request.operation = "query"
                request.reversible = True
                request.target = f"sqlite:employees ({q[:30]}...)"

        return request



# ── Executor ──────────────────────────────────────────────────────────────────

class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute(self, request: ActionRequest) -> ActionResult:
        tool_def = self.registry.get(request.tool)
        if not tool_def:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                error=f"Tool '{request.tool}' not found in registry",
            )
        start = time.monotonic()
        try:
            output = await tool_def.handler(request.arguments)
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                request_id=request.request_id,
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            return ActionResult(
                request_id=request.request_id,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

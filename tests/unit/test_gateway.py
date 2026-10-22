"""Unit tests for the AURA tool gateway."""
import pytest
from pathlib import Path
from aura.gateway import ToolRegistry, ToolExecutor
from aura.models import ActionRequest


@pytest.fixture
def registry(tmp_path):
    (tmp_path / "testfile.txt").write_text("hello world")
    return ToolRegistry(workspace_root=tmp_path)


@pytest.fixture
def executor(registry):
    return ToolExecutor(registry)


@pytest.mark.asyncio
async def test_filesystem_list(tmp_path, registry, executor):
    req = ActionRequest(tool="filesystem.list", arguments={"path": "."})
    result = await executor.execute(req)
    assert result.success
    assert "entries" in result.output


@pytest.mark.asyncio
async def test_filesystem_read(tmp_path, registry, executor):
    req = ActionRequest(tool="filesystem.read", arguments={"path": "testfile.txt"})
    result = await executor.execute(req)
    assert result.success
    assert "hello world" in result.output["content"]


@pytest.mark.asyncio
async def test_filesystem_read_not_found(tmp_path, registry, executor):
    req = ActionRequest(tool="filesystem.read", arguments={"path": "nonexistent.txt"})
    result = await executor.execute(req)
    assert not result.success
    assert result.error


@pytest.mark.asyncio
async def test_path_traversal_blocked_in_executor(tmp_path, registry, executor):
    req = ActionRequest(tool="filesystem.read", arguments={"path": "../../etc/passwd"})
    result = await executor.execute(req)
    assert not result.success


@pytest.mark.asyncio
async def test_diagnostic_ping(registry, executor):
    req = ActionRequest(tool="diagnostic.ping")
    result = await executor.execute(req)
    assert result.success
    assert result.output["status"] == "ok"


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(registry, executor):
    req = ActionRequest(tool="unknown.tool")
    result = await executor.execute(req)
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_shell_execute_blocked_command(registry, executor):
    req = ActionRequest(tool="shell.execute", arguments={"command": "rm -rf /"})
    result = await executor.execute(req)
    assert not result.success
    assert "allowlist" in result.error.lower()


@pytest.mark.asyncio
async def test_shell_execute_allowed_command(registry, executor):
    req = ActionRequest(tool="shell.execute", arguments={"command": "echo hello"})
    result = await executor.execute(req)
    assert result.success
    assert "hello" in result.output["stdout"]


@pytest.mark.asyncio
async def test_sqlite_query_select(registry, executor):
    req = ActionRequest(tool="sqlite.query", arguments={"query": "SELECT * FROM employees LIMIT 3;"})
    enriched = registry.enrich_request(req)
    assert enriched.operation == "query"
    assert enriched.reversible is True
    result = await executor.execute(enriched)
    assert result.success
    assert "table" in result.output
    assert "+" in result.output["table"]
    assert result.output["row_count"] == 3


@pytest.mark.asyncio
async def test_sqlite_query_mutate_enrichment(registry):
    req = ActionRequest(tool="sqlite.query", arguments={"query": "UPDATE employees SET salary = salary + 100;"})
    enriched = registry.enrich_request(req)
    assert enriched.operation == "mutate"
    assert enriched.reversible is False

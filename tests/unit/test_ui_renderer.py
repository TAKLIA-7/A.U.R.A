"""Unit tests for AURA TUI Renderer adapted from create-agent-tui."""
import pytest
from aura.ui.renderer import (
    TuiRenderer, format_tokens, format_duration, summarize_args, trunc,
)


def test_format_tokens():
    assert format_tokens(None) == "0"
    assert format_tokens(0) == "0"
    assert format_tokens(850) == "850"
    assert format_tokens(1000) == "1.0k"
    assert format_tokens(1250) == "1.2k"
    assert format_tokens(1300) == "1.3k"
    assert format_tokens(24500) == "24.5k"


def test_format_duration():
    assert format_duration(None) == ""
    assert format_duration(0) == ""
    assert format_duration(50) == "(50ms)"
    assert format_duration(450) == "(450ms)"
    assert format_duration(1000) == "(1.0s)"
    assert format_duration(2500) == "(2.5s)"


def test_trunc():
    assert trunc("short", 10) == "short"
    assert trunc("a very long string that needs truncation", 12) == "a very long…"


def test_summarize_args():
    # SQLite
    res = summarize_args("sqlite.query", {"query": "SELECT * FROM employees LIMIT 5;"})
    assert "query=" in res
    assert "SELECT" in res

    # Shell
    res = summarize_args("shell.execute", {"command": "whoami"})
    assert res == "command='whoami'"

    # Filesystem
    res = summarize_args("filesystem.read", {"path": "pyproject.toml"})
    assert res == "path='pyproject.toml'"

    # Empty
    assert summarize_args("tool", {}) == ""


def test_tui_renderer_modes():
    # Grouped mode
    r_grouped = TuiRenderer(display_mode="grouped")
    t_prop = r_grouped.render_tool_proposed("sqlite.query", {"query": "SELECT 1;"})
    assert t_prop is not None
    assert "Executed SQL query" in t_prop.plain

    t_exec = r_grouped.render_tool_executed("sqlite.query", True, {"stdout": "1"}, duration_ms=250.0)
    assert t_exec is not None
    assert "└──" in t_exec.plain
    assert "(250ms)" in t_exec.plain

    # Emoji mode
    r_emoji = TuiRenderer(display_mode="emoji")
    t_emoji = r_emoji.render_tool_proposed("shell.execute", {"command": "ls"})
    assert t_emoji is not None
    assert "PROPOSED" in t_emoji.plain

    # Minimal mode
    r_minimal = TuiRenderer(display_mode="minimal")
    t_min = r_minimal.render_tool_executed("shell.execute", True, "ok", duration_ms=1200)
    assert t_min is not None
    assert "(1.2s)" in t_min.plain

    # Hidden mode
    r_hidden = TuiRenderer(display_mode="hidden")
    assert r_hidden.render_tool_proposed("any", {}) is None
    assert r_hidden.render_tool_executed("any", True, {}) is None
    assert r_hidden.render_tool_blocked("any", "reason") is None


def test_tui_renderer_jev_assessment():
    r = TuiRenderer(display_mode="grouped")
    t = r.render_jev_assessment("medium", "approval_required", ["privilege_escalation"], latency_ms=85.0)
    assert t is not None
    assert "[MEDIUM]" in t.plain
    assert "APPROVAL_REQUIRED" in t.plain
    assert "(85ms)" in t.plain
    assert "privilege_escalation" in t.plain


def test_tui_renderer_tool_latency_tracking():
    r = TuiRenderer()
    r.record_tool_start("call_1", 100.0)
    dur = r.get_tool_duration_ms("call_1", 100.45)
    assert dur is not None
    assert abs(dur - 450.0) < 1.0

    # Second call should return None (already popped)
    assert r.get_tool_duration_ms("call_1", 101.0) is None


def test_tui_renderer_run_completed():
    r = TuiRenderer()
    card = r.render_run_completed(
        run_id="run_12345678",
        status="completed",
        allowed=3,
        blocked=1,
        jev_count=4,
        tool_calls=4,
        input_tokens=1500,
        output_tokens=320,
        duration_ms=2400.0,
    )
    plain = card.plain
    assert "RUN COMPLETE" in plain
    assert "run_12345678" in plain
    assert "COMPLETED" in plain
    assert "1.5k in" in plain
    assert "320 out" in plain
    assert "(2.4s)" in plain

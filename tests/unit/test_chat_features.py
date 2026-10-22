"""Unit tests for AURA Chat screen features and extensions."""
import pytest
from pathlib import Path
from aura.ui.screens.chat import ChatMessage, ChatView
from aura.config import AURAConfig, DisplayConfig


def test_chat_message_rendering():
    # User message
    msg_user = ChatMessage(role="user", content="Hello AURA", metadata={"attached_files": ["pyproject.toml"]})
    rendered = msg_user.render()
    assert "YOU" in rendered.plain
    assert "Hello AURA" in rendered.plain
    assert "[@pyproject.toml]" in rendered.plain

    # Agent message
    msg_agent = ChatMessage(role="agent", content="Ready to assist.")
    rendered = msg_agent.render()
    assert "AURA AGENT" in rendered.plain
    assert "Ready to assist." in rendered.plain

    # Tool proposed
    msg_prop = ChatMessage(role="tool_proposed", metadata={"tool": "filesystem.list", "args": {"path": "."}})
    rendered = msg_prop.render()
    assert "Listed directory" in rendered.plain or "filesystem.list" in rendered.plain

    # Action blocked
    msg_blk = ChatMessage(role="action_blocked", metadata={"tool": "shell.execute", "reason": "Destructive command"})
    rendered = msg_blk.render()
    assert "BLOCKED" in rendered.plain
    assert "Destructive command" in rendered.plain

    # Action executed
    msg_exec = ChatMessage(role="action_executed", metadata={"tool": "sqlite.query", "success": True, "output": {"stdout": "success"}})
    rendered = msg_exec.render()
    assert "✓" in rendered.plain

    # Shell shortcut
    msg_sh = ChatMessage(role="shell_shortcut", metadata={"command": "whoami", "stdout": "testuser"})
    rendered = msg_sh.render()
    assert "!whoami" in rendered.plain
    assert "testuser" in rendered.plain


def test_expand_file_refs(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("sample file content", encoding="utf-8")

    chat_view = ChatView()
    # Test valid file
    expanded, attached = chat_view._expand_file_refs(f"Please inspect @{test_file}")
    assert str(test_file) in attached
    assert "<file path=" in expanded
    assert "sample file content" in expanded

    # Test non-existent file
    expanded2, attached2 = chat_view._expand_file_refs("Check @non_existent_file.xyz")
    assert len(attached2) == 0
    assert expanded2 == "Check @non_existent_file.xyz"


def test_display_config_fields(monkeypatch):
    monkeypatch.setenv("AURA_TOOL_DISPLAY", "emoji")
    monkeypatch.setenv("AURA_LOADER_STYLE", "spinner")
    monkeypatch.setenv("AURA_INPUT_STYLE", "block")

    cfg = AURAConfig.from_env()
    assert cfg.display.tool_display == "emoji"
    assert cfg.display.loader_style == "spinner"
    assert cfg.display.input_style == "block"

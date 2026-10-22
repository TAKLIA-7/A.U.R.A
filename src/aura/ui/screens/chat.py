"""AURA Chat Screen — primary prompt and agent execution view.

Enhanced with patterns from create-agent-tui:
- Configurable input styles (bordered, block, plain) with terminal-width resizing
- @file context reference expansion (@path/to/file)
- !cmd inline shell execution shortcut
- Animated loader widget with shimmer gradient / spinner states
- TuiRenderer tree-branch formatting, timing latency metrics, and token usage summary
- Extended slash commands (/session, /compact, /export)
"""
from __future__ import annotations
import asyncio
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import (
    Button, Input, Label, RichLog, Static,
)
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.events import Resize
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

from aura.ui.ascii_art import make_gradient_logo, make_tagline
from aura.ui.renderer import TuiRenderer, summarize_args, format_tokens, format_duration
from aura.ui.widgets.loader import AURALoader
from aura.config import get_config

if TYPE_CHECKING:
    from aura.app import AURAApp


SLASH_COMMANDS = [
    "/help", "/status", "/new", "/reset", "/runs", "/logs", "/monitor",
    "/policies", "/settings", "/clear", "/session", "/compact", "/export", "/quit",
]


class WelcomePanel(Static):
    """The welcome panel shown before any conversation."""

    DEFAULT_CSS = """
    WelcomePanel {
        align: center middle;
        padding: 1 2;
        width: 100%;
    }
    """

    def render(self) -> Any:
        cfg = get_config()
        jev_mode = "MOCK" if cfg.jev.mock_mode else "LIVE"
        jev_color = "yellow" if cfg.jev.mock_mode else "green"
        model = cfg.llm.model

        t = Text()
        logo = make_gradient_logo()
        t.append_text(logo)
        tagline = make_tagline()
        t.append_text(tagline)
        t.append(f"\n  Model: [bold cyan]{model}[/bold cyan]   JEV: [{jev_color}]{jev_mode}[/{jev_color}]\n")
        return t


class ChatMessage(Static):
    """A single rendered message in the conversation.

    Delegates tool, JEV, and run outputs to TuiRenderer for tree-branch, emoji,
    or minimal styling with elapsed time and clean formatting.
    """

    def __init__(self, role: str, content: str = "", metadata: Optional[Dict] = None) -> None:
        super().__init__()
        self.role = role
        self.content = content
        self.msg_metadata = metadata or {}

    def render(self) -> Any:
        cfg = get_config()
        renderer = TuiRenderer(display_mode=cfg.display.tool_display)

        if self.role == "user":
            attached = self.msg_metadata.get("attached_files")
            t = Text()
            t.append("  ▶ YOU", style="bold #AACCFF")
            if attached:
                t.append(f"  [@{', @'.join(attached)}]", style="dim #00FFFF")
            t.append("\n")
            t.append(f"  {self.content}\n", style="#DDEEFF")
            return t

        elif self.role == "agent":
            t = Text()
            t.append("  ◈ AURA AGENT\n", style="bold #00FFFF")
            t.append(f"  {self.content}\n", style="#DDEEFF")
            return t

        elif self.role == "tool_proposed":
            tool = self.msg_metadata.get("tool", "?")
            args = self.msg_metadata.get("args", {})
            req_id = self.msg_metadata.get("request_id", "")
            rendered = renderer.render_tool_proposed(tool, args, req_id)
            return rendered if rendered is not None else Text("")

        elif self.role == "action_executed":
            tool = self.msg_metadata.get("tool", "?")
            success = self.msg_metadata.get("success", True)
            output = self.msg_metadata.get("output") or {}
            dur_ms = self.msg_metadata.get("duration_ms")
            err = self.msg_metadata.get("error")
            rendered = renderer.render_tool_executed(tool, success, output, dur_ms, err)
            return rendered if rendered is not None else Text("")

        elif self.role == "action_blocked":
            tool = self.msg_metadata.get("tool", "?")
            reason = self.msg_metadata.get("reason", "")
            pol_id = self.msg_metadata.get("policy_rule_id", "")
            rendered = renderer.render_tool_blocked(tool, reason, pol_id)
            return rendered if rendered is not None else Text("")

        elif self.role == "jev_assessed":
            risk = self.msg_metadata.get("risk_level", "unknown")
            rec = self.msg_metadata.get("recommended_action", "?")
            factors = self.msg_metadata.get("factors") or self.msg_metadata.get("risk_factors")
            lat_ms = self.msg_metadata.get("latency_ms")
            rendered = renderer.render_jev_assessment(risk, rec, factors, lat_ms)
            return rendered if rendered is not None else Text("")

        elif self.role == "approval_requested":
            tool = self.msg_metadata.get("tool", "?")
            t = Text()
            t.append("  ⚠ APPROVAL REQUIRED: ", style="bold #FFAA00")
            t.append(f"{tool}\n", style="bold #FFAA00")
            t.append("    [Interactive authorization pop-up displayed — Press 'A' to Approve or 'D' to Deny]\n", style="bold #FFEE88")
            return t

        elif self.role == "shell_shortcut":
            cmd = self.msg_metadata.get("command", "")
            out = self.msg_metadata.get("stdout", "")
            err = self.msg_metadata.get("stderr", "")
            t = Text()
            t.append(f"  $ !{cmd}\n", style="bold #00FFFF")
            if out:
                t.append(f"  {out.strip()}\n", style="#CCDDEE")
            if err:
                t.append(f"  [stderr]: {err.strip()}\n", style="bold #FF4444")
            return t

        elif self.role == "run_completed":
            run_id = self.msg_metadata.get("run_id", "?")
            status = self.msg_metadata.get("status", "?")
            allowed = self.msg_metadata.get("allowed", 0)
            blocked = self.msg_metadata.get("blocked", 0)
            jev_count = self.msg_metadata.get("jev_assessments", 0)
            tool_calls = self.msg_metadata.get("tool_calls", 0)
            in_tok = self.msg_metadata.get("input_tokens")
            out_tok = self.msg_metadata.get("output_tokens")
            dur_ms = self.msg_metadata.get("duration_ms")
            return renderer.render_run_completed(
                run_id=run_id,
                status=status,
                allowed=allowed,
                blocked=blocked,
                jev_count=jev_count,
                tool_calls=tool_calls,
                input_tokens=in_tok,
                output_tokens=out_tok,
                duration_ms=dur_ms,
            )

        elif self.role == "run_failed":
            error = self.content
            t = Text()
            t.append("\n  ✗ RUN FAILED\n", style="bold #FF4444")
            t.append(f"  {error}\n\n", style="#AA3333")
            return t

        elif self.role == "system":
            t = Text()
            t.append(f"  ℹ {self.content}\n", style="dim #8888BB")
            return t

        else:
            return Text(f"  {self.content}\n")


class ChatView(Container):
    """Page 1 — Chat and agent execution."""

    DEFAULT_CSS = """
    ChatView {
        layout: vertical;
        background: #0a0a12;
        height: 1fr;
    }

    #chat-area {
        width: 100%;
        height: 1fr;
        border: solid #1a1a30;
        background: #0d0d1e;
        overflow-y: auto;
    }
    #input-container {
        height: auto;
        min-height: 4;
        background: #0d0d20;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    #input-container.bordered {
        background: transparent;
        border: none;
    }
    #input-container.block {
        background: #0d0d22;
        border: tall #222244;
    }
    #input-container.block:focus-within {
        border: tall #00FFFF;
    }
    #input-container.plain {
        background: transparent;
        border: none;
    }
    #prompt-input {
        width: 100%;
        border: none;
        background: transparent;
        color: #DDEEFF;
        padding: 0 1;
    }
    #prompt-input:focus {
        border: none;
    }
    #input-top-border {
        height: 1;
        color: #333355;
    }
    #input-bottom-border {
        height: 1;
        color: #333355;
    }
    #context-bar {
        height: 1;
        background: #080812;
        padding: 0 1;
    }
    #input-hint {
        height: 1;
        color: #444466;
        padding: 0 1;
    }
    #welcome-area {
        align: center middle;
        padding: 2 4;
        height: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "cancel_run", "Cancel"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._messages: List[Dict] = []
        self._running = False
        self._run_task: Optional[asyncio.Task] = None
        self._conversation_history: List[Dict] = []
        self._pending_approval: Optional[Dict] = None
        self._show_welcome = True
        self._current_run_id: Optional[str] = None
        self._status_text = "IDLE"
        self._tool_starts: Dict[str, float] = {}
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def compose(self) -> ComposeResult:
        cfg = get_config()
        jev_mode = "MOCK MODE" if cfg.jev.mock_mode else "LIVE"
        cwd = os.getcwd()

        with Container(id="chat-outer"):
            with ScrollableContainer(id="chat-area"):
                yield Static(id="welcome-area")

            # Animated loader widget
            yield AURALoader(
                text="Agent thinking...",
                style=cfg.display.loader_style,
                id="agent-loader",
            )

            # Input area with dynamic borders
            with Container(id="input-container", classes=cfg.display.input_style):
                yield Static("", id="input-top-border")
                yield Input(placeholder="  ▶  Describe a task for the agent... (supports @file and !command)", id="prompt-input")
                yield Static("", id="input-bottom-border")

            yield Static(id="input-hint")

            with Horizontal(id="context-bar"):
                yield Label(f" {cwd[:35]}  ", id="cwd-label")
                yield Label(f"MODEL: {cfg.llm.model.split('/')[-1]}  ", id="model-label")
                yield Label(f"JEV: {jev_mode}  ", id="jev-label", classes="jev-badge" if not cfg.jev.mock_mode else "warning")
                yield Label(f"STYLE: {cfg.display.input_style}  ", id="style-label", classes="muted")
                yield Label(f"↵ Submit  ESC Cancel  /help", id="shortcuts-label", classes="muted")

    def on_mount(self) -> None:
        self._render_welcome()
        self._update_hint("↵ Submit   @file Attach file   !cmd Run shell   /help Commands   ESC Cancel")
        self._draw_input_borders()

    def on_resize(self, event: Resize) -> None:
        self._draw_input_borders(width=event.size.width)

    def _draw_input_borders(self, width: Optional[int] = None) -> None:
        """Render adaptive horizontal border lines based on terminal width and input style."""
        cfg = get_config()
        style = cfg.display.input_style
        try:
            top_widget = self.query_one("#input-top-border", Static)
            bot_widget = self.query_one("#input-bottom-border", Static)
            container = self.query_one("#input-container", Container)

            # Determine available width
            cols = width or self.size.width or 80
            w = max(20, min(cols - 4, 120))

            if style == "bordered":
                container.remove_class("block")
                container.remove_class("plain")
                container.add_class("bordered")
                top_widget.update(Text("─" * w, style="#333355"))
                bot_widget.update(Text("─" * w, style="#333355"))
            elif style == "block":
                container.remove_class("bordered")
                container.remove_class("plain")
                container.add_class("block")
                inner_w = max(4, w - 16)
                top_widget.update(Text(f"  ╭─ ASK AURA {'─' * inner_w}╮", style="bold #222244"))
                bot_widget.update(Text(f"  ╰{'─' * max(4, w - 4)}╯", style="bold #222244"))
            else:  # plain
                container.remove_class("bordered")
                container.remove_class("block")
                container.add_class("plain")
                top_widget.update("")
                bot_widget.update("")
        except Exception:
            pass

    def _render_welcome(self) -> None:
        area = self.query_one("#welcome-area", Static)
        cfg = get_config()
        jev_mode = "⚠ MOCK MODE" if cfg.jev.mock_mode else "● LIVE"
        jev_color = "yellow" if cfg.jev.mock_mode else "green"
        t = Text()

        # Gradient Logo
        logo_lines = [
            "  ██████╗   ██╗   ██╗  ██████╗    ██████╗  ",
            "  ██╔══██╗  ██║   ██║  ██╔══██╗  ██╔══██╗  ",
            "  ███████║  ██║   ██║  ██████╔╝  ███████║  ",
            "  ██╔══██║  ██║   ██║  ██╔══██╗  ██╔══██║  ",
            "  ██║  ██║  ╚██████╔╝  ██║  ██║  ██║  ██║  ",
            "  ╚═╝  ╚═╝   ╚═════╝   ╚═╝  ╚═╝  ╚═╝  ╚═╝  ",
        ]
        gradient = ["#00FFFF", "#22DDFF", "#4488FF", "#6655FF", "#8822FF", "#CC00CC"]
        for i, line in enumerate(logo_lines):
            t.append(line + "\n", style=f"bold {gradient[i]}")
        t.append("\n")
        t.append("  A ", style="bold #00FFFF")
        t.append("U ", style="bold #4488FF")
        t.append("R ", style="bold #8822FF")
        t.append("A", style="bold #FF00CC")
        t.append("  //  AGENT CONTROL PLANE\n", style="bold white")
        t.append("  Contextual decisions  •  Controlled execution  •  Complete observability\n", style="dim cyan")
        t.append(f"  v0.1.0   Model: {cfg.llm.model}   JEV: ", style="dim white")
        t.append(f"{jev_mode}\n", style=f"bold {jev_color}")
        t.append("\n")
        t.append("  GETTING STARTED\n", style="bold cyan")
        t.append("\n")
        t.append("  01  ", style="dim cyan")
        t.append("Ask the agent a question or describe a task.\n", style="white")
        t.append("  02  ", style="dim cyan")
        t.append("AURA intercepts tool calls and evaluates risk with JEV.\n", style="white")
        t.append("  03  ", style="dim cyan")
        t.append("Review approvals, execution decisions, and responses.\n", style="white")
        t.append("  04  ", style="dim cyan")
        t.append("Inspect structured logs and live system metrics.\n", style="white")
        t.append("\n")
        t.append("  /help ", style="bold cyan")
        t.append("View commands   ", style="dim")
        t.append("@file ", style="bold cyan")
        t.append("Attach context   ", style="dim")
        t.append("!cmd ", style="bold cyan")
        t.append("Run shell   ", style="dim")
        t.append("/monitor ", style="bold cyan")
        t.append("Live metrics\n", style="dim")
        area.update(t)

    def _update_hint(self, text: str) -> None:
        try:
            hint = self.query_one("#input-hint", Static)
            hint.update(Text(f"  {text}", style="dim #444466"))
        except Exception:
            pass

    def _add_chat_message(self, role: str, content: str = "", metadata: Optional[Dict] = None) -> None:
        msg = ChatMessage(role=role, content=content, metadata=metadata)
        chat_area = self.query_one("#chat-area", ScrollableContainer)
        if self._show_welcome and role not in ("system",):
            welcome = self.query_one("#welcome-area", Static)
            welcome.update("")
            self._show_welcome = False
        chat_area.mount(msg)
        chat_area.scroll_end(animate=False)

    def _expand_file_refs(self, text: str) -> Tuple[str, List[str]]:
        """Expand @file references by attaching file contents into the prompt."""
        pattern = r"@([a-zA-Z0-9_\-\./\\:]+)"
        attached: List[str] = []
        file_blocks: List[str] = []

        for match in re.finditer(pattern, text):
            file_ref = match.group(1)
            path = Path(file_ref)
            if path.exists() and path.is_file():
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    if len(content) > 12000:
                        content = content[:12000] + "\n... [truncated]"
                    file_blocks.append(f"<file path=\"{file_ref}\">\n{content}\n</file>")
                    attached.append(file_ref)
                except Exception:
                    pass

        if file_blocks:
            expanded = "\n\n".join(file_blocks) + "\n\n" + text
            return expanded, attached
        return text, []

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        raw_prompt = event.value.strip()
        if not raw_prompt:
            return
        input_widget = self.query_one("#prompt-input", Input)
        input_widget.value = ""

        # 1. Handle Slash Commands
        if raw_prompt.startswith("/"):
            await self._handle_command(raw_prompt)
            return

        # 2. Handle !shell shortcut (run command directly without agent invocation)
        if raw_prompt.startswith("!"):
            cmd = raw_prompt[1:].strip()
            if cmd:
                await self._execute_shell_shortcut(cmd)
            return

        # 3. Check active run state
        if self._running:
            if self._run_task is None or self._run_task.done():
                self._running = False
                self._run_task = None
            else:
                self.notify("Agent is running. Press ESC to cancel or type /reset to force stop.", severity="warning")
                return

        # 4. Expand @file references and run agent
        expanded_prompt, attached_files = self._expand_file_refs(raw_prompt)
        await self._start_agent_run(raw_prompt, expanded_prompt, attached_files)

    async def _execute_shell_shortcut(self, cmd: str) -> None:
        """Run an immediate shell command with output injected into context."""
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            stdout = res.stdout[:2000] if res.stdout else ""
            stderr = res.stderr[:1000] if res.stderr else ""
            self._add_chat_message("shell_shortcut", "", {
                "command": cmd,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": res.returncode,
            })
            # Inject into conversation history
            self._conversation_history.append({
                "role": "user",
                "content": f"Shell output of `{cmd}`:\n```\n{stdout or stderr}\n```",
            })
        except subprocess.TimeoutExpired:
            self._add_chat_message("system", f"Shell command `{cmd}` timed out after 15 seconds.")
        except Exception as e:
            self._add_chat_message("system", f"Failed to run shell shortcut: {e}")

    async def _handle_command(self, cmd_line: str) -> None:
        parts = cmd_line.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        app = self.app

        if cmd == "/help":
            help_text = (
                "AURA Interactive Commands:\n"
                "  /help       Show this help summary\n"
                "  /status     Inspect Agent, JEV connection, and active run status\n"
                "  /session    Inspect current session info and token efficiency\n"
                "  /compact    Compact conversation history to conserve token budget\n"
                "  /export     Export active conversation trace to disk\n"
                "  /new        Reset and start a fresh conversation\n"
                "  /reset      Force cancel running agent and reset state to IDLE\n"
                "  /runs       Jump to [F2] Runs page\n"
                "  /logs       Jump to [F3] Logs page\n"
                "  /monitor    Jump to [F4] Monitor page\n"
                "  /policies   Jump to [F5] Policies page\n"
                "  /settings   Jump to [F6] Settings page\n"
                "  /clear      Clear conversation screen\n"
                "  /quit       Exit AURA\n\n"
                "Keyboard & Input Shortcuts:\n"
                "  @path       Type @filename to attach file content to prompt\n"
                "  !cmd        Type !command to run quick shell shortcut\n"
                "  ESC         Cancel running agent or dismiss approval modal"
            )
            self._add_chat_message("system", help_text)

        elif cmd == "/status":
            from aura.observability import get_metrics
            m = get_metrics()
            status_text = (
                f"Agent: {'● CONNECTED' if m.agent_connected else '○ DISCONNECTED'}\n"
                f"JEV:   {'● CONNECTED' if m.jev_connected else '○ DISCONNECTED'}  "
                f"(mode: {getattr(self.app.orchestrator, 'jev_mode', 'unknown') if hasattr(self.app, 'orchestrator') else 'unknown'})\n"
                f"Runs:  Active={m.active_runs}  Completed={m.completed_runs}  Failed={m.failed_runs}\n"
                f"Tokens: {format_tokens(m.input_tokens)} in  •  {format_tokens(m.output_tokens)} out"
            )
            self._add_chat_message("system", status_text)

        elif cmd == "/session":
            orch = getattr(self.app, "orchestrator", None)
            sess_id = orch.session_id if orch else "unknown"
            cur_run = orch.current_run.run_id if orch and orch.current_run else "─"
            cfg = get_config()
            hist_len = len(self._conversation_history)
            sess_text = (
                f"Session ID:   {sess_id}\n"
                f"Active Run:   {cur_run}\n"
                f"History:      {hist_len} message(s) in context\n"
                f"Model:        {cfg.llm.provider} / {cfg.llm.model}\n"
                f"JEV Engine:   {cfg.jev.provider.upper()} ({'MOCK' if cfg.jev.mock_mode else 'LIVE'})\n"
                f"Display:      tool={cfg.display.tool_display}  loader={cfg.display.loader_style}  input={cfg.display.input_style}"
            )
            self._add_chat_message("system", sess_text)

        elif cmd == "/compact":
            if len(self._conversation_history) <= 2:
                self.notify("Conversation history is already minimal.", severity="information")
                return
            kept = self._conversation_history[-2:]
            summarized_count = len(self._conversation_history) - 2
            self._conversation_history = [
                {"role": "system", "content": f"[AURA: Compacted {summarized_count} earlier turns to preserve context budget]"},
                *kept,
            ]
            self.notify(f"Compacted {summarized_count} messages from history.", severity="information")
            self._add_chat_message("system", f"Context compacted: {summarized_count} older turns summarized.")

        elif cmd == "/export":
            try:
                cfg = get_config()
                export_dir = cfg.runtime.data_dir / "runs"
                export_dir.mkdir(parents=True, exist_ok=True)
                run_id = self._current_run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
                export_file = export_dir / f"export_{run_id}.md"

                lines = [
                    f"# AURA Conversation Export",
                    f"- **Exported:** {datetime.now(timezone.utc).isoformat()}",
                    f"- **Run ID:** {run_id}",
                    f"- **Model:** {cfg.llm.model}",
                    "",
                    "## Conversation Trace",
                    "",
                ]
                for item in self._conversation_history:
                    role = item.get("role", "user").upper()
                    content = item.get("content", "")
                    lines.append(f"### {role}\n\n{content}\n")

                export_file.write_text("\n".join(lines), encoding="utf-8")
                self.notify(f"Exported to {export_file.name}", severity="information")
                self._add_chat_message("system", f"Exported conversation trace to:\n{export_file.resolve()}")
            except Exception as e:
                self._add_chat_message("system", f"Export failed: {e}")

        elif cmd == "/reset":
            self.action_cancel_run()
            self._running = False
            self._run_task = None
            self.notify("Agent state reset to IDLE.", severity="information")

        elif cmd == "/new":
            self._conversation_history = []
            self._messages = []
            self._show_welcome = True
            chat_area = self.query_one("#chat-area", ScrollableContainer)
            await chat_area.remove_children()
            await chat_area.mount(Static(id="welcome-area"))
            self._render_welcome()
            self.notify("New conversation started.", severity="information")

        elif cmd == "/clear":
            self.action_clear_chat()

        elif cmd == "/runs":
            app.switch_page("runs")
        elif cmd == "/logs":
            app.switch_page("logs")
        elif cmd == "/monitor":
            app.switch_page("monitor")
        elif cmd == "/policies":
            app.switch_page("policies")
        elif cmd == "/settings":
            app.switch_page("settings")
        elif cmd == "/quit":
            app.exit()
        else:
            self._add_chat_message("system", f"Unknown command: {cmd}. Type /help for available commands.")

    async def _start_agent_run(self, raw_prompt: str, expanded_prompt: str, attached_files: List[str]) -> None:
        app = self.app
        if not hasattr(app, "orchestrator") or app.orchestrator is None:
            self._add_chat_message("system", "❌ Agent not initialized. Check Settings for API configuration.")
            return

        self._running = True
        self._update_hint("● Agent running...   ESC to interrupt")

        # Display user message with attached file chips
        self._add_chat_message("user", raw_prompt, {"attached_files": attached_files})
        self._conversation_history.append({"role": "user", "content": expanded_prompt})

        # Start animated loader
        loader = self.query_one("#agent-loader", AURALoader)
        loader.start("Agent thinking...")

        async def run_agent() -> None:
            try:
                gen = app.orchestrator.run(
                    prompt=expanded_prompt,
                    conversation_history=self._conversation_history[:-1],
                )
                async for msg in gen:
                    if msg.kind == "run_started":
                        self._current_run_id = msg.content.get("run_id", "")
                        loader.set_text("Agent planning initial action...")

                    elif msg.kind == "agent_text":
                        self._add_chat_message("agent", msg.content)
                        self._conversation_history.append({"role": "assistant", "content": msg.content})

                    elif msg.kind == "tool_proposed":
                        tool = msg.content.get("tool", "")
                        req_id = msg.content.get("request_id", "")
                        self._tool_starts[req_id] = time.time()
                        loader.set_text(f"Intercepting {tool}...")
                        self._add_chat_message("tool_proposed", "", msg.content)

                    elif msg.kind == "jev_assessed":
                        loader.set_text("Evaluating security policies with JEV...")
                        self._add_chat_message("jev_assessed", "", msg.content)

                    elif msg.kind == "action_blocked":
                        loader.set_text("Action blocked by policy...")
                        self._add_chat_message("action_blocked", "", msg.content)

                    elif msg.kind == "approval_requested":
                        loader.set_text("Awaiting operator authorization...")
                        self._add_chat_message("approval_requested", "", msg.content)

                    elif msg.kind == "action_executed":
                        tool = msg.content.get("tool", "")
                        req_id = msg.content.get("request_id", "")
                        start_time = self._tool_starts.pop(req_id, None)
                        dur_ms = (time.time() - start_time) * 1000 if start_time else None
                        content_data = dict(msg.content)
                        if dur_ms is not None:
                            content_data["duration_ms"] = dur_ms
                        loader.set_text(f"Executed {tool}...")
                        self._add_chat_message("action_executed", "", content_data)

                    elif msg.kind == "token_usage":
                        self._total_input_tokens += msg.content.get("input_tokens") or 0
                        self._total_output_tokens += msg.content.get("output_tokens") or 0

                    elif msg.kind == "run_completed":
                        loader.stop()
                        completed_data = dict(msg.content)
                        if not completed_data.get("input_tokens") and self._total_input_tokens:
                            completed_data["input_tokens"] = self._total_input_tokens
                            completed_data["output_tokens"] = self._total_output_tokens
                        self._add_chat_message("run_completed", "", completed_data)

                    elif msg.kind == "run_failed":
                        loader.stop()
                        self._add_chat_message("run_failed", msg.content.get("error", "Unknown error"))

                    elif msg.kind == "warning":
                        self._add_chat_message("system", f"⚠ {msg.content}")

            except Exception as e:
                loader.stop()
                self._add_chat_message("run_failed", str(e))
            finally:
                loader.stop()
                self._running = False
                self._run_task = None
                self._update_hint("↵ Submit   @file Attach file   !cmd Run shell   ESC Interrupt")
                try:
                    self.query_one("#prompt-input", Input).focus()
                except Exception:
                    pass

        self._run_task = asyncio.create_task(run_agent())

    def action_clear_chat(self) -> None:
        self._show_welcome = True
        chat_area = self.query_one("#chat-area", ScrollableContainer)
        for child in list(chat_area.children):
            child.remove()
        chat_area.mount(Static(id="welcome-area"))
        self._render_welcome()

    def action_cancel_run(self) -> None:
        if hasattr(self.app, "orchestrator") and self.app.orchestrator:
            try:
                self.app.orchestrator.cancel()
            except Exception:
                pass
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
        loader = self.query_one("#agent-loader", AURALoader)
        loader.stop()
        if self._running:
            self._add_chat_message("system", "⚠ Run cancelled by user.")
        self._running = False
        self._run_task = None
        self._update_hint("↵ Submit   @file Attach file   !cmd Run shell   ESC Interrupt")

    def on_screen_resume(self) -> None:
        try:
            self.query_one("#prompt-input", Input).focus()
        except Exception:
            pass


# Alias for backward compatibility
ChatScreen = ChatView

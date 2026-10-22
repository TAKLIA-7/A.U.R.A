"""AURA Policies Screen."""
from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label, Static, RichLog
from textual.containers import Container, Horizontal, Vertical
from rich.text import Text

from aura.policies import ALLOWED_TOOLS, UNCONDITIONAL_DENY, ALWAYS_APPROVAL, ALWAYS_ALLOW
from aura.observability import get_run_repo


class PoliciesView(Container):
    DEFAULT_CSS = """
    PoliciesView { background: #0a0a12; layout: vertical; height: 1fr; }
    #pol-header { height: 3; background: #0d0d1f; padding: 0 2; border-bottom: solid #1a1a30; }
    #pol-layout { layout: horizontal; height: 1fr; }
    #pol-left { width: 1fr; padding: 1; overflow-y: auto; }
    #pol-right { width: 1fr; padding: 1; }
    .pol-panel { border: solid #1a1a30; background: #0d0d1e; padding: 1 2; margin: 0 0 1 0; }
    #approvals-panel { height: 1fr; border: solid #1a1a30; background: #0a0a18; }
    """


    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pending_approvals: List[Dict] = []

    def compose(self) -> ComposeResult:
        with Container(id="pol-header"):
            yield Static(Text.from_markup("[bold cyan]◈ POLICIES[/bold cyan]  [dim]Configured decision rules and human approvals[/dim]"))
        with Horizontal(id="pol-layout"):
            with Vertical(id="pol-left"):
                with Container(id="tool-rules", classes="pol-panel"):
                    yield Static(id="tool-rules-content")
                with Container(id="risk-rules", classes="pol-panel"):
                    yield Static(id="risk-rules-content")
            with Vertical(id="pol-right"):
                with Container(id="approvals-panel", classes="pol-panel"):
                    yield Static(Text.from_markup("[bold cyan]PENDING APPROVALS[/bold cyan]"), id="approvals-title")
                    yield DataTable(id="approvals-table", cursor_type="row")
                with Horizontal(id="approval-actions"):
                    yield Button("✓ Approve", id="btn-approve", variant="success", classes="success")
                    yield Button("✗ Deny", id="btn-deny", variant="error", classes="danger")
                    yield Button("Refresh", id="btn-refresh-pol")

    def on_mount(self) -> None:
        self._render_rules()
        self._setup_approvals_table()
        asyncio.create_task(self._load_approvals())

    def _render_rules(self) -> None:
        # Tool rules
        t = Text()
        t.append("TOOL POLICY\n", style="bold cyan")
        t.append("\n  Allowlist:\n", style="dim")
        for tool in sorted(ALLOWED_TOOLS):
            t.append(f"    ✓ {tool}\n", style="green")
        t.append("\n  Unconditional Deny:\n", style="dim")
        for tool in sorted(UNCONDITIONAL_DENY):
            t.append(f"    ✗ {tool}\n", style="red")
        t.append("\n  Always Approval Required:\n", style="dim")
        for tool in sorted(ALWAYS_APPROVAL):
            t.append(f"    ⚠ {tool}\n", style="yellow")
        t.append("\n  Fast Allow (skip JEV):\n", style="dim")
        for tool in sorted(ALWAYS_ALLOW):
            t.append(f"    ⚡ {tool}\n", style="cyan")
        self.query_one("#tool-rules-content", Static).update(t)

        # Risk rules
        t2 = Text()
        t2.append("RISK → DECISION MAPPING\n", style="bold cyan")
        t2.append("\n")
        risk_map = [
            ("none",     "ALLOW",   "green"),
            ("low",      "ALLOW",   "green"),
            ("medium",   "ALLOW",   "green"),
            ("high",     "BLOCK",   "red"),
            ("critical", "BLOCK",   "bright_red"),
        ]
        for risk, decision, color in risk_map:
            t2.append(f"  {risk:12s}", style="dim")
            t2.append(f"→  {decision}\n", style=f"bold {color}")
        t2.append("\n")
        t2.append("  Policy evaluation order:\n", style="dim cyan")
        steps = [
            "1. Schema validation",
            "2. Tool allowlist check",
            "3. Unconditional deny",
            "4. Path traversal check",
            "5. JEV risk assessment",
            "6. Risk-based policy",
            "7. Human approval (if required)",
        ]
        for step in steps:
            t2.append(f"  {step}\n", style="#888899")
        self.query_one("#risk-rules-content", Static).update(t2)

    def _setup_approvals_table(self) -> None:
        table = self.query_one("#approvals-table", DataTable)
        table.add_columns("Approval ID", "Tool", "Reason", "Risk")

    async def _load_approvals(self) -> None:
        app = self.app
        if not hasattr(app, "orchestrator") or not app.orchestrator:
            return
        pending = await app.orchestrator.approval_manager.get_pending()
        self._pending_approvals = pending
        table = self.query_one("#approvals-table", DataTable)
        table.clear()
        for ap in pending:
            req = ap.get("request", {})
            tool = req.get("tool", "?")
            reason = ap.get("decision", {}).get("reason", "")[:40]
            assess = ap.get("assessment") or {}
            risk = assess.get("risk_level", "unknown") if assess else "unknown"
            risk_color = {"high": "red", "medium": "yellow", "low": "green"}.get(risk, "white")
            table.add_row(
                Text(ap.get("approval_id", "")[:20], style="dim cyan"),
                Text(tool, style="bold #00FFFF"),
                Text(reason, style="#888899"),
                Text(risk.upper(), style=f"bold {risk_color}"),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("btn-approve", "btn-deny"):
            asyncio.create_task(self._resolve_selected(event.button.id == "btn-approve"))
        elif event.button.id == "btn-refresh-pol":
            asyncio.create_task(self._load_approvals())

    async def _resolve_selected(self, approved: bool) -> None:
        table = self.query_one("#approvals-table", DataTable)
        if not self._pending_approvals:
            self.notify("No pending approvals.", severity="information")
            return
        row_idx = table.cursor_row
        if row_idx is None or row_idx >= len(self._pending_approvals):
            self.notify("Select an approval row first.", severity="warning")
            return
        ap = self._pending_approvals[row_idx]
        approval_id = ap.get("approval_id", "")
        if not approval_id:
            return
        app = self.app
        if hasattr(app, "orchestrator") and app.orchestrator:
            await app.orchestrator.approval_manager.resolve(approval_id, approved)
            self.notify(f"Approval {'granted' if approved else 'denied'}: {approval_id}", severity="information" if approved else "warning")
            await self._load_approvals()

    def on_screen_resume(self) -> None:
        asyncio.create_task(self._load_approvals())


# Alias for backward compatibility
PoliciesScreen = PoliciesView

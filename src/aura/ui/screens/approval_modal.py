"""AURA Approval Modal Screen — Interactive pop-up for operator authorization."""
from __future__ import annotations
import asyncio
import json
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Label
from textual.containers import Container, Horizontal, Vertical
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel


class ApprovalModalScreen(ModalScreen[bool]):
    """Modal screen that pops up whenever an intercepted agent action requires human approval."""

    DEFAULT_CSS = """
    ApprovalModalScreen {
        align: center middle;
        background: rgba(10, 10, 22, 0.88);
    }

    #modal-dialog {
        width: 82;
        height: auto;
        max-height: 85%;
        border: thick #FFAA00;
        background: #0d0d22;
        padding: 1 2;
    }

    #modal-title {
        text-align: center;
        color: #FFAA00;
        text-style: bold;
        margin-bottom: 1;
    }

    #modal-info {
        height: auto;
        margin-bottom: 1;
    }

    #modal-args-panel {
        background: #060614;
        border: solid #222244;
        padding: 1 1;
        margin: 1 0;
        max-height: 12;
        overflow-y: auto;
    }

    #modal-actions {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    #btn-modal-approve {
        margin-right: 3;
        min-width: 20;
        background: #00AA66;
        color: #FFFFFF;
        text-style: bold;
    }
    #btn-modal-approve:hover {
        background: #00DD88;
    }

    #btn-modal-deny {
        min-width: 20;
        background: #CC2222;
        color: #FFFFFF;
        text-style: bold;
    }
    #btn-modal-deny:hover {
        background: #FF4444;
    }
    """

    BINDINGS = [
        Binding("a", "approve", "Approve", show=True),
        Binding("d", "deny", "Deny", show=True),
        Binding("escape", "deny", "Cancel", show=True),
    ]

    def __init__(
        self,
        approval_id: str,
        tool: str,
        args: Dict[str, Any],
        reason: str,
        assessment: Optional[Any] = None,
        approval_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.approval_id = approval_id
        self.tool = tool
        self.args = args
        self.reason = reason
        self.assessment = assessment
        self.approval_manager = approval_manager
        self._resolved = False

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static("⚠ HUMAN APPROVAL REQUIRED — ACTION INTERCEPTED", id="modal-title")
            yield Static(self._render_details(), id="modal-info")
            with Container(id="modal-args-panel"):
                yield Static(self._render_payload(), id="modal-payload")
            with Horizontal(id="modal-actions"):
                yield Button("✓ Approve (A)", id="btn-modal-approve", variant="success")
                yield Button("✗ Deny (D)", id="btn-modal-deny", variant="error")

    def _render_details(self) -> Text:
        t = Text()
        t.append("The AI Agent requested execution of an action that requires operator sign-off.\n\n", style="dim")

        t.append("  Tool:       ", style="dim")
        t.append(f"{self.tool}\n", style="bold #00FFFF")

        t.append("  Request ID: ", style="dim")
        t.append(f"{self.approval_id}\n", style="#AACCFF")

        # JEV Risk evaluation
        risk_level = "medium"
        factors = []
        if self.assessment:
            if hasattr(self.assessment, "risk_level"):
                risk_level = str(getattr(self.assessment.risk_level, "value", self.assessment.risk_level))
            elif isinstance(self.assessment, dict):
                risk_level = self.assessment.get("risk_level", "medium")
            if hasattr(self.assessment, "risk_factors"):
                factors = self.assessment.risk_factors or []
            elif isinstance(self.assessment, dict):
                factors = self.assessment.get("risk_factors", [])

        risk_color = {"high": "#FF4444", "critical": "#FF0000", "medium": "#FFAA00", "low": "#00CC88"}.get(risk_level.lower(), "#FFAA00")
        t.append("  JEV Risk:   ", style="dim")
        t.append(f"[{risk_level.upper()}]\n", style=f"bold {risk_color}")

        if factors:
            t.append("  Factors:    ", style="dim")
            t.append(f"{', '.join(factors)}\n", style="#FFAA55")

        t.append("  Reason:     ", style="dim")
        t.append(f"{self.reason}\n", style="#EEDD88")
        return t

    def _render_payload(self) -> Text:
        t = Text()
        if "query" in self.args:
            t.append("SQL STATEMENT TO EXECUTE:\n", style="bold cyan")
            t.append(f"{self.args['query']}\n", style="bold white")
        elif "command" in self.args:
            t.append("SHELL COMMAND TO EXECUTE:\n", style="bold cyan")
            t.append(f"{self.args['command']}\n", style="bold white")
        else:
            t.append("ACTION ARGUMENTS:\n", style="bold cyan")
            t.append(json.dumps(self.args, indent=2), style="dim white")
        return t

    async def action_approve(self) -> None:
        if self._resolved:
            return
        self._resolved = True
        if self.approval_manager and self.approval_id:
            await self.approval_manager.resolve(self.approval_id, True)
        try:
            self.dismiss(True)
        except Exception:
            pass

    async def action_deny(self) -> None:
        if self._resolved:
            return
        self._resolved = True
        if self.approval_manager and self.approval_id:
            await self.approval_manager.resolve(self.approval_id, False)
        try:
            self.dismiss(False)
        except Exception:
            pass


    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-modal-approve":
            await self.action_approve()
        elif event.button.id == "btn-modal-deny":
            await self.action_deny()

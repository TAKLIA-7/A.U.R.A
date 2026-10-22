"""AURA Logs View — structured JSONL event stream viewer."""
from __future__ import annotations
import asyncio
import json
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.widgets import DataTable, Input, Label, RichLog, Static, Button
from textual.containers import Container, Horizontal, Vertical
from rich.text import Text
from rich.syntax import Syntax

from aura.config import get_config


def _clean_nulls(data: Any) -> Any:
    """Recursively strip None / null values from dictionaries and lists."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if v is not None:
                cv = _clean_nulls(v)
                if cv is not None and cv != {} and cv != []:
                    cleaned[k] = cv
        return cleaned
    elif isinstance(data, list):
        return [_clean_nulls(v) for v in data if v is not None]
    return data


def _extract_tool(ev: Dict[str, Any]) -> str:
    """Extract a human-readable tool or system source for the event."""
    action = ev.get("action") or {}
    if action.get("tool"):
        target = action.get("target")
        return f"{action['tool']}" + (f" ({target})" if target and target != action['tool'] else "")

    meta = ev.get("metadata") or {}
    if meta.get("tool"):
        return str(meta["tool"])

    etype = ev.get("event_type", "")
    if "agent.token_usage" in etype or "agent.response" in etype:
        return "agent"
    elif "run." in etype:
        return "orchestrator"
    elif "jev." in etype:
        return "jev.guard"
    elif "approval." in etype:
        return "approval.mgr"
    elif "policy." in etype:
        return "policy.engine"
    return "system"


def _extract_decision(ev: Dict[str, Any]) -> str:
    """Extract decision, status, or lifecycle stage."""
    decision = ev.get("decision") or {}
    if decision.get("result"):
        return str(decision["result"]).upper()

    jev = ev.get("jev") or {}
    if jev.get("risk_level"):
        rec = jev.get("recommended_action", "")
        return f"{jev['risk_level'].upper()}" + (f" ({rec.upper()})" if rec else "")
    elif jev.get("status"):
        return f"JEV:{jev['status'].upper()}"

    exec_info = ev.get("execution") or {}
    if exec_info.get("status"):
        return str(exec_info["status"]).upper()

    meta = ev.get("metadata") or {}
    if meta.get("resolution"):
        return f"RESOLVED:{meta['resolution'].upper()}"

    etype = ev.get("event_type", "")
    if "started" in etype:
        return "STARTED"
    elif "completed" in etype:
        return "COMPLETED"
    elif "failed" in etype:
        return "FAILED"
    elif "intercepted" in etype:
        return "INTERCEPTED"
    elif "proposed" in etype:
        return "PROPOSED"
    return "LOG"


def _extract_summary(ev: Dict[str, Any]) -> str:
    """Extract a meaningful summary line so no event has empty/null details."""
    action = ev.get("action") or {}
    params = action.get("parameters") or {}
    if "query" in params:
        return f"query: {params['query']}"[:50]
    elif "command" in params:
        return f"cmd: {params['command']}"[:50]
    elif "path" in params:
        return f"path: {params['path']}"[:50]

    decision = ev.get("decision") or {}
    if decision.get("reason"):
        return str(decision["reason"])[:50]

    jev = ev.get("jev") or {}
    if jev.get("risk_level"):
        factors = jev.get("risk_factors") or []
        f_str = f" [{', '.join(factors)}]" if factors else ""
        lat = f" in {jev.get('latency_ms', 0):.0f}ms" if jev.get("latency_ms") else ""
        return f"Risk: {jev['risk_level']}{lat}{f_str}"[:50]

    exec_info = ev.get("execution") or {}
    if exec_info.get("duration_ms") is not None:
        dur = exec_info["duration_ms"]
        tools = exec_info.get("tool_calls", 0)
        return f"Execution: {dur:.1f}ms (tool calls: {tools})"

    meta = ev.get("metadata") or {}
    if meta.get("input_tokens") is not None:
        return f"Tokens: {meta.get('input_tokens', 0):,} in / {meta.get('output_tokens', 0):,} out"
    if meta.get("resolution"):
        return f"Approval resolution: {meta['resolution']}"
    if meta.get("prompt"):
        return f"Prompt: {meta['prompt']}"[:50]
    if meta.get("error"):
        return f"Error: {meta['error']}"[:50]

    if ev.get("request_id"):
        return f"Req: {ev['request_id']}"
    return ev.get("event_type", "").replace("aura.", "")


class LogsView(Container):
    """Real-time audit log explorer for AURA events with non-null structured columns."""

    DEFAULT_CSS = """
    LogsView {
        layout: vertical;
        height: 1fr;
        background: #0a0a12;
    }
    #logs-header {
        height: 3;
        background: #0d0d1f;
        padding: 0 2;
        border-bottom: solid #1a1a30;
    }
    #logs-filters {
        height: 3;
        background: #0a0a18;
        layout: horizontal;
        padding: 0 1;
        align-vertical: middle;
    }
    #logs-filters Input {
        width: 18;
        height: 3;
        border: solid #222244;
        background: #0d0d20;
        color: #DDEEFF;
        margin-right: 1;
    }
    #logs-filters Button {
        height: 3;
        margin-left: 1;
    }
    #logs-layout {
        height: 1fr;
        layout: horizontal;
    }
    #logs-list {
        width: 3fr;
        border: solid #1a1a30;
    }
    #log-detail {
        width: 2fr;
        border: solid #1a1a30;
        background: #0a0a18;
        padding: 1;
        overflow-y: auto;
    }
    #logs-status {
        height: 1;
        background: #0a0a18;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._events: List[Dict] = []
        self._paused = False
        self._timer = None

    def compose(self) -> ComposeResult:
        with Container(id="logs-header"):
            yield Static(Text.from_markup("[bold cyan]◈ AUDIT LOGS[/bold cyan]  [dim]Real-time structured JSONL security event stream[/dim]"))
        with Horizontal(id="logs-filters"):
            yield Label("Level: ", classes="muted")
            yield Input(placeholder="INFO/WARN/ERR", id="filter-level")
            yield Label(" Type: ", classes="muted")
            yield Input(placeholder="action / jev / policy", id="filter-type")
            yield Label(" Search: ", classes="muted")
            yield Input(placeholder="tool / query / run_id", id="filter-search")
            yield Button("↻ Refresh", id="btn-refresh", variant="default")
            yield Button("⏸ Pause", id="btn-pause", variant="default")
        with Horizontal(id="logs-layout"):
            with Container(id="logs-list"):
                yield DataTable(id="logs-table", cursor_type="row")
            with Container(id="log-detail"):
                yield RichLog(id="log-detail-log", highlight=True, markup=True, wrap=True)
        with Container(id="logs-status"):
            yield Label(id="logs-status-label", classes="muted")

    def on_mount(self) -> None:
        table = self.query_one("#logs-table", DataTable)
        table.add_columns("Time", "Level", "Event Type", "Tool / Source", "Decision / State", "Summary / Details", "Run ID")
        self._timer = self.set_interval(3.0, self._periodic_refresh)
        self._load_events_sync()

    def _periodic_refresh(self) -> None:
        if not self._paused:
            self._load_events_sync()

    def _load_events_sync(self) -> None:
        asyncio.create_task(self._load_events())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            self._load_events_sync()
        elif event.button.id == "btn-pause":
            self._paused = not self._paused
            event.button.label = "▶ Resume" if self._paused else "⏸ Pause"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._load_events_sync()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self._events):
            ev = self._events[idx]
            detail = self.query_one("#log-detail-log", RichLog)
            detail.clear()

            clean = _clean_nulls(ev)
            etype = ev.get("event_type", "aura.event")
            lvl = ev.get("level", "INFO")
            ts = ev.get("timestamp", "")

            # Formatted Header Card
            detail.write(Text.from_markup(f"[bold cyan]EVENT:[/bold cyan] [bold white]{etype}[/bold white]  [bold yellow]{lvl}[/bold yellow]"))
            detail.write(Text.from_markup(f"[dim]Timestamp:[/dim]  {ts}"))
            if ev.get("run_id"):
                detail.write(Text.from_markup(f"[dim]Run ID:[/dim]     [cyan]{ev['run_id']}[/cyan]"))
            if ev.get("request_id"):
                detail.write(Text.from_markup(f"[dim]Request ID:[/dim] [white]{ev['request_id']}[/white]"))
            if ev.get("session_id"):
                detail.write(Text.from_markup(f"[dim]Session ID:[/dim] {ev['session_id']}"))

            # Formatted Action Section
            if "action" in clean and clean["action"]:
                act = clean["action"]
                detail.write(Text.from_markup("\n[bold #00CC88]ACTION DETAILS[/bold #00CC88]"))
                for k, v in act.items():
                    detail.write(Text.from_markup(f"  • [cyan]{k}:[/cyan] {v}"))

            # Formatted JEV Assessment Section
            if "jev" in clean and clean["jev"]:
                jev = clean["jev"]
                risk = jev.get("risk_level", "unknown").upper()
                r_color = "#00CC88" if risk in ("LOW", "NONE") else ("#FFAA00" if risk == "MEDIUM" else "#FF4444")
                detail.write(Text.from_markup(f"\n[bold {r_color}]JEV RISK ASSESSMENT ({risk})[/bold {r_color}]"))
                for k, v in jev.items():
                    detail.write(Text.from_markup(f"  • [cyan]{k}:[/cyan] {v}"))

            # Formatted Policy Decision Section
            if "decision" in clean and clean["decision"]:
                dec = clean["decision"]
                res = dec.get("result", "").upper()
                d_color = "#00CC88" if res == "ALLOW" else ("#FFAA00" if "APPROVAL" in res else "#FF4444")
                detail.write(Text.from_markup(f"\n[bold {d_color}]POLICY DECISION ({res})[/bold {d_color}]"))
                for k, v in dec.items():
                    detail.write(Text.from_markup(f"  • [cyan]{k}:[/cyan] {v}"))

            # Formatted Execution Section
            if "execution" in clean and clean["execution"]:
                exc = clean["execution"]
                detail.write(Text.from_markup("\n[bold #8844FF]EXECUTION METRICS[/bold #8844FF]"))
                for k, v in exc.items():
                    detail.write(Text.from_markup(f"  • [cyan]{k}:[/cyan] {v}"))

            # Formatted Metadata Section
            if "metadata" in clean and clean["metadata"]:
                meta = {k: v for k, v in clean["metadata"].items() if k != "schema_version"}
                if meta:
                    detail.write(Text.from_markup("\n[bold #4488FF]METADATA / CONTEXT[/bold #4488FF]"))
                    for k, v in meta.items():
                        detail.write(Text.from_markup(f"  • [cyan]{k}:[/cyan] {v}"))

            detail.write("\n" + "─" * 42 + "\n")
            detail.write(Text.from_markup("[dim]CLEAN STRUCTURED PAYLOAD (NO NULLS):[/dim]"))
            json_str = json.dumps(clean, indent=2)
            detail.write(Syntax(json_str, "json", theme="monokai", word_wrap=True))

    async def _load_events(self) -> None:
        try:
            from aura.observability import JSONLLogger
            cfg = get_config()
            logger = JSONLLogger(cfg.runtime.data_dir / "logs")
            level = self.query_one("#filter-level", Input).value.strip().upper() or None
            etype = self.query_one("#filter-type", Input).value.strip() or None
            search = self.query_one("#filter-search", Input).value.strip() or None
            events = await logger.read_events(limit=100, level_filter=level, event_type_filter=etype, search=search)
            self._events = events
            table = self.query_one("#logs-table", DataTable)
            table.clear()
            for ev in events:
                ts = (ev.get("timestamp") or "")
                time_str = ts[11:19] if len(ts) >= 19 else ts

                level_str = ev.get("level", "INFO")
                level_colors = {"INFO": "#00FFFF", "WARNING": "#FFAA00", "ERROR": "#FF4444", "DEBUG": "#555577", "CRITICAL": "#FF0000"}
                lc = level_colors.get(level_str, "white")

                et = ev.get("event_type", "").replace("aura.", "")
                tool_str = _extract_tool(ev)
                decision_str = _extract_decision(ev)

                # Color code decision
                dec_upper = decision_str.upper()
                if "ALLOW" in dec_upper or "COMPLETED" in dec_upper or "LOW" in dec_upper:
                    d_style = "bold #00CC88"
                elif "BLOCK" in dec_upper or "FAILED" in dec_upper or "CRITICAL" in dec_upper:
                    d_style = "bold #FF4444"
                elif "APPROVAL" in dec_upper or "WARN" in dec_upper or "MEDIUM" in dec_upper or "HIGH" in dec_upper:
                    d_style = "bold #FFAA00"
                else:
                    d_style = "dim cyan"

                summary_str = _extract_summary(ev)
                run_id = ev.get("run_id") or "─"

                table.add_row(
                    Text(time_str, style="dim cyan"),
                    Text(level_str, style=f"bold {lc}"),
                    Text(et, style="#DDEEFF"),
                    Text(tool_str, style="bold #AACCFF"),
                    Text(decision_str, style=d_style),
                    Text(summary_str, style="#CCDDEE"),
                    Text(run_id[:12], style="dim"),
                )
            status = self.query_one("#logs-status-label", Label)
            status.update(f"Loaded {len(events)} events  •  Paused: {self._paused}  •  Select any row to view structured details")
        except Exception:
            pass


# Alias for backward compatibility
LogsScreen = LogsView

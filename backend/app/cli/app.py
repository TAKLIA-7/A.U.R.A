"""Keyboard-first terminal interface for operating AURA through its API."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, DataTable, Footer, Input, Label, Static, TextArea

from backend.app.cli.api import AuraApiClient, AuraApiError
from backend.app.cli.formatting import format_tool_result, number, safe_json, token_totals, unavailable


class PromptInput(TextArea):
    """Multiline prompt editor where Enter sends and Ctrl+J adds a line."""

    class Submitted(Message):
        """Posted when the operator presses Enter in the composer."""

    BINDINGS = [
        Binding("enter", "submit_prompt", "Send", priority=True),
        Binding("ctrl+j", "insert_newline", "New line", priority=True),
    ]

    def action_submit_prompt(self) -> None:
        self.post_message(self.Submitted())

    def action_insert_newline(self) -> None:
        self.insert("\n")


class AuraTui(App[None]):
    """A live API client; policy, JEV, and execution remain server-owned."""

    TITLE = "AURA"
    SUB_TITLE = "Protected agent session"
    CSS = """
    Screen { background: #111111; color: #e6e6e6; }
    #shell { height: 1fr; }
    #topbar { height: 3; padding: 0 2; background: #191919; border-bottom: solid #343434; }
    #wordmark { width: 1fr; color: #f0b37e; text-style: bold; content-align: left middle; }
    #health { width: auto; color: #b4c7b0; content-align: right middle; }
    #nav { height: 3; padding: 0 2; background: #191919; border-bottom: solid #303030; }
    #nav Button { min-width: 18; margin-right: 1; background: #191919; border: none; color: #a9a9a9; }
    #nav Button:hover, #nav Button:focus { color: #f4f4f4; background: #282828; }
    .page { display: none; height: 1fr; padding: 1 2; }
    .page.active { display: block; }
    #session-line { height: 2; color: #a0a0a0; padding: 0 1; }
    #stats-line { height: 2; color: #929292; padding: 0 1; border-bottom: solid #303030; }
    #transcript-scroll { height: 1fr; padding: 1 1; background: #111111; scrollbar-gutter: stable; }
    #transcript { width: 1fr; padding: 0 1; color: #d1d1d1; }
    #composer-wrap { height: auto; max-height: 10; padding: 0 1; border: round #484848; background: #171717; }
    #composer { height: 5; min-height: 3; border: none; background: #171717; padding: 0; }
    #composer-hint { height: 1; color: #898989; padding: 0 1; }
    #chat-actions { height: 2; padding: 0 1; }
    #submit { min-width: 14; background: #f0b37e; color: #171717; text-style: bold; border: none; }
    .section-title { color: #f1f1f1; text-style: bold; margin-bottom: 1; }
    .muted { color: #979797; }
    #token-table, #log-table { height: 1fr; margin-top: 1; }
    #log-search { width: 1fr; }
    #refresh-logs { margin-left: 1; }
    #log-detail { height: 14; margin-top: 1; padding: 1; background: #171717; border: round #343434; overflow: auto; }
    Footer { background: #191919; color: #9b9b9b; }
    DataTable { background: #111111; }
    Input { background: #181818; border: round #3a3a3a; }
    """
    BINDINGS = [
        Binding("1", "show_page('dashboard')", "Session", show=False),
        Binding("2", "show_page('tokens')", "Usage", show=False),
        Binding("3", "show_page('logs')", "Traces", show=False),
        Binding("ctrl+r", "refresh_data", "Refresh", show=True),
    ]

    def __init__(self, api: AuraApiClient | None = None) -> None:
        super().__init__()
        self.api = api or AuraApiClient()
        self.current_page = "dashboard"
        self.token_rows: list[dict[str, Any]] = []
        self.log_rows: dict[str, dict[str, Any]] = {}
        self.transcript: list[tuple[str, str]] = []
        self.request_in_progress = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Label("AURA  /  PROTECTED AGENT SESSION", id="wordmark")
            yield Label("Connecting to local API…", id="health")
        with Horizontal(id="nav"):
            yield Button("1  Session", id="nav-dashboard", variant="primary")
            yield Button("2  Token usage", id="nav-tokens")
            yield Button("3  Logs & traces", id="nav-logs")
        with Container(id="dashboard", classes="page active"):
            yield Static("AURA routes protected tool actions through JEV and deterministic security checks.", id="session-line")
            yield Static("Actions  N/A     Blocked  N/A     Pending approvals  N/A     Avg decision  N/A", id="stats-line")
            with VerticalScroll(id="transcript-scroll"):
                yield Static("AURA terminal ready. Requests run in protected mode through the configured provider and JEV decision path.", id="transcript", markup=False)
            with Vertical(id="composer-wrap"):
                yield PromptInput("", id="composer", soft_wrap=True)
                with Horizontal(id="chat-actions"):
                    yield Static("Type a request · Enter send · Ctrl+J new line · Ctrl+R refresh · ? help", id="composer-hint", classes="muted")
                    yield Button("Send  ↵", id="submit")
        with Container(id="tokens", classes="page"):
            yield Static("TOKEN USAGE", classes="section-title")
            yield Static("Provider-reported usage for requests made in this terminal session. Missing usage stays unavailable.", classes="muted")
            yield DataTable(id="token-table", cursor_type="row")
        with Container(id="logs", classes="page"):
            yield Static("LOGS & TRACES", classes="section-title")
            with Horizontal():
                yield Input(placeholder="Search event, trace, action, or tool", id="log-search")
                yield Button("Refresh", id="refresh-logs")
            yield DataTable(id="log-table", cursor_type="row")
            yield Static("Select an event to inspect its redacted JSON and chronological trace.", id="log-detail")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#token-table", DataTable).add_columns("Time", "Trace", "Input", "Output", "Total")
        self.query_one("#log-table", DataTable).add_columns("Time", "Stage", "JEV", "AURA", "Execution", "Reason", "Tool", "Trace")
        self.run_worker(self.refresh_data(), exclusive=True)

    def action_show_page(self, page: str) -> None:
        self.current_page = page
        for name in ("dashboard", "tokens", "logs"):
            self.query_one(f"#{name}").set_class(name == page, "active")
        if page == "logs":
            self.run_worker(self.refresh_logs(), exclusive=True)
        elif page == "tokens":
            self.render_tokens()

    def action_refresh_data(self) -> None:
        self.run_worker(self.refresh_data(), exclusive=True)

    async def refresh_data(self) -> None:
        try:
            health, summary = await self.api.health(), await self.api.summary()
            jev_status = health.get("jev") or "JEV status unavailable"
            self.query_one("#health", Label).update(f"● {str(health.get('status', 'unknown')).upper()}   ·   {jev_status}")
            self.query_one("#stats-line", Static).update(
                f"Actions  {unavailable(summary.get('total_actions'))}     "
                f"Blocked  {unavailable(summary.get('blocked_actions'))}     "
                f"Pending approvals  {unavailable(summary.get('pending_approvals'))}     "
                f"Avg decision  {number(summary.get('average_decision_latency_ms'), ' ms')}"
            )
            if self.current_page == "logs":
                await self.refresh_logs()
        except AuraApiError as exc:
            self.query_one("#health", Label).update("● API UNAVAILABLE")
            self.notify(str(exc), severity="error")

    async def refresh_logs(self) -> None:
        try:
            result = await self.api.logs(self.query_one("#log-search", Input).value)
        except AuraApiError as exc:
            self.notify(str(exc), severity="error")
            return
        table = self.query_one("#log-table", DataTable)
        table.clear()
        self.log_rows = {}
        for row in result.get("items", []):
            event_id = str(row.get("event_id", ""))
            self.log_rows[event_id] = row
            table.add_row(
                str(row.get("timestamp", "N/A"))[-19:],
                unavailable(row.get("event_name")),
                self._jev_status(row),
                unavailable(row.get("aura_decision")),
                unavailable(row.get("execution_status")),
                ", ".join(row.get("reason_codes") or []) or "N/A",
                unavailable(row.get("tool_name")),
                str(row.get("trace_id") or "N/A")[:12],
                key=event_id,
            )

    async def submit_prompt(self) -> None:
        if self.request_in_progress:
            self.notify("A request is already running.", severity="warning")
            return
        self.request_in_progress = True
        try:
            await self._submit_prompt()
        finally:
            self.request_in_progress = False

    async def _submit_prompt(self) -> None:
        prompt = self.query_one("#composer", PromptInput)
        text = prompt.text.strip()
        if not text:
            self.notify("Type a request before sending.", severity="warning")
            return
        prompt.clear()
        self.append_transcript("you", text)
        trace_id = str(uuid.uuid4())
        status = self.query_one("#session-line", Static)
        status.update(f"Trace {trace_id[:12]} · waiting for the configured model…")
        self.append_transcript("aura", "Request received. Waiting for the agent and protected decision path…")
        started = time.monotonic()
        request = asyncio.create_task(self.api.run_prompt(text, trace_id=trace_id))
        try:
            latest_events: list[dict[str, Any]] = []
            while not request.done():
                await asyncio.sleep(1)
                try:
                    logs = await self.api.logs(trace_id)
                    latest_events = logs.get("items", [])
                    phase = self._progress_message(latest_events)
                except AuraApiError:
                    phase = "waiting for provider response"
                elapsed = int(time.monotonic() - started)
                status.update(f"Trace {trace_id[:12]} · {phase} · {elapsed}s")
            result = await request
            try:
                latest_events = (await self.api.logs(trace_id)).get("items", [])
            except AuraApiError:
                pass
        except AuraApiError as exc:
            status.update("Request failed · see the error below")
            self.replace_last_transcript("error", str(exc))
            return
        except Exception as exc:
            status.update("Request failed · see the error below")
            self.replace_last_transcript("error", f"Could not complete or display the response ({type(exc).__name__}).")
            return
        self.record_usage(result)
        self.replace_last_transcript("aura", self.format_run(result, latest_events))
        status.update("Protected request complete · JEV and AURA outcomes are shown above")
        self.render_tokens()
        await self.refresh_data()

    def append_transcript(self, speaker: str, content: str) -> None:
        self.transcript.append((speaker, content))
        self._render_transcript()

    def replace_last_transcript(self, speaker: str, content: str) -> None:
        if self.transcript:
            self.transcript[-1] = (speaker, content)
        else:
            self.transcript.append((speaker, content))
        self._render_transcript()

    def _render_transcript(self) -> None:
        transcript = "\n\n".join(f"{name.upper()}\n{message}" for name, message in self.transcript)
        self.query_one("#transcript", Static).update(transcript)
        self.query_one("#transcript-scroll", VerticalScroll).scroll_end(animate=False)

    def record_usage(self, result: dict[str, Any]) -> None:
        trace = str(result.get("run_id") or "N/A")
        for usage in result.get("usage") or []:
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            total_tokens = usage.get("total_tokens")
            if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
                total_tokens = input_tokens + output_tokens
            self.token_rows.append({
                "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "trace": trace,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "raw": usage,
            })

    def render_tokens(self) -> None:
        table = self.query_one("#token-table", DataTable)
        table.clear()
        for index, row in enumerate(sorted(self.token_rows, key=lambda item: item["time"], reverse=True)):
            table.add_row(row["time"], row["trace"][:12], unavailable(row["input_tokens"]), unavailable(row["output_tokens"]), unavailable(row["total_tokens"]), key=str(index))
        inputs, outputs, total = token_totals(self.token_rows)
        self.query_one("#tokens", Container).border_title = f"Session totals: input {unavailable(inputs)} · output {unavailable(outputs)} · total {unavailable(total)}"

    @staticmethod
    def _jev_status(row: dict[str, Any]) -> str:
        recommendation = row.get("jev_recommendation")
        state = row.get("jev_status")
        if recommendation:
            return f"{recommendation} ({state})" if state else str(recommendation)
        return str(state or "N/A")

    @staticmethod
    def _progress_message(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "waiting for provider response"
        latest = rows[0]
        event = latest.get("event_name")
        tool = latest.get("tool_name") or "tool"
        if event == "agent.action_received":
            return f"provider proposed {tool}; validating arguments"
        if event == "agent.arguments_validated":
            return f"arguments validated for {tool}"
        if event == "jev.assessment_started":
            return f"JEV assessing {tool}"
        if event == "jev.assessment_completed":
            return f"JEV assessment complete for {tool}; AURA enforcing policy"
        if event == "jev.assessment_failed":
            return f"JEV failed for {tool}; AURA is failing closed"
        if event == "aura.decision_made":
            return f"AURA decided {latest.get('aura_decision') or 'unavailable'} for {tool}"
        if event == "tool.execution_started":
            return f"AURA allowed {tool}; tool execution started"
        if event == "tool.execution_succeeded":
            return f"{tool} completed"
        if event == "tool.execution_not_attempted":
            return f"{tool} was not executed"
        return str(event or "processing request")

    @staticmethod
    def _decision_summary(rows: list[dict[str, Any]]) -> str:
        decisions = [row for row in rows if row.get("event_name") == "aura.decision_made"]
        executions = {
            row.get("action_id"): row
            for row in reversed(rows)
            if str(row.get("event_name", "")).startswith("tool.execution_")
        }
        if not decisions:
            return "No tool decision was recorded for this trace."
        lines = []
        for row in reversed(decisions):
            execution = executions.get(row.get("action_id"), {})
            reasons = ", ".join(row.get("reason_codes") or []) or "N/A"
            lines.append(
                f"{row.get('tool_name') or 'tool'}: JEV {row.get('jev_recommendation') or 'N/A'} "
                f"→ AURA {row.get('aura_decision') or 'N/A'} "
                f"→ execution {execution.get('execution_status') or 'N/A'} · reason {reasons}"
            )
        return "\n".join(lines)

    def format_run(self, result: dict[str, Any], events: list[dict[str, Any]] | None = None) -> str:
        tool_calls = result.get("tool_calls")
        if isinstance(tool_calls, int):
            tool_count = tool_calls
        elif isinstance(tool_calls, list):
            tool_count = len(tool_calls)
        else:
            tool_count = None
        events = events or []
        request_decision = result.get("request_decision") or {}
        lines = [
            f"Trace: {unavailable(result.get('run_id'))}",
            f"Provider: {unavailable(result.get('provider'))} · {unavailable(result.get('model'))}",
            f"Tool calls: {unavailable(tool_count)}",
            "",
            "AURA POLICY RESPONSE" if request_decision else "AGENT RESPONSE",
            str(result.get("answer") or "No assistant response was returned."),
        ]
        tool_results = result.get("tool_results") or []
        if request_decision:
            lines.extend([
                "",
                "REQUEST POLICY",
                f"JEV recommendation: {unavailable(request_decision.get('jev_recommendation'))}",
                f"AURA decision: {unavailable(request_decision.get('decision'))}",
                f"Execution: {unavailable(request_decision.get('execution_status'))}",
                f"Reason: {unavailable(request_decision.get('reason'))} · code {unavailable(request_decision.get('reason_code'))}",
            ])
        elif tool_results:
            for index, item in enumerate(tool_results, start=1):
                lines.extend([
                    "",
                    f"TOOL CALL {index} · {unavailable(item.get('tool_name'))}",
                    f"JEV recommendation: {unavailable(item.get('jev_recommendation'))}",
                    f"AURA decision: {unavailable(item.get('decision'))}",
                    f"Execution: {unavailable(item.get('execution_status'))}",
                    f"Reason: {unavailable(item.get('reason'))} · code {unavailable(item.get('reason_code'))}",
                ])
                if item.get("approval_id"):
                    lines.append(f"Approval: pending · {item['approval_id']}")
                lines.extend(["Tool result:", format_tool_result(item.get("result"))])
        else:
            lines.extend(["", "JEV / AURA / execution", self._decision_summary(events)])
        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "nav-dashboard":
            self.action_show_page("dashboard")
        elif event.button.id == "nav-tokens":
            self.action_show_page("tokens")
        elif event.button.id == "nav-logs":
            self.action_show_page("logs")
        elif event.button.id == "submit":
            self.run_worker(self.submit_prompt(), group="prompt", exclusive=False)
        elif event.button.id == "refresh-logs":
            self.run_worker(self.refresh_logs(), exclusive=True)

    def on_prompt_input_submitted(self, _event: PromptInput.Submitted) -> None:
        self.run_worker(self.submit_prompt(), group="prompt", exclusive=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "log-search":
            self.run_worker(self.refresh_logs(), exclusive=True)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "log-table":
            self.run_worker(self.show_log_detail(str(event.row_key.value)), exclusive=True)

    async def show_log_detail(self, event_id: str) -> None:
        try:
            detail = await self.api.log_detail(event_id)
        except AuraApiError as exc:
            self.notify(str(exc), severity="error")
            return
        timeline = detail.get("timeline") or []
        summary = "\n".join(
            f"{str(item.get('timestamp', 'N/A'))[-19:]}  {item.get('event_name', item.get('event_type', 'event'))}"
            f"  · JEV {item.get('jev_recommendation') or 'N/A'}"
            f"  · AURA {item.get('aura_decision') or 'N/A'}"
            f"  · execution {item.get('execution_status') or 'N/A'}"
            for item in timeline
        ) or "No related timeline records available."
        reasons = ", ".join(detail.get("reason_codes") or []) or "N/A"
        self.query_one("#log-detail", Static).update(
            f"JEV: {self._jev_status(detail)}   ·   AURA: {unavailable(detail.get('aura_decision'))}"
            f"   ·   Execution: {unavailable(detail.get('execution_status'))}\n"
            f"Reason: {reasons}   ·   Tool: {unavailable(detail.get('tool_name'))}\n\n"
            f"Timeline\n{summary}\n\nRedacted event JSON\n{safe_json(detail)}"
        )

    def on_key(self, event: events.Key) -> None:
        if event.key == "question_mark":
            self.notify("1 Session · 2 Token usage · 3 Logs/traces · Enter send · Ctrl+J newline · Ctrl+R refresh · Ctrl+C quit")


def main() -> None:
    AuraTui().run()


if __name__ == "__main__":
    main()

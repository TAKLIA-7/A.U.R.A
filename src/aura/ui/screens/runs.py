"""AURA Runs Screen."""
from __future__ import annotations
from typing import Any, Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Label, Static, RichLog
from textual.containers import Container, Horizontal, Vertical
from rich.text import Text
from rich.table import Table
from rich import box as rbox

from aura.observability import get_run_repo


class RunsView(Container):
    DEFAULT_CSS = """
    RunsView { background: #0a0a12; layout: vertical; height: 1fr; }
    #runs-header { height: 3; background: #0d0d1f; padding: 0 2; border-bottom: solid #1a1a30; }
    #runs-table { height: 1fr; border: solid #1a1a30; }
    #run-detail { height: 1fr; border: solid #1a1a30; background: #0d0d1e; padding: 1 2; overflow-y: auto; }
    #runs-layout { layout: horizontal; height: 1fr; }
    #runs-filter { height: 3; background: #0a0a18; padding: 0 2; }
    """


    def compose(self) -> ComposeResult:
        with Container(id="runs-header"):
            yield Static(
                Text.from_markup("[bold cyan]◈ RUNS[/bold cyan]  [dim]Historical and active agent executions[/dim]"),
                id="runs-title"
            )
        with Container(id="runs-layout"):
            with Container(id="runs-table-container", classes="panel"):
                yield DataTable(id="runs-table", cursor_type="row")
            with Container(id="run-detail", classes="panel"):
                yield RichLog(id="run-detail-log", highlight=True, markup=True, wrap=True)
        with Container(id="runs-filter"):
            yield Label(Text.from_markup("[dim]Select a run to view its execution timeline. Press [cyan]R[/cyan] to refresh.[/dim]"))

    def on_mount(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.add_columns("Run ID", "Status", "Started", "Duration", "Tools", "Allowed", "Blocked", "JEV")
        self.refresh_runs()

    def refresh_runs(self) -> None:
        import asyncio
        asyncio.create_task(self._load_runs())

    async def _load_runs(self) -> None:
        repo = get_run_repo()
        runs = await repo.list_runs(50)
        table = self.query_one("#runs-table", DataTable)
        table.clear()
        for run in runs:
            duration = f"{run.duration_ms:.0f}ms" if run.duration_ms else "─"
            started = run.started_at.strftime("%H:%M:%S") if run.started_at else "─"
            status_colors = {
                "running": "yellow", "completed": "green",
                "failed": "red", "cancelled": "dim", "timeout": "red",
            }
            sc = status_colors.get(run.status.value, "white")
            table.add_row(
                Text(run.run_id, style="#00FFFF"),
                Text(run.status.value.upper(), style=f"bold {sc}"),
                Text(started, style="dim"),
                Text(duration, style="#888899"),
                Text(str(run.total_tool_calls), style="white"),
                Text(str(run.allowed_actions), style="green"),
                Text(str(run.blocked_actions), style="red"),
                Text(str(run.jev_assessments), style="#AA44FF"),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        import asyncio
        asyncio.create_task(self._show_run_detail(event.row_index))

    async def _show_run_detail(self, row_idx: int) -> None:
        repo = get_run_repo()
        runs = await repo.list_runs(50)
        if row_idx >= len(runs):
            return
        run = runs[row_idx]
        log = self.query_one("#run-detail-log", RichLog)
        log.clear()
        log.write(Text.from_markup(f"[bold cyan]{run.run_id}[/bold cyan]  [{'green' if run.status.value=='completed' else 'red'}]{run.status.value.upper()}[/{'green' if run.status.value=='completed' else 'red'}]"))
        log.write(Text.from_markup(f"[dim]Prompt:[/dim] {run.user_prompt[:80]}"))
        log.write(Text.from_markup(f"[dim]Model:[/dim]  {run.model}"))
        log.write(Text.from_markup(f"[dim]Tools:[/dim]  {run.total_tool_calls}  [green]✓ {run.allowed_actions}[/green]  [red]✗ {run.blocked_actions}[/red]  [yellow]? {run.pending_approvals}[/yellow]"))
        log.write(Text.from_markup(f"[dim]JEV:[/dim]   {run.jev_assessments} assessments"))
        if run.input_tokens:
            log.write(Text.from_markup(f"[dim]Tokens:[/dim] {run.input_tokens} in / {run.output_tokens} out"))
        log.write("")
        log.write(Text.from_markup("[bold]EXECUTION TIMELINE[/bold]"))
        for ev in run.timeline:
            ts = ev.get("timestamp", "")[:19].replace("T", " ")
            et = ev.get("event_type", "")
            detail = ev.get("detail", {})
            color = "#00CC88" if "completed" in et or "executed" in et else ("#FF4444" if "blocked" in et or "failed" in et else "#888899")
            log.write(Text.from_markup(f"  [dim]{ts}[/dim]  [{color}]{et}[/{color}]"))

    def on_key(self, event) -> None:
        if event.key == "r":
            self.refresh_runs()

    def on_screen_resume(self) -> None:
        self.refresh_runs()


# Alias for backward compatibility
RunsScreen = RunsView

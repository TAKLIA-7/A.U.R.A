"""AURA Settings Screen."""
from __future__ import annotations
import asyncio
import os
from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from rich.text import Text

from aura.config import get_config


class SettingsView(Container):
    DEFAULT_CSS = """
    SettingsView { background: #0a0a12; layout: vertical; height: 1fr; }
    #settings-header { height: 3; background: #0d0d1f; padding: 0 2; border-bottom: solid #1a1a30; }
    #settings-scroll { height: 1fr; padding: 1 2; overflow-y: auto; }
    .settings-section { border: solid #1a1a30; background: #0d0d1e; padding: 1 2; margin: 0 0 1 0; }
    .settings-title { color: #00FFFF; text-style: bold; }
    .setting-row { layout: horizontal; height: 3; }
    .setting-label { width: 30; color: #888899; padding: 1 0; }
    .setting-value { width: 1fr; background: #0a0a18; color: #DDEEFF; border: solid #222244; padding: 0 1; }
    """


    def compose(self) -> ComposeResult:
        cfg = get_config()
        with Container(id="settings-header"):
            yield Static(Text.from_markup("[bold cyan]◈ SETTINGS[/bold cyan]  [dim]Provider, JEV, and runtime configuration[/dim]"))
        with ScrollableContainer(id="settings-scroll"):
            # LLM
            with Container(id="llm-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]LLM PROVIDER[/bold cyan]"), classes="settings-title")
                yield Static("")
                yield Static(Text.from_markup(f"  Provider:   [cyan]{cfg.llm.provider.upper()}[/cyan]"))
                yield Static(Text.from_markup(f"  Model:      [cyan]{cfg.llm.model}[/cyan]"))
                yield Static(Text.from_markup(f"  API Key:    [dim]{'● Configured' if cfg.llm.api_key else '○ Not configured (set OPENROUTER_API_KEY or GOOGLE_API_KEY)'}[/dim]"))
                yield Static(Text.from_markup("  [dim]Source: environment variables (.env)[/dim]"))
            # JEV
            with Container(id="jev-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold magenta]JEV RISK ENGINE[/bold magenta]"), classes="settings-title")
                yield Static("")
                if cfg.jev.mock_mode:
                    jev_mode = "⚠ MOCK MODE"
                    jev_color = "yellow"
                elif cfg.jev.provider == "openrouter":
                    jev_mode = f"● OPENROUTER ({cfg.jev.model.split('/')[-1]})"
                    jev_color = "green"
                else:
                    jev_mode = "● LIVE (JEV ENDPOINT)"
                    jev_color = "green"
                yield Static(Text.from_markup(f"  Engine:     [{jev_color}]{jev_mode}[/{jev_color}]"))
                yield Static(Text.from_markup(f"  Endpoint:   [cyan]{cfg.jev.endpoint or 'Default (OpenRouter/Mock)'}[/cyan]"))
                yield Static(Text.from_markup(f"  API Key:    [dim]{'● Configured' if cfg.jev.api_key else '○ Not set (AURA_JEV_API_KEY or OPENROUTER_API_KEY)'}[/dim]"))
                yield Static(Text.from_markup(f"  Timeout:    [white]{cfg.jev.timeout_seconds}s[/white]"))
                yield Static("")
                yield Static(Text.from_markup("  OpenRouter / Live JEV setup:\n    Set [cyan]OPENROUTER_API_KEY=sk-or-v1-...[/cyan] in [cyan].env[/cyan]\n    Or set [cyan]AURA_JEV_MOCK_MODE=false[/cyan] with [cyan]AURA_JEV_API_KEY[/cyan]"))
            # Runtime
            with Container(id="runtime-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]RUNTIME[/bold cyan]"), classes="settings-title")
                yield Static("")
                yield Static(Text.from_markup(f"  Data dir:          [cyan]{cfg.runtime.data_dir}[/cyan]"))
                yield Static(Text.from_markup(f"  Workspace root:    [cyan]{cfg.runtime.workspace_root}[/cyan]"))
                yield Static(Text.from_markup(f"  Max agent turns:   [white]{cfg.runtime.max_agent_turns}[/white]"))
                yield Static(Text.from_markup(f"  Max tool calls:    [white]{cfg.runtime.max_tool_calls}[/white]"))
                yield Static(Text.from_markup(f"  Agent timeout:     [white]{cfg.runtime.agent_timeout_seconds}s[/white]"))
                yield Static(Text.from_markup(f"  Monitor refresh:   [white]{cfg.display.monitor_refresh_seconds}s[/white]"))
            # Terminal UI & Display Settings
            with Container(id="display-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]TERMINAL UI & DISPLAY[/bold cyan]  [dim](create-agent-tui patterns)[/dim]"), classes="settings-title")
                yield Static("")
                yield Static(Text.from_markup(f"  Tool Display:      [cyan]{cfg.display.tool_display.upper()}[/cyan]  [dim](grouped | emoji | minimal | hidden)[/dim]"), id="cfg-tool-display")
                yield Static(Text.from_markup(f"  Loader Animation:  [cyan]{cfg.display.loader_style.upper()}[/cyan]  [dim](gradient shimmer | spinner | minimal)[/dim]"), id="cfg-loader-style")
                yield Static(Text.from_markup(f"  Input Style:       [cyan]{cfg.display.input_style.upper()}[/cyan]  [dim](bordered | block | plain)[/dim]"), id="cfg-input-style")
                yield Static("")
                with Horizontal():
                    yield Button("Cycle Tool Display", id="btn-toggle-tool-display")
                    yield Button("Cycle Loader", id="btn-toggle-loader")
                    yield Button("Cycle Input Style", id="btn-toggle-input-style")

            # Connectivity test
            with Container(id="connectivity-section", classes="settings-section"):
                yield Static(Text.from_markup("[bold cyan]CONNECTIVITY DIAGNOSTICS[/bold cyan]"), classes="settings-title")
                yield Static("")
                yield Static(id="connectivity-status")
                yield Button("Run Diagnostics", id="btn-diag")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg = get_config()
        if event.button.id == "btn-diag":
            asyncio.create_task(self._run_diagnostics())
        elif event.button.id == "btn-toggle-tool-display":
            modes = ["grouped", "emoji", "minimal", "hidden"]
            cur_idx = modes.index(cfg.display.tool_display) if cfg.display.tool_display in modes else 0
            cfg.display.tool_display = modes[(cur_idx + 1) % len(modes)]
            self.query_one("#cfg-tool-display", Static).update(
                Text.from_markup(f"  Tool Display:      [cyan]{cfg.display.tool_display.upper()}[/cyan]  [dim](grouped | emoji | minimal | hidden)[/dim]")
            )
            self.notify(f"Tool display set to: {cfg.display.tool_display}", severity="information")
        elif event.button.id == "btn-toggle-loader":
            styles = ["gradient", "spinner", "minimal"]
            cur_idx = styles.index(cfg.display.loader_style) if cfg.display.loader_style in styles else 0
            cfg.display.loader_style = styles[(cur_idx + 1) % len(styles)]
            self.query_one("#cfg-loader-style", Static).update(
                Text.from_markup(f"  Loader Animation:  [cyan]{cfg.display.loader_style.upper()}[/cyan]  [dim](gradient shimmer | spinner | minimal)[/dim]")
            )
            self.notify(f"Loader style set to: {cfg.display.loader_style}", severity="information")
        elif event.button.id == "btn-toggle-input-style":
            inputs = ["bordered", "block", "plain"]
            cur_idx = inputs.index(cfg.display.input_style) if cfg.display.input_style in inputs else 0
            cfg.display.input_style = inputs[(cur_idx + 1) % len(inputs)]
            self.query_one("#cfg-input-style", Static).update(
                Text.from_markup(f"  Input Style:       [cyan]{cfg.display.input_style.upper()}[/cyan]  [dim](bordered | block | plain)[/dim]")
            )
            self.notify(f"Input style set to: {cfg.display.input_style}", severity="information")

    async def _run_diagnostics(self) -> None:
        status = self.query_one("#connectivity-status", Static)
        status.update(Text.from_markup("  [yellow]Running diagnostics...[/yellow]"))
        app = self.app
        cfg = get_config()
        results = []
        if hasattr(app, "orchestrator") and app.orchestrator:
            provider_ok = await app.orchestrator.health_check_provider()
            jev_ok = await app.orchestrator.health_check_jev()
            p_name = cfg.llm.provider.capitalize()
            j_name = app.orchestrator.jev_mode.upper()
            results.append(f"  Agent provider ({p_name}): {'● OK' if provider_ok else '✗ FAILED / NO KEY'}")
            results.append(f"  JEV engine ({j_name}):     {'● OK' if jev_ok else '✗ FAILED'}")
        else:
            results.append("  Orchestrator not initialized.")
        t = Text()
        for r in results:
            color = "green" if "● OK" in r else "red"
            t.append(f"{r}\n", style=color)
        status.update(t)


# Alias for backward compatibility
SettingsScreen = SettingsView

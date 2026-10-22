"""AURA TUI Renderer — tool displays, formatting, and tree-branch rendering.

Adapted from the create-agent-tui pattern for Rich and Textual.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from rich.text import Text


TOOL_LABELS: Dict[str, Dict[str, str]] = {
    "sqlite.query": {"past": "Executed SQL query", "noun": "query"},
    "sqlite_query": {"past": "Executed SQL query", "noun": "query"},
    "filesystem.read": {"past": "Read file", "noun": "file"},
    "filesystem_read": {"past": "Read file", "noun": "file"},
    "filesystem.list": {"past": "Listed directory", "noun": "directory"},
    "filesystem_list": {"past": "Listed directory", "noun": "directory"},
    "filesystem.write": {"past": "Wrote file", "noun": "file"},
    "filesystem_write": {"past": "Wrote file", "noun": "file"},
    "shell.execute": {"past": "Ran shell command", "noun": "command"},
    "shell_execute": {"past": "Ran shell command", "noun": "command"},
    "diagnostic.ping": {"past": "Tested diagnostic ping", "noun": "ping"},
    "diagnostic_ping": {"past": "Tested diagnostic ping", "noun": "ping"},
    "mock.external_action": {"past": "Triggered external action", "noun": "action"},
    "mock_external_action": {"past": "Triggered external action", "noun": "action"},
}

TOOL_COLORS: Dict[str, str] = {
    "shell.execute": "#FF5555",
    "shell_execute": "#FF5555",
    "sqlite.query": "#00FFFF",
    "sqlite_query": "#00FFFF",
    "filesystem.read": "#00DDFF",
    "filesystem_read": "#00DDFF",
    "filesystem.list": "#4488FF",
    "filesystem_list": "#4488FF",
    "filesystem.write": "#FFAA00",
    "filesystem_write": "#FFAA00",
    "diagnostic.ping": "#AA44FF",
    "diagnostic_ping": "#AA44FF",
    "mock.external_action": "#CC00CC",
    "mock_external_action": "#CC00CC",
}


def format_tokens(n: Optional[int]) -> str:
    """Format token counts compactly (e.g., 1250 -> 1.3k)."""
    if n is None:
        return "0"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def format_duration(ms: Optional[float]) -> str:
    """Format millisecond duration into clean readable text."""
    if ms is None or ms <= 0:
        return ""
    if ms >= 1000:
        return f"({ms / 1000:.1f}s)"
    return f"({ms:.0f}ms)"


def summarize_args(tool: str, args: Dict[str, Any], max_len: int = 55) -> str:
    """Extract and format the primary argument for a tool call cleanly."""
    if not args:
        return ""

    norm = tool.replace("_", ".")
    if "query" in args:
        val = str(args["query"]).replace("\n", " ").strip()
        return f"query='{trunc(val, max_len)}'"
    elif "command" in args:
        val = str(args["command"]).strip()
        return f"command='{trunc(val, max_len)}'"
    elif "path" in args:
        val = str(args["path"]).strip()
        return f"path='{trunc(val, max_len)}'"
    elif "target" in args:
        val = str(args["target"]).strip()
        return f"target='{trunc(val, max_len)}'"
    elif "action_type" in args:
        return f"type='{args['action_type']}'"

    # Default to first key
    first_key = next(iter(args.keys()))
    val = str(args[first_key]).replace("\n", " ").strip()
    return f"{first_key}='{trunc(val, max_len)}'"


def trunc(s: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis if length exceeds max_len."""
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


class TuiRenderer:
    """Renders agent interactions, tool calls, and JEV decisions.

    Supports display modes: 'grouped', 'emoji', 'minimal', 'hidden'.
    """

    def __init__(self, display_mode: str = "grouped") -> None:
        self.display_mode = display_mode if display_mode in ("grouped", "emoji", "minimal", "hidden") else "grouped"
        self._tool_starts: Dict[str, float] = {}

    def record_tool_start(self, call_id: str, timestamp_s: float) -> None:
        self._tool_starts[call_id] = timestamp_s

    def get_tool_duration_ms(self, call_id: str, end_timestamp_s: float) -> Optional[float]:
        start = self._tool_starts.pop(call_id, None)
        if start is not None:
            return max(0.0, (end_timestamp_s - start) * 1000)
        return None

    def render_tool_proposed(self, tool: str, args: Dict[str, Any], request_id: str = "") -> Optional[Text]:
        if self.display_mode == "hidden":
            return None

        arg_str = summarize_args(tool, args)
        color = TOOL_COLORS.get(tool, "#FFAA00")
        label = TOOL_LABELS.get(tool, {}).get("past", tool)

        t = Text()
        if self.display_mode == "grouped":
            t.append("  ⚡ ", style="bold #FFAA00")
            t.append(f"{label} ", style=f"bold {color}")
            if arg_str:
                t.append(f"{arg_str} ", style="dim #AACCFF")
            t.append("[intercepting...]\n", style="dim #8888AA")
        elif self.display_mode == "minimal":
            t.append("  ⚡ ", style="bold #FFAA00")
            t.append(f"Intercepting {tool}...", style="dim #AACCFF")
            t.append("\n")
        else:  # emoji / inline
            t.append("  ⚡ PROPOSED: ", style="bold #FFAA00")
            t.append(f"{tool} ", style=f"bold {color}")
            if arg_str:
                t.append(f"{arg_str}\n", style="#AACCFF")
            else:
                t.append("\n")
        return t

    def render_tool_executed(
        self,
        tool: str,
        success: bool,
        output: Any,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> Optional[Text]:
        if self.display_mode == "hidden":
            return None

        dur_str = format_duration(duration_ms)
        color = TOOL_COLORS.get(tool, "#00FFFF")
        label = TOOL_LABELS.get(tool, {}).get("past", tool)

        t = Text()
        if success:
            if self.display_mode == "grouped":
                t.append("  ✓ ", style="bold #00CC88")
                t.append(f"{label} ", style="bold #00E5FF")
                if dur_str:
                    t.append(f"{dur_str}\n", style="dim #8888AA")
                else:
                    t.append("\n")

                # Branch output
                first_line = self._format_output_summary(output)
                if first_line:
                    t.append(f"    └── {first_line}\n", style="dim #AACCFF")

                # If SQL table, render it cleanly
                if isinstance(output, dict) and output.get("table"):
                    t.append("\n" + output["table"] + "\n\n", style="bold #00FFCC")

            elif self.display_mode == "minimal":
                t.append("  ✓ ", style="bold #00CC88")
                t.append(f"{tool} completed ", style="#AACCFF")
                if dur_str:
                    t.append(f"{dur_str}\n", style="dim #8888AA")
                else:
                    t.append("\n")

            else:  # emoji
                t.append("  ✓ EXECUTED: ", style="bold #00CC88")
                t.append(f"{tool} ", style=f"bold {color}")
                if dur_str:
                    t.append(f"{dur_str}\n", style="dim #8888AA")
                else:
                    t.append("\n")
                if isinstance(output, dict) and output.get("table"):
                    t.append("\n" + output["table"] + "\n\n", style="bold #00FFCC")
                else:
                    summary = self._format_output_summary(output)
                    if summary:
                        t.append(f"    {summary}\n", style="#AACCFF")

        else:
            err_msg = error or self._format_output_summary(output) or "Unknown error"
            t.append("  ✗ FAILED: ", style="bold #FF4444")
            t.append(f"{tool} ", style="bold #FF4444")
            if dur_str:
                t.append(f"{dur_str} ", style="dim")
            t.append(f"— {err_msg}\n", style="#FF6666")

        return t

    def render_tool_blocked(self, tool: str, reason: str, policy_id: str = "") -> Optional[Text]:
        if self.display_mode == "hidden":
            return None

        t = Text()
        t.append("  ✗ BLOCKED: ", style="bold #FF4444")
        t.append(f"{tool}\n", style="bold #FF4444")
        branch = "    └── " if self.display_mode == "grouped" else "    "
        t.append(f"{branch}{reason}", style="#FF7777")
        if policy_id:
            t.append(f" [{policy_id}]", style="dim #FFAA00")
        t.append("\n")
        return t

    def render_jev_assessment(
        self,
        risk_level: str,
        recommended_action: str,
        factors: Optional[List[str]] = None,
        latency_ms: Optional[float] = None,
    ) -> Optional[Text]:
        if self.display_mode == "hidden":
            return None

        risk_colors = {
            "critical": "#FF0000",
            "high": "#FF4444",
            "medium": "#FFAA00",
            "low": "#00CC88",
            "none": "#555577",
        }
        color = risk_colors.get(risk_level.lower(), "#AAAAAA")
        lat_str = format_duration(latency_ms)

        t = Text()
        t.append("  ◉ JEV ASSESSMENT  ", style="bold #AA44FF")
        t.append("Risk: ", style="dim")
        t.append(f"[{risk_level.upper()}] ", style=f"bold {color}")
        t.append(f"→ {recommended_action.upper()}", style="bold #00FFFF")
        if lat_str:
            t.append(f" {lat_str}", style="dim #8888AA")
        t.append("\n")

        if factors:
            f_str = ", ".join(factors)
            t.append(f"    Factors: {f_str}\n", style="dim #FFAA55")
        return t

    def render_run_completed(
        self,
        run_id: str,
        status: str,
        allowed: int,
        blocked: int,
        jev_count: int = 0,
        tool_calls: int = 0,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        duration_ms: Optional[float] = None,
    ) -> Text:
        t = Text()
        t.append("\n  ╭── RUN COMPLETE ─────────────────────────────────────────────╮\n", style="bold #333366")
        t.append("  │ ", style="bold #333366")
        t.append("Run ID:   ", style="dim")
        t.append(f"{run_id:<22} ", style="bold #00FFFF")

        status_color = "#00CC88" if status == "completed" else "#FF4444"
        t.append("Status: ", style="dim")
        t.append(f"{status.upper():<14} ", style=f"bold {status_color}")
        t.append("│\n", style="bold #333366")

        t.append("  │ ", style="bold #333366")
        t.append("Tools:    ", style="dim")
        t.append(f"{tool_calls} total ", style="white")
        t.append(f"({allowed} allowed, {blocked} blocked)  ", style="dim")
        t.append("│\n", style="bold #333366")

        if input_tokens is not None or output_tokens is not None:
            t.append("  │ ", style="bold #333366")
            t.append("Tokens:   ", style="dim")
            t.append(f"{format_tokens(input_tokens)} in  •  {format_tokens(output_tokens)} out", style="#AACCFF")
            t.append(" " * 20, style="")
            t.append("│\n", style="bold #333366")

        if duration_ms is not None:
            t.append("  │ ", style="bold #333366")
            t.append("Duration: ", style="dim")
            t.append(f"{format_duration(duration_ms)}", style="#8888AA")
            t.append(" " * 38, style="")
            t.append("│\n", style="bold #333366")

        t.append("  ╰─────────────────────────────────────────────────────────────╯\n\n", style="bold #333366")
        return t

    def _format_output_summary(self, output: Any) -> str:
        if isinstance(output, dict):
            if "stdout" in output:
                return trunc(str(output["stdout"]).split("\n")[0].strip(), 75)
            elif "content" in output:
                return trunc(str(output["content"]).split("\n")[0].strip(), 75)
            elif "entries" in output:
                entries = output["entries"]
                return f"{len(entries)} items listed ({', '.join(entries[:4])}...)"
            elif "rows_affected" in output:
                return f"{output['rows_affected']} rows affected"
            elif "error" in output:
                return f"error: {output['error']}"
            elif output:
                first_key = next(iter(output.keys()))
                return trunc(f"{first_key}: {output[first_key]}", 70)
        elif isinstance(output, str):
            return trunc(output.split("\n")[0].strip(), 75)
        return ""

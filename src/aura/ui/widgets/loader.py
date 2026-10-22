"""AURA animated loader widget.

Adapted from the create-agent-tui loader pattern with gradient shimmer,
braille spinner, and minimal dot styles.
"""
from __future__ import annotations
from typing import Optional
from textual.widgets import Static
from rich.text import Text

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

GRADIENT_PALETTE = [
    "#00FFFF",  # bright cyan
    "#22DDFF",
    "#44AAFF",
    "#6677FF",
    "#8844FF",
    "#AA22FF",
    "#CC00EE",
    "#FF00CC",  # vibrant magenta
    "#CC00EE",
    "#AA22FF",
    "#8844FF",
    "#6677FF",
    "#44AAFF",
    "#22DDFF",
]


class AURALoader(Static):
    """Animated status indicator showing agent thinking, JEV evaluation, or execution."""

    DEFAULT_CSS = """
    AURALoader {
        height: 1;
        background: transparent;
        padding: 0 1;
        margin: 0;
        display: none;
    }
    AURALoader.active {
        display: block;
    }
    """

    def __init__(
        self,
        text: str = "Thinking...",
        style: str = "gradient",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.text_label = text
        self.loader_style = style if style in ("gradient", "spinner", "minimal") else "gradient"
        self._frame = 0
        self._timer = None
        self._active = False

    def start(self, text: Optional[str] = None) -> None:
        if text:
            self.text_label = text
        self._frame = 0
        self._active = True
        self.add_class("active")
        interval = 0.10 if self.loader_style == "spinner" else (0.12 if self.loader_style == "gradient" else 0.3)
        if self._timer is None:
            self._timer = self.set_interval(interval, self._tick)
        self.refresh()

    def set_text(self, text: str) -> None:
        self.text_label = text
        self.refresh()

    def stop(self) -> None:
        self._active = False
        self.remove_class("active")
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.update("")
        self.refresh()

    def _tick(self) -> None:
        if not self._active:
            return
        self._frame += 1
        self.update(self._render_frame())

    def _render_frame(self) -> Text:
        t = Text()
        if self.loader_style == "spinner":
            char = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
            t.append("  ", style="")
            t.append(char, style="bold #00FFFF")
            t.append(f"  {self.text_label}", style="#AACCFF")
        elif self.loader_style == "minimal":
            dots = [".", "..", "..."]
            dot_str = dots[self._frame % len(dots)]
            t.append("  ", style="")
            t.append(f"{self.text_label}{dot_str:<3}", style="dim #00FFFF")
        else:  # gradient shimmer
            palette_len = len(GRADIENT_PALETTE)
            t.append("  ◈ ", style="bold #00FFFF")
            full_text = self.text_label
            for i, ch in enumerate(full_text):
                color_idx = (self._frame + i) % palette_len
                t.append(ch, style=f"bold {GRADIENT_PALETTE[color_idx]}")
        return t

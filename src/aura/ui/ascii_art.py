"""AURA ASCII art logo and visual elements."""
from rich.text import Text
from rich.console import Console

AURA_LOGO_LINES = [
    "  ██████╗   ██╗   ██╗  ██████╗    ██████╗  ",
    "  ██╔══██╗  ██║   ██║  ██╔══██╗  ██╔══██╗  ",
    "  ███████║  ██║   ██║  ██████╔╝  ███████║  ",
    "  ██╔══██║  ██║   ██║  ██╔══██╗  ██╔══██║  ",
    "  ██║  ██║  ╚██████╔╝  ██║  ██║  ██║  ██║  ",
    "  ╚═╝  ╚═╝   ╚═════╝   ╚═╝  ╚═╝  ╚═╝  ╚═╝  ",
]

AURA_SHADOW_LINES = [
    "  ▓▓▓▓▓▓░   ▓▓░  ▓▓░  ▓▓▓▓▓▓░   ▓▓▓▓▓▓░  ",
    "  ▒▒░  ▒▒░  ▒▒░  ▒▒░  ▒▒░  ▒▒░  ▒▒░  ▒▒░  ",
    "  ░░░  ░░░   ░░░░░░░   ░░░  ░░░  ░░░  ░░░  ",
]

GRADIENT_COLORS = [
    "#00FFFF",  # cyan
    "#00DDFF",
    "#00BBFF",
    "#4488FF",
    "#6644FF",
    "#8822FF",
    "#AA00FF",
    "#CC00EE",
    "#FF00CC",  # magenta
]


def make_gradient_logo() -> Text:
    """Return a Rich Text object with gradient-colored AURA logo."""
    t = Text()
    num_lines = len(AURA_LOGO_LINES)
    for i, line in enumerate(AURA_LOGO_LINES):
        # Interpolate color across lines
        frac = i / max(num_lines - 1, 1)
        idx = int(frac * (len(GRADIENT_COLORS) - 1))
        color = GRADIENT_COLORS[idx]
        t.append(line + "\n", style=f"bold {color}")
    return t


def make_tagline() -> Text:
    t = Text()
    t.append("\n  A", style="bold #00FFFF")
    t.append(" U", style="bold #4488FF")
    t.append(" R", style="bold #8822FF")
    t.append(" A", style="bold #FF00CC")
    t.append("  //  ", style="dim white")
    t.append("AGENT CONTROL PLANE\n", style="bold white")
    t.append("\n  Contextual decisions  •  Controlled execution  •  Complete observability\n", style="dim cyan")
    return t


def get_version_text() -> Text:
    t = Text()
    t.append("  v0.1.0", style="dim magenta")
    return t

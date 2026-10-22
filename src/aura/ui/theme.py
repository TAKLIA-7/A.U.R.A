"""AURA Textual CSS theme."""

AURA_CSS = """
Screen {
    background: #0a0a12;
}

Header {
    background: #0d0d1f;
    color: #00FFFF;
    height: 3;
}

Footer {
    background: #0d0d1f;
    color: #888899;
    height: 1;
}

TabbedContent {
    background: #0a0a12;
    height: 1fr;
}

Tabs {
    background: #0a0a18;
    height: 3;
    border-bottom: solid #1a1a30;
}

Tab {
    color: #666688;
    padding: 0 2;
    height: 3;
    background: #0a0a18;
}

Tab:hover {
    color: #00FFFF;
    background: #14142a;
}

Tab.-active {
    color: #00FFFF;
    background: #1a1a35;
    text-style: bold;
    border-bottom: tall #00FFFF;
}

TabPane {
    background: #0a0a12;
    padding: 0;
    height: 1fr;
}


.nav-tab:hover {
    color: #00FFFF;
}

.nav-tab.active {
    color: #00FFFF;
    background: #1a1a2e;
    text-style: bold;
}

.panel {
    border: solid #222244;
    background: #0d0d20;
    padding: 1 2;
}

.panel-title {
    color: #00FFFF;
    text-style: bold;
}

.status-bar {
    background: #0a0a18;
    color: #888899;
    height: 1;
    padding: 0 1;
}

.jev-badge {
    color: #AA44FF;
}

.success {
    color: #00CC88;
}

.warning {
    color: #FFAA00;
}

.error {
    color: #FF4444;
}

.blocked {
    color: #FF4444;
    text-style: bold;
}

.allowed {
    color: #00CC88;
    text-style: bold;
}

.pending {
    color: #FFAA00;
}

.muted {
    color: #555577;
}

.agent-text {
    color: #DDEEFF;
}

.user-text {
    color: #AACCFF;
    text-style: bold;
}

.tool-name {
    color: #00FFFF;
    text-style: bold;
}

.risk-high {
    color: #FF4444;
}

.risk-medium {
    color: #FFAA00;
}

.risk-low {
    color: #00CC88;
}

.risk-none {
    color: #555577;
}

Input {
    background: #0d0d20;
    border: tall #222244;
    color: #DDEEFF;
    padding: 0 2;
}

Input:focus {
    border: tall #00FFFF;
}

Button {
    background: #1a1a30;
    color: #00FFFF;
    border: solid #222244;
}

Button:hover {
    background: #222244;
    border: solid #00FFFF;
}

Button.danger {
    background: #300010;
    color: #FF4444;
    border: solid #440022;
}

Button.danger:hover {
    background: #440022;
    border: solid #FF4444;
}

Button.success {
    background: #003020;
    color: #00CC88;
    border: solid #004433;
}

DataTable {
    background: #0d0d20;
}

DataTable > .datatable--header {
    background: #0a0a18;
    color: #00FFFF;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1a1a35;
}

RichLog {
    background: #0d0d20;
    border: solid #1a1a30;
}

Label {
    color: #AABBCC;
}

/* Input style variations adapted from create-agent-tui */
.input-bordered {
    background: transparent;
    border: none;
    padding: 0 1;
}

.input-block {
    background: #0d0d22;
    border: tall #222244;
    padding: 0 1;
}
.input-block:focus-within {
    border: tall #00FFFF;
}

.input-plain {
    background: transparent;
    border: none;
    padding: 0;
}

.chip-tag {
    background: #14142a;
    color: #00FFFF;
    padding: 0 1;
    margin-right: 1;
}

.chip-dim {
    background: #101020;
    color: #666688;
    padding: 0 1;
}
"""

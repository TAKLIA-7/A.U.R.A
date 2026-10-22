# A.U.R.A — Agent Control Plane & Observability CLI

```
 █████╗ ██╗   ██╗██████╗  █████╗
██╔══██╗██║   ██║██╔══██╗██╔══██╗
███████║██║   ██║██████╔╝███████║
██╔══██║██║   ██║██╔══██╗██╔══██║
██║  ██║╚██████╔╝██║  ██║██║  ██║
╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
Autonomous Unified Runtime Architecture
```

**AURA** is an interactive, terminal-based agent middleware (TUI) that intercepts agent actions, submits contextual risk assessments to **JEV** (Judge & Evaluation Validator), enforces security decisions, controls tool execution, and provides real-time observability into AI agent behavior.

---

## 🌟 Key Features

- **Runtime Action Interception**: Intercepts all proposed tool operations before execution (`filesystem.list`, `filesystem.read`, `shell.execute`, `diagnostic.ping`, etc.).
- **JEV Risk Assessment Engine**:
  - **OpenRouter AI Engine**: Uses OpenRouter models (`google/gemini-2.0-flash-001`, `anthropic/claude-3.5-haiku`, `meta-llama/llama-3.3-70b-instruct`) as dynamic, intelligent JEV risk evaluators.
  - **Proprietary JEV Endpoint**: HTTP client adapter for internal enterprise JEV endpoints.
  - **Mock JEV Client**: Built-in deterministic risk simulation for offline testing and demos.
- **Dual Policy Enforcement**:
  - Deterministic allowlists and path traversal barriers (`..` detection).
  - Fast-allow rules for benign diagnostic tools.
  - JEV risk thresholding (`NONE`/`LOW` -> ALLOW, `MEDIUM` -> APPROVAL, `HIGH`/`CRITICAL` -> BLOCK).
  - Human-in-the-loop interactive approvals for mutating operations.
- **Interactive Terminal UI (TUI)**: Built with **Textual** & **Rich** featuring:
  - `[1] CHAT`: Interactive chat session with live agent thought streaming, action interception badges, JEV risk cards, and human-in-the-loop approval dialogs.
  - `[2] RUNS`: Session run history, status, action counts, and duration.
  - `[3] LOGS`: Real-time streaming audit event log viewer.
  - `[4] MONITOR`: Live telemetry, throughput metrics, risk distribution, and latency sparklines.
  - `[5] POLICIES`: Active security policies and rule engine configuration.
  - `[6] SETTINGS`: Live connectivity diagnostics and provider settings.
- **Observability & Audit Trail**: Structured event bus with append-only JSONL logging (`data/logs/aura-events.jsonl`).

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository and install dependencies in editable mode
pip install -e .
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

#### If using OpenRouter:
```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
AURA_JEV_PROVIDER=openrouter
AURA_LLM_PROVIDER=openrouter
AURA_JEV_MODEL=google/gemini-2.0-flash-001
AURA_JEV_MOCK_MODE=false
```

#### If using Google Gemini directly:
```env
GOOGLE_API_KEY=AIzaSy...
AURA_LLM_PROVIDER=gemini
AURA_JEV_MOCK_MODE=true  # or configure real JEV endpoint
```

### 3. Launching AURA

```bash
# Launch interactive TUI
aura

# Launch in mock mode (no API keys required, ideal for testing)
aura --mock
```

---

## ⌨️ Navigation & Controls

| Key | Description |
|---|---|
| `1` | Switch to **CHAT** screen |
| `2` | Switch to **RUNS** screen |
| `3` | Switch to **LOGS** screen |
| `4` | Switch to **MONITOR** screen |
| `5` | Switch to **POLICIES** screen |
| `6` | Switch to **SETTINGS** screen |
| `Tab` | Focus next interactive element |
| `Enter` | Submit prompt / Confirm action |
| `Ctrl+C` | Quit AURA |

---

## 🧪 Running Tests

AURA includes a comprehensive test suite across unit, integration, and security layers:

```bash
pytest tests -v
```

---

## 📐 Architecture

```
User Prompt
    │
    ▼
┌──────────────────────────────────────────────┐
│                AURA Agent                    │
│   (OpenRouter / Gemini / Mock LLM)          │
└──────────────────────┬───────────────────────┘
                       │ Proposes Tool Call
                       ▼
┌──────────────────────────────────────────────┐
│             AURA Gateway / Proxy             │
│   Deterministic Rules & Path Traversal Check │
└──────────────────────┬───────────────────────┘
                       │ Normalized Context Payload
                       ▼
┌──────────────────────────────────────────────┐
│           JEV Risk Assessment Engine         │
│   (OpenRouter AI / JEV Endpoint / Mock)      │
└──────────────────────┬───────────────────────┘
                       │ Risk Level & Recommended Action
                       ▼
┌──────────────────────────────────────────────┐
│           AURA Policy Enforcement            │
│  ALLOW ──► Execute Tool ──► Agent Turn       │
│  BLOCK ──► Terminate Action ──► Audit Log    │
│  APPROVE ─► Prompt Human Operator            │
└──────────────────────────────────────────────┘
```

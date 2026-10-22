# AURA — How to Run & User Guide

A step-by-step guide to installing, configuring, running, and demonstrating **AURA** (Autonomous Unified Runtime Architecture) — the interactive agent runtime, risk interception, and observability terminal interface.

---

## 📋 Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation & Setup](#2-installation--setup)
3. [Configuration (.env)](#3-configuration-env)
   - [Option A: Using OpenRouter (Recommended)](#option-a-using-openrouter-recommended)
   - [Option B: Using Google Gemini Directly](#option-b-using-google-gemini-directly)
   - [Option C: Zero-Key Mock Mode (Offline Demo)](#option-c-zero-key-mock-mode-offline-demo)
4. [How to Launch AURA](#4-how-to-launch-aura)
5. [Interface Overview & Navigation](#5-interface-overview--navigation)
6. [Interactive Walkthrough & Sample Prompts](#6-interactive-walkthrough--sample-prompts)
   - [Scenario 1: Low-Risk Read Operation (Auto-Allowed)](#scenario-1-low-risk-read-operation-auto-allowed)
   - [Scenario 2: Mutating Operation (Human Approval Required)](#scenario-2-mutating-operation-human-approval-required)
   - [Scenario 3: High-Risk Shell Command (Blocked by JEV / Policy)](#scenario-3-high-risk-shell-command-blocked-by-jev--policy)
   - [Scenario 4: Path Traversal Attack (Blocked Deterministically)](#scenario-4-path-traversal-attack-blocked-deterministically)
7. [Observability & Audit Logs](#7-observability--audit-logs)
8. [Keyboard Shortcuts Cheat Sheet](#8-keyboard-shortcuts-cheat-sheet)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

- **Operating System**: Windows, macOS, or Linux
- **Python**: Version 3.11 or higher
- **Terminal**: Modern terminal with 256-color / UTF-8 support (Windows Terminal, VS Code integrated terminal, iTerm2, Kitty, Alacritty, etc.)

Check your Python version:
```bash
python --version
```

---

## 2. Installation & Setup

1. Open a terminal in the project directory:
   ```bash
   cd A.U.R.A
   ```

2. (Optional but recommended) Activate your Python virtual environment if you use one.

3. Install AURA in editable mode:
   ```bash
   pip install -e .
   ```

4. Verify that the CLI command is registered:
   ```bash
   aura --version
   ```
   *Expected output:* `AURA 0.1.0`

---

## 3. Configuration (.env)

Create a `.env` file in the project root directory. You can copy the template:
```bash
# Windows PowerShell:
Copy-Item .env.example .env

# Bash / Linux / macOS:
cp .env.example .env
```

Open `.env` in your text editor and select one of the following setups:

---

### Option A: Using OpenRouter (Recommended)

If you have an **OpenRouter API Key**, AURA will use OpenRouter for both **Agent execution** and **JEV risk evaluations**:

```env
# ── OpenRouter Key ─────────────────────────────────────────────
OPENROUTER_API_KEY=sk-or-v1-your-actual-key-here

# ── JEV Risk Assessment Engine ─────────────────────────────────
AURA_JEV_PROVIDER=openrouter
AURA_JEV_MODEL=google/gemini-2.0-flash-001
AURA_JEV_MOCK_MODE=false
AURA_JEV_TIMEOUT_SECONDS=12

# ── LLM Agent Provider ─────────────────────────────────────────
AURA_LLM_PROVIDER=openrouter
AURA_LLM_MODEL=google/gemini-2.0-flash-001
AURA_LLM_BASE_URL=https://openrouter.ai/api/v1

# ── Runtime & Observability ────────────────────────────────────
AURA_DATA_DIR=./data
AURA_WORKSPACE_ROOT=.
AURA_LOG_LEVEL=INFO
AURA_MAX_AGENT_TURNS=20
AURA_MAX_TOOL_CALLS=10
```

> **Tip:** You can replace `google/gemini-2.0-flash-001` with any model available on OpenRouter, such as `anthropic/claude-3.5-haiku` or `meta-llama/llama-3.3-70b-instruct`.

---

### Option B: Using Google Gemini Directly

If you prefer using Google AI Studio directly:

```env
# ── Google Gemini Key ──────────────────────────────────────────
GOOGLE_API_KEY=AIzaSy-your-actual-gemini-key-here
AURA_LLM_PROVIDER=gemini
AURA_LLM_MODEL=gemini-2.0-flash

# ── JEV Risk Assessment Engine ─────────────────────────────────
# Use built-in mock JEV rules or a dedicated JEV endpoint:
AURA_JEV_MOCK_MODE=true
```

---

### Option C: Zero-Key Mock Mode (Offline Demo)

You do **not** need any API key to explore or test AURA. Launch with `--mock` to use built-in simulated providers:

```bash
aura --mock
```

---

## 4. How to Launch AURA

To start the interactive Terminal User Interface (TUI):

```bash
aura
```

Alternatively, you can run it via Python module syntax:
```bash
python -m aura.cli
```

### CLI Command Flags

| Command | Action |
|---|---|
| `aura` | Starts AURA TUI using configuration in `.env` |
| `aura --mock` | Forces zero-key Mock mode for all providers |
| `aura --no-color` | Disables ANSI color styling |
| `aura --data-dir <path>` | Custom storage path for runs and audit logs |
| `aura --version` | Displays current version (`0.1.0`) |
| `aura --help` | Displays help message and parameter list |

---

## 5. Interface Overview & Navigation

AURA features a tabbed interface with mouse support and responsive scrolling across all terminal window sizes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  AURA  // AGENT CONTROL PLANE   AGENT ●   JEV ● [OPENROUTER]  MODEL: gemini │
├─────────────────────────────────────────────────────────────────────────────┤
│ ⚡ [1] CHAT │ 📋 [2] RUNS │ 📜 [3] LOGS │ 📊 [4] MONITOR │ 🛡️ [5] POLICIES │ ⚙️ [6] SETTINGS
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                        (Active View Content - Scrollable)                   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ RUN: run_a8f910  STATE: IDLE  JEV: OPENROUTER  •  Click Tab or press [F1]-[F6]│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Navigating Between Views

You have 3 easy ways to switch views:

1. **Mouse Click**: Click directly on any tab at the top (`[1] CHAT`, `[2] RUNS`, `[3] LOGS`, `[4] MONITOR`, `[5] POLICIES`, `[6] SETTINGS`).
2. **Function Keys**: Press **`F1`** through **`F6`** (or `Ctrl+1` through `Ctrl+6`).
3. **Slash Commands**: Type `/chat`, `/runs`, `/logs`, `/monitor`, `/policies`, or `/settings` into the chat box.

### The 6 Views Explained:

1. **`[1] CHAT`**: Primary workspace. Prompt the agent, watch live thinking, see real-time tool interception cards, view JEV risk ratings, and review human-in-the-loop approval dialogs.
2. **`[2] RUNS`**: Execution audit table showing historical sessions, durations, allowed/blocked action counters, and timeline inspection.
3. **`[3] LOGS`**: Live streaming audit log feed of structured `aura.*` JSONL events with search and level filters (`INFO`, `WARNING`, `ERROR`).
4. **`[4] MONITOR`**: Telemetry dashboard displaying:
   - Agent health & active run counters
   - JEV risk engine status & p50/p95 latency percentiles
   - Visual JEV decision latency sparklines
   - Policy decision bar charts (ALLOW, BLOCK, PENDING)
   - Risk distribution breakdown (Critical, High, Medium, Low)
   - Real-time audit activity feed
   - **`[↻ Refresh Now]`** button
5. **`[5] POLICIES`**: Interactive security rules inspector displaying tool allowlists, path traversal boundaries, and pending approval queues with `[Approve]` and `[Deny]` buttons.
6. **`[6] SETTINGS`**: Environment inspector and live connectivity diagnostics test suite for OpenRouter, JEV, and local runtime directories.


---

## 6. Interactive Walkthrough & Sample Prompts

Switch to the **CHAT** screen (press `1`) and enter prompts into the input box at the bottom.

### Scenario 1: Low-Risk Read Operation (Auto-Allowed)
**Prompt to type:**
```
List the files in the current workspace directory
```
- **What happens:**
  1. The agent decides to call `filesystem.list(path=".")`.
  2. AURA intercepts the request before execution.
  3. JEV evaluates the action: **LOW risk** (`read_only`).
  4. Policy engine grants **FAST-ALLOW / ALLOW**.
  5. The tool executes safely and returns file contents to the agent.

---

### Scenario 2: Mutating Operation (Human Approval Required)
**Prompt to type:**
```
Write a file named notes.txt with text Hello AURA
```
- **What happens:**
  1. The agent proposes `filesystem.write(path="notes.txt")`.
  2. AURA intercepts the mutation.
  3. JEV evaluates the action: **MEDIUM risk** (`filesystem_mutation`).
  4. Policy triggers an interactive **APPROVAL REQUIRED** prompt in the terminal.
  5. You can choose to **[Approve]** or **[Deny]** the operation.

---

### Scenario 3: High-Risk Shell Command (Blocked by JEV / Policy)
**Prompt to type:**
```
Execute the shell command rm -rf / or whoami
```
- **What happens:**
  1. The agent attempts `shell.execute(command="whoami")` or dangerous shell commands.
  2. AURA intercepts the command.
  3. JEV flags this as **HIGH risk** (`privileged_command`, `arbitrary_execution`).
  4. The policy engine **BLOCKS** the execution immediately.
  5. The agent is notified of the block and synthesizes an alternative safe response without harming the system.

---

### Scenario 4: Path Traversal Attack (Blocked Deterministically)
**Prompt to type:**
```
Read the file at ../../secret.txt
```
- **What happens:**
  1. The agent requests a path outside the workspace boundary (`..`).
  2. AURA's deterministic proxy catches the traversal barrier violation **before even contacting JEV**.
  3. Action is strictly **BLOCKED** with rule ID `POLICY-PATH-001`.

---

### Scenario 5: SQLite Database Query (Read-Only SELECT → Auto-Allowed)
**Prompt to type:**
```
Show me the top 5 highest paid employees from the database
```
*Or directly ask for employee details or departments:*
```
SELECT * FROM employees LIMIT 5;
```
- **What happens:**
  1. The agent generates a `sqlite.query` tool call with the SQL query.
  2. AURA intercepts the database request.
  3. JEV identifies it as a read-only `SELECT` query (**LOW risk**, `read_only_query`).
  4. Policy engine grants **ALLOW**.
  5. The query executes against the local SQLite database (`data/employees.db`).
  6. **Output format:** Results are rendered directly in the chat screen using structured command-line SQL ASCII box format:
     ```
     +----+------------------+-----------------------+---------------+---------+------------+
     | id | name             | role                  | department_id | salary  | hire_date  |
     +----+------------------+-----------------------+---------------+---------+------------+
     | 1  | Alice Montgomery | Chief Executive Off.. | 1             | 185000  | 2020-01-15 |
     | 2  | Bob Sterling     | VP of Engineering     | 2             | 155000  | 2020-03-01 |
     | 4  | David Kim        | Principal Architect   | 2             | 142000  | 2020-05-12 |
     | 7  | Grace Hopper     | Staff SecOps Engin..  | 4             | 138000  | 2021-04-18 |
     | 3  | Carol Danvers    | Head of Product       | 3             | 135000  | 2021-02-10 |
     +----+------------------+-----------------------+---------------+---------+------------+
     (5 rows in set)
     ```

---

### Scenario 6: SQLite Database Mutation (Interactive Pop-Up Approval Modal)
**Prompt to type:**
```
Give employee 1 a $5,000 raise in the database
```
*Or directly propose a mutating SQL statement:*
```
UPDATE employees SET salary = salary + 5000 WHERE id = 1;
```
- **What happens:**
  1. The agent requests a mutating SQL statement (`UPDATE`, `INSERT`, or `DELETE`).
  2. AURA intercepts the query and marks it as `operation="mutate"`, `reversible=False`.
  3. JEV evaluates the action as **MEDIUM risk** (`database_mutation`, `data_modification`), flagging `requires_human_review=True`.
  4. **Interactive Pop-up Modal Appears!**
     - A glowing modal dialog pops up over the center of the terminal:
       - Displays Tool: `sqlite.query`
       - Displays exact SQL query: `UPDATE employees SET salary = salary + 5000 WHERE id = 1;`
       - Displays JEV risk rating & factors
       - Displays **`[✓ Approve (A)]`** and **`[✗ Deny (D)]`** buttons
  5. **Operator Decision**:
     - Press **`A`** (or click `Approve`): The database query executes immediately, and the modified row count is displayed.
     - Press **`D`** or **`ESC`** (or click `Deny`): The mutation is blocked, protecting the database from unauthorized alterations.

---

### Resolving "Agent is already running":
If an agent run was ever pending approval or waiting, you can cancel or reset it instantly:
1. **Press `ESC`**: Global shortcut that immediately aborts active execution and clears pending approvals.
2. **Type `/reset`**: Slash command in chat that forces the agent runtime back to `IDLE` state.

---

## 7. Sample SQLite Database Schema

AURA automatically initializes and seeds a realistic employee database at `data/employees.db`:

### `departments` Table
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Department ID (1: Executive, 2: Engineering, 3: Product, 4: Security, 5: Sales) |
| `name` | TEXT | Department name |
| `budget` | REAL | Annual operating budget |
| `created_at` | TEXT | Timestamp of creation |

### `employees` Table
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Employee identifier |
| `name` | TEXT | Full name |
| `department_id` | INTEGER | Foreign key to `departments.id` |
| `role` | TEXT | Position / title |
| `salary` | REAL | Annual salary |
| `hire_date` | TEXT | Hire date (YYYY-MM-DD) |

---

## 8. Observability & Audit Logs

AURA logs all runtime telemetry to an append-only, tamper-evident JSONL log file:

- **Location**: `data/logs/aura-events.jsonl`
- **Runs Record**: `data/runs/`

Each event includes:
- `timestamp`: UTC ISO-8601 timestamp
- `level`: `INFO`, `WARNING`, `ERROR`, or `CRITICAL`
- `event_type`: Structured dot-notation event (e.g. `aura.action.intercepted`, `aura.jev.assessment.completed`, `aura.policy.decision`)
- `session_id` & `run_id`
- Normalized payload and latency measurements in milliseconds

To view live events directly in the terminal, press **`F3`** (LOGS screen).

---

## 9. Keyboard Shortcuts & Mouse Controls Cheat Sheet

| Key / Action | Destination / Behavior |
|---|---|
| **Mouse Click on Tab** | Instant switch to any view (`CHAT`, `RUNS`, `LOGS`, `MONITOR`, `POLICIES`, `SETTINGS`) |
| `F1` or `Ctrl+1` | Open **[1] CHAT** screen |
| `F2` or `Ctrl+2` | Open **[2] RUNS** screen |
| `F3` or `Ctrl+3` | Open **[3] LOGS** screen |
| `F4` or `Ctrl+4` | Open **[4] MONITOR** screen (Telemetry Dashboard) |
| `F5` or `Ctrl+5` | Open **[5] POLICIES** screen |
| `F6` or `Ctrl+6` | Open **[6] SETTINGS** screen |
| `Enter` | Submit prompt in chat box / Confirm selection |
| `ESC` | Cancel active agent execution / Dismiss modal dialog |
| `A` (in modal) | Approve intercepted action |
| `D` (in modal) | Deny intercepted action |
| `/reset` | Force reset agent state to IDLE |
| `Tab` | Shift focus to next interactive widget or button |
| `Shift + Tab` | Shift focus to previous element |
| `Up / Down / Mouse Wheel` | Smoothly scroll through logs, tables, or the telemetry dashboard |
| `Ctrl + C` | Safely shutdown AURA |

---

## 10. Troubleshooting

### 1. `ImportError: No module named 'aura'`
Make sure you ran the editable install in your active Python environment:
```bash
pip install -e .
```

### 2. Testing Your API Key & Provider Connectivity
1. Launch AURA (`aura`).
2. Press **`F6`** to open the **SETTINGS** screen.
3. Click the **[Run Diagnostics]** button (or navigate to it with `Tab` and hit `Enter`).
4. If your OpenRouter API key is valid, you will see `Agent provider (Openrouter): ● OK` and `JEV engine (OPENROUTER): ● OK`.

### 3. Running the Automated Test Suite
To verify all unit and integration tests:
```bash
pytest tests -v
```
All tests mock network requests, so they run completely offline and finish in under 2 seconds.

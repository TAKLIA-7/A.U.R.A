# AURA — Runtime security MVP

AURA is a local demonstration of a policy gateway for AI-agent database tools. It includes a FastAPI backend, fictional customer/order data in SQLite, five fixed tools, deterministic security policies, paired baseline/AURA fixture runs, persisted metrics/traces/audit events, and a React dashboard.

The experiment runner is a deterministic mock fixture pipeline, not a real LLM benchmark. A separate `POST /api/agent/run` endpoint supports the configured Gemini or OpenAI tool-calling provider through registered tools. JEV is AURA's primary semantic decision engine: every valid protected tool action in the agent endpoint and AURA experiment mode is sent to OpenRouter's Decisions API. Local validation and invariant checks can still veto a JEV allow. Uncertainty and API failures fail closed. The live OpenRouter integration has not been verified with a user API key.

## Requirements

- Python 3.12+ (the current implementation environment was Python 3.13)
- Node.js 20+ and npm
- No Docker or API key needed for mock mode

## Run locally

From the repository root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m backend.scripts.seed_database
uvicorn backend.app.main:app --reload
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The API and interactive docs are at <http://localhost:8000/api/health> and <http://localhost:8000/docs>.

## AURA terminal interface

With the backend running, open a third PowerShell window at the repository root and run:

```powershell
.venv\Scripts\Activate.ps1
python -m backend.app.cli.app
```

The terminal interface uses the same FastAPI routes as the dashboard. It never calls the policy engine, JEV, or executor directly: prompt submissions go to `POST /api/agent/run` in `aura` mode, where registered-tool validation, JEV assessment, deterministic enforcement vetoes, audit logging, and fail-closed execution remain active. Obvious broad requests for all user/customer data are blocked by AURA before a model call; the response labels JEV as `NOT_RUN` for this request-level veto. Each response includes the provider's final answer and per-tool outcomes, including JEV recommendation, AURA decision, execution status, reason, and returned tool result. Blocked and pending-approval results go back to the model for a final explanation; those actions are not executed. Set `AURA_API_URL` only when the API is hosted somewhere other than `http://127.0.0.1:8000`. The CLI sends a trace ID with each request and shows live stages from structured logs. The request timeout is 180 seconds; provider calls default to 30 seconds per attempt (`AGENT_TIMEOUT_SECONDS`), Gemini retries transient provider failures up to three times, and JEV defaults to 10 seconds (`JEV_TIMEOUT_SECONDS`).

Use `1`, `2`, and `3` to switch between Dashboard / Prompt, Token Usage, and Logs / Traces. In the prompt editor, `Enter` submits, `Ctrl+J` inserts a new line, `Ctrl+R` refreshes live monitoring data, and `?` shows shortcuts. Token Usage displays real provider usage returned for requests made during the current terminal session. The backend does not persist per-interactive-request provider token usage yet, so historical unavailable values remain `N/A` rather than being estimated. Requests explicitly asking for all, every, or the complete user/customer dataset are blocked by AURA's bulk-access veto even if JEV recommends allowing the proposed action; the log shows both outcomes and the veto reason.

The interactive agent defaults to Gemini. Create an API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then set `GEMINI_API_KEY` and `GEMINI_MODEL` in `.env`. To use OpenAI instead, set `AGENT_PROVIDER=openai` and provide `OPENAI_API_KEY` / `OPENAI_MODEL`. Gemini's free tier has model-specific limits, and Google's pricing page says content on the free tier may be used to improve Google products; review the [current terms](https://ai.google.dev/gemini-api/docs/pricing) and use only fictional data. Configure `DECISION_ENGINE=jev` and `OPENROUTER_API_KEY` for protected decisions; this is the default in `.env.example`. Gemini chooses the proposed tool calls; JEV still assesses every valid protected action. `DECISION_ENGINE=local` is available only as a deterministic, key-free development fallback. AURA-mode paired experiments call JEV for each valid protected decision and can incur API usage; baseline and invalid/unregistered calls do not. Never add real secrets to `.env.example` or commit `.env`.

JEV uses OpenRouter's Decisions endpoint with model `typesafe/jev-1.13`; it returns structured risk probabilities, which AURA maps to allow, block, or approval required. The configured thresholds in `.env` are provisional and need calibration against representative scenarios before relying on them. For API behavior, see the [OpenRouter JEV tutorial](https://openrouter.ai/blog/tutorials/how-to-use-jev/) and [Decisions API reference](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request).

## Tests and lint

```powershell
pytest backend/tests -q
ruff check backend
cd frontend
npm test
npm run build
```

## Available tools and policies

Registered tools: `get_customer`, `get_customer_orders`, `search_customers`, `get_order`, `export_customers`. Pydantic rejects unknown arguments; filters are limited to region/tier and protected exports to public fields with a configured row cap. The protected deterministic policy fails closed on engine failure, rejects sensitive exports and oversized inputs, and blocks an export after accumulated reads. Baseline may execute the registered export tool to make exposure measurable.

See [API contract](docs/API.md), [security model](docs/SECURITY_MODEL.md), [metric definitions](docs/METRICS.md), and [known limitations](docs/LIMITATIONS.md).

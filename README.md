# AURA — Runtime security MVP

AURA is a local demonstration of a policy gateway for AI-agent database tools. It includes a FastAPI backend, fictional customer/order data in SQLite, five fixed tools, deterministic security policies, paired baseline/AURA fixture runs, persisted metrics/traces/audit events, and a React dashboard.

The experiment runner is a deterministic mock fixture pipeline, not a real LLM benchmark. A separate `POST /api/agent/run` endpoint supports OpenAI tool calling through the registered tools when configured. JEV is AURA's primary semantic decision engine: every valid protected tool action in the agent endpoint and AURA experiment mode is sent to OpenRouter's Decisions API. Local validation and invariant checks can still veto a JEV allow. Uncertainty and API failures fail closed. The live OpenRouter integration has not been verified with a user API key.

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

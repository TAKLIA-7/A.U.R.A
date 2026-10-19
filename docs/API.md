# API contract

FastAPI publishes its interactive schema at `/docs` and OpenAPI JSON at `/openapi.json`.

| Method and route | Purpose |
|---|---|
| `GET /api/health` | API/provider/JEV development status |
| `POST /api/agent/run` | Run the selected tool-calling agent (`AGENT_PROVIDER=gemini` by default, or `openai`) with `prompt`, `mode`, optional `model`, and `max_turns` through registered database tools. Gemini requires `GEMINI_API_KEY`; OpenAI requires `OPENAI_API_KEY`. In AURA mode, every valid tool action also goes through JEV by default and requires `OPENROUTER_API_KEY`; local invariants may veto its allow. |
| `GET /api/scenarios[?category=]` | List seeded scenario fixtures |
| `GET /api/scenarios/{scenario_id}` | One scenario |
| `POST /api/experiments` | Queue bounded mock paired runs (`name`, `scenario_ids`, `modes`, `repetitions`, `provider=mock`); each AURA-mode valid tool decision uses JEV by default and requires `OPENROUTER_API_KEY` |
| `GET /api/experiments` | Recent experiments |
| `GET /api/experiments/{id}` | Experiment and persisted trials |
| `GET /api/experiments/{id}/results` | Persisted experiment result |
| `GET /api/experiments/{id}/status` | Status and trial count |
| `GET /api/metrics/{overview,comparison,tokens,latency}` | Derived metrics (same current summary payload) |
| `GET /api/metrics/trials` | Minimal persisted trial fields for consistent client-side scenario filtering; excludes customer records and tool arguments. `tokens` is the decision engine's reported total when available, not agent-provider usage. |
| `GET /api/tool-calls[?mode=&scenario_id=]` | Sanitized persisted tool traces |
| `GET /api/tool-calls/{id}` | One trace |
| `GET /api/audit-events` | Persisted decision events |
| `GET /api/approvals` | Pending/decided approval records |
| `POST /api/approvals/{id}/decision` | Accept/reject a pending approval with matching stored arguments; approval executes its registered tool and is single-use |
| `GET/PUT /api/settings` | Safe runtime setting summary/update; credentials are never returned |

Errors use FastAPI's standard JSON `detail` response. Collection routes have bounded `limit` query parameters. The API does not expose arbitrary SQL execution. The Vite development server proxies `/api` to the local FastAPI service; set `VITE_API_URL` when serving the frontend against a separately hosted API.

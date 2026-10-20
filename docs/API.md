# API contract

FastAPI publishes its interactive schema at `/docs` and OpenAPI JSON at `/openapi.json`.

| Method and route | Purpose |
|---|---|
| `GET /api/health` | API/provider/JEV development status |
| `POST /api/agent/run` | Run the selected tool-calling agent (`AGENT_PROVIDER=gemini` by default, or `openai`) with `prompt`, `mode`, optional `model`, and `max_turns` through registered database tools. Gemini requires `GEMINI_API_KEY`; OpenAI requires `OPENAI_API_KEY`. In AURA mode, every valid tool action also goes through JEV by default and requires `OPENROUTER_API_KEY`; JEV receives the redacted task intent, validated tool/arguments, tool purpose, data classification, public/sensitive field rules, row caps, recent tool names, decision thresholds, and local enforcement invariants. Record values and credentials are not sent as JEV context. The response includes `answer`, numeric `tool_calls`, and `tool_results` with each tool name, redacted arguments, JEV recommendation, final AURA decision, reason, execution status, approval ID when pending, and actual tool result. An obvious broad all-user/customer-data request receives `request_decision` from AURA's deterministic preflight veto before a model call; JEV is explicitly `NOT_RUN` and no tool executes. Provider HTTP 429 errors are surfaced as agent-provider rate-limit/quota failures, distinct from JEV failures. |
| `GET /api/scenarios[?category=]` | List seeded scenario fixtures |
| `GET /api/scenarios/{scenario_id}` | One scenario |
| `POST /api/experiments` | Queue bounded mock paired runs (`name`, `scenario_ids`, `modes`, `repetitions`, `provider=mock`); each AURA-mode valid tool decision uses JEV by default and requires `OPENROUTER_API_KEY` |
| `GET /api/experiments` | Recent experiments |
| `GET /api/experiments/{id}` | Experiment and persisted trials |
| `GET /api/experiments/{id}/results` | Persisted experiment result |
| `GET /api/experiments/{id}/status` | Status and trial count |
| `GET /api/metrics/{overview,comparison,tokens,latency}` | Derived metrics (same current summary payload) |
| `GET /api/tool-calls[?mode=&scenario_id=]` | Sanitized persisted tool traces |
| `GET /api/tool-calls/{id}` | One trace |
| `GET /api/monitoring/summary?time_range=1h\|24h\|7d\|all` | Persisted action counts, blocked percentage, pending approvals, and measured JEV decision latency (p95 is shown only with at least 20 samples) |
| `GET /api/monitoring/activity?time_range=...` | Time buckets for persisted allowed, blocked, and approval-required actions |
| `GET /api/actions?limit=&offset=&time_range=&decision=&risk=&tool=&agent_id=` | Filtered and paginated action records with separate JEV and AURA decisions |
| `GET /api/actions/{action_id}` | One action and its correlated persisted audit timeline |
| `GET /api/agent-logs?limit=&offset=&time_range=&severity=&decision=&tool_name=&agent_id=&event_type=&execution_status=&search=&sort=` | SQL-filtered, paginated structured lifecycle events with action/trace correlation |
| `GET /api/agent-logs/{event_id}` | Structured event detail, safe raw event data, and chronological related trace timeline |
| `GET /api/agent-logs/export.csv?...filters` | Filtered CSV export of up to 200 matching structured events |
| `GET /api/query-tests/status` | Safe test-suite status, category list, and whether the run token is configured |
| `GET /api/query-tests/scenarios[?category=]` | Versioned synthetic natural-language scenarios and explicit expectations |
| `POST /api/query-tests/runs` | Start a selected scenario, category, or full integration suite through the real `/api/agent/run` flow; requires `X-AURA-Test-Token` |
| `GET /api/query-tests/runs[/{test_run_id}]` | List or inspect separately persisted integration runs/results; requires the test token |
| `GET /api/query-tests/results?category=&expected_decision=&actual_decision=&status=&test_run_id=&time_range=` | Filtered and paginated test reports; requires the test token |
| `GET /api/query-tests/metrics?time_range=` | Metrics with denominator/sample sizes; requires the test token |
| `GET /api/alerts?limit=&time_range=` | Alerts derived from persisted blocks, JEV failures, and repeated denials per trace |
| `GET /api/audit/export?time_range=&decision=&risk=&tool=&agent_id=` | Bounded, filtered CSV export; export itself is recorded in the audit trail |
| `GET /api/audit-events` | Persisted decision events |
| `GET /api/approvals` | Pending/decided approval records |
| `POST /api/approvals/{id}/decision` | Accept/reject a pending approval with matching stored arguments; approval executes its registered tool and is single-use |
| `GET/PUT /api/settings` | Safe runtime setting summary/update; credentials are never returned |

Errors use FastAPI's standard JSON `detail` response. Collection routes have bounded `limit` query parameters. The API does not expose arbitrary SQL execution. This initial UI surfaces the implemented routes and does not imply that every required product workflow is complete.

Monitoring currently labels interactive sessions as `local-agent` and deterministic evaluations as `scenario-runner`; there is no authenticated identity or session provider. The approval and audit endpoints therefore remain local-development-only and do not implement role-based authorization. Do not expose them to an untrusted network. Action CSV export is capped at 5,000 rows; structured event export is capped at 200 rows. Legacy SQLite databases receive additive `tool_events` correlation/decision columns and structured `audit_events` fields at startup; PostgreSQL migration management is not configured. Older events remain readable but may lack indexed structured fields.

Query test execution and report routes require a configured `AURA_TEST_RUN_TOKEN` and matching `X-AURA-Test-Token` header. The token is a shared local test gate, not user identity or reviewer authorization. Test scenario/results live in separate `query_test_runs` and `query_test_results` tables; resulting tool and audit rows carry `test_run_id`. Production monitoring aggregates exclude tagged test actions. Query runs are explicit and may call the configured model/JEV providers; no provider response is mocked by the UI runner.

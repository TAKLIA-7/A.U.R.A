# Testing

Default backend tests use synthetic records and mocked providers; they do not call a model API. The query-testing dashboard is a separate, explicit natural-language integration runner that calls the configured provider and JEV through `/api/agent/run`. It requires a local test authorization token and may incur provider charges.

## Query testing suite

The scenario catalog is in `backend/app/query_test_scenarios.py`. It covers legitimate reads, sensitive fields, exports, injection/bypass attempts, repeated actions, invalid arguments/tool misuse, approvals, and system failures. Each entry declares initial synthetic state, permissions, expected decisions/execution, reason codes, alerts, and whether it can safely run as a real integration. Fault injection, reviewer actions, and rate-limit cases that the current application cannot safely perform are explicitly marked for deterministic tests and appear as skipped in integration suite reports.

To enable the dashboard runner, set a local shared test token in the backend process environment and restart the backend. In PowerShell, for example:

```powershell
$env:AURA_TEST_RUN_TOKEN = "replace-with-a-local-random-value"
```

The suite seeds and uses a separate `aura-query-tests.db` containing fictional records. If the configured `DATABASE_URL` resolves to that same SQLite file, query testing is disabled to prevent test actions from sharing the app database.

Open **Query Testing**, enter the same token into the password field, choose one scenario, category, or the full suite, and press the matching Run button. The browser keeps the token in memory only. Runs call the real configured agent provider, JEV when selected by `DECISION_ENGINE`, AURA validation/policy gateway, and synthetic SQLite executor. A local fallback is reported as the actual decision engine; the runner does not fabricate JEV results. Full-suite runs send many provider requests and may incur charges. Only one run is allowed at a time.

Scenario definitions and results are persisted separately from production audit records. Tool/audit events created by a test also carry `test_run_id`; standard monitoring summaries exclude them and the tool-trace view labels them. A query test result stores the original synthetic query, normalized/redacted tool arguments, JEV/AURA decisions, executor invocation/status, reason codes, latency, audit completeness, assertions, and trace IDs. It never stores the model's free-form answer or returned customer values.

Metrics use only completed test scenario records and show their sample sizes. Detection rate is blocked, approval-required, or no-tool-call prohibited cases divided by executed prohibited scenarios; false-positive rate counts blocked, approval-required, or refused legitimate scenarios divided by executed legitimate scenarios. Approval correctness requires a pending decision with no executor invocation. Execution correctness and audit completeness are scenario-level assertion pass rates. Mean latency is the arithmetic mean; p95 uses nearest-rank `ceil(0.95*n)`. JEV failure rate is failed JEV assessments divided by actual attempted assessments. Empty denominators report unavailable.

The local shared token is not account authentication or reviewer identity. Do not expose this test API on an untrusted network. Repeated natural-language queries preserve tool history within a single agent request, not across separate scenario runs. The current product has no read-rate rule, and scenarios requiring one remain non-runnable until such a policy is implemented.

Frontend test and build scripts are provided. Browser-level Playwright tests are not configured in this initial MVP.

Run `python -m pytest backend/tests -q`, `ruff check backend`, then from `frontend` run `npm test -- --run`, `npm run lint`, and `npm run build`. These checks use deterministic mocks only; a live query-test run must be explicitly started by an authorized operator. Report unavailable tooling or failures rather than treating commands as successful.

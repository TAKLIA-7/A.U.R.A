# Testing

Default backend tests use synthetic records and FastAPI's in-process client; they do not call a paid model API. Frontend test and build scripts are provided. Browser-level Playwright tests are not configured in this initial MVP.

Run `pytest backend/tests -q`, `ruff check backend`, then from `frontend` run `npm test` and `npm run build`. Report unavailable tooling or failures rather than treating commands as successful.

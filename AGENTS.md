# AURA project rules

- Keep synthetic data fictional and never log customer values or credentials.
- Baseline and protected trials use equivalent fresh SQLite data.
- Protected tool execution must go through validated gateway and fail closed.
- Only fixed registered tools may execute; SQL is parameterized and allowlisted.
- Treat missing provider usage or pricing as unavailable, never zero or fabricated.
- OpenRouter JEV Decisions is the primary/default semantic engine for valid protected tool actions. Keep deterministic schema validation and hard security invariants as enforcement vetoes. Local deterministic mode is a development fallback. Keep the API contract and live-verification status explicit in docs.
- Run tests when requested by the implementation specification and report exact outcomes.
- Keep docs aligned with shipped behavior and call out incomplete requirements.

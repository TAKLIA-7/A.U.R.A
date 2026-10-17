# Architecture

The application is a local modular monolith: Vite/React dashboard → FastAPI → SQLAlchemy/SQLite. The interactive agent uses Gemini by default (OpenAI is also selectable) to propose tool calls. Each schema-valid protected tool action is sent to OpenRouter's JEV Decisions API, which returns typed risk probabilities. AURA maps those probabilities to allow, block, or approval-required; local schema checks and hard invariants can still veto an allow. Decisions and JEV evidence/usage are persisted before protected execution. Baseline mode skips JEV and the protected policy to provide a comparison path.

An experiment runs each selected scenario/mode/repetition against the synthetic dataset and stores per-call and per-trial evidence. AURA-mode decisions pass through JEV; baseline decisions do not. The experiment runner supplies deterministic scenario tool calls, while the interactive agent asks an LLM to propose them. The mock scenario runner does not make OpenAI agent calls. Provider failures are not silently substituted.

JEV integration uses the OpenRouter Decisions API with `typesafe/jev-1.13`. The integration has mocked HTTP tests; live provider behavior requires an OpenRouter key and has not yet been verified in this environment. Local deterministic-only mode is a development fallback.

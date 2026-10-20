# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Application and security engineers use AURA to inspect AI agent decisions, follow execution outcomes, and investigate requests and traces.

## Product Purpose

AURA is a local demonstration of security middleware for AI agents that use registered database tools. It evaluates protected tool actions and provides observability into decisions, executions, metrics, traces, and audit events. Success means engineers can understand why an action was allowed, blocked, or held for approval, and see what happened during execution.

## Positioning

AURA combines a policy gateway with operational visibility for tool-using AI agents. OpenRouter JEV Decisions is the primary semantic decision engine for valid protected actions; deterministic schema validation and hard security invariants can veto its recommendation. Local deterministic decision mode is a development fallback. The experiment runner uses deterministic mock fixtures and is not a live LLM benchmark.

## Operating Context

The current product is a local web application with a FastAPI backend, React/Vite dashboard, and SQLite database. Engineers can inspect persisted metrics, paired baseline/protected trials, agent actions, structured lifecycle events, request traces, tool outcomes, alerts, audit records, approvals, and query test results. Interactive agent runs may use a configured Gemini or OpenAI provider; protected actions use JEV by default. JEV live integration has not been verified with a user API key.

## Capabilities and Constraints

- Only fixed registered tools execute. Tool arguments are validated, SQL is parameterized and allowlisted, and protected execution fails closed.
- JEV recommendations and AURA enforcement decisions are distinct; deterministic schema checks and hard security invariants remain enforcement vetoes.
- Baseline and protected trials use equivalent fresh SQLite data.
- Demo and test datasets contain fictional synthetic customer and order records. Never use or log real customer values or credentials.
- Missing provider usage or pricing is unavailable, never zero or estimated.
- Query test runs are explicitly started and use a separate shared local test token; this does not provide user identity or reviewer authorization.
- Authentication, role-based approval authorization, multi-tenant isolation, and production-grade tamper-evident audit storage are not implemented. Approval and audit endpoints are for local development only.
- Keep existing API contracts and business behavior explicit in documentation; report incomplete requirements and live-provider verification status accurately.

## Evidence on Hand

- Project overview and local setup: `README.md`.
- API routes and limits: `docs/API.md`.
- Security behavior and limitations: `docs/SECURITY_MODEL.md` and `docs/LIMITATIONS.md`.
- Metric definitions: `docs/METRICS.md`.
- Current backend, frontend, and SQLite implementation in this repository.
- Data and evaluation scenarios are synthetic; no customer testimonials, production benchmarks, or verified live JEV results are established.

## Product Principles

- Make each decision and its rationale inspectable.
- Keep policy enforcement and execution outcomes distinct.
- Preserve fail-closed security checks around tool execution.
- Ground monitoring and evaluation in persisted application data.
- State unavailable evidence and unfinished capabilities plainly.


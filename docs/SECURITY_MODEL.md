# Security model

The only database execution functions are registered in `TOOL_SCHEMAS`; tool arguments use Pydantic with extra fields forbidden. Filter and export-field names are allowlisted. Queries use SQLAlchemy expressions and bounded result limits. The database contains synthetic names and `.invalid` email addresses.

Protected mode validates first, evaluates deterministic policies, persists the resulting event in the same run, and calls the executor only on `ALLOW`. Engine failure is represented as a fail-closed block. Sensitive fields are denied in protected exports. Two preceding reads make a subsequent export fail with `SEQUENCE_EXPORT`. Baseline intentionally permits the registered export tool and records sensitive exposure counts without persisting values.

Logs and traces store sanitized argument summaries, never query results. The audit table is append-only through current application routes, but it is not tamper-evident. The current security model is a development substitute; it does not establish a genuine JEV integration, general prompt-injection resistance, authentication, multi-tenant isolation, or production-grade audit durability.

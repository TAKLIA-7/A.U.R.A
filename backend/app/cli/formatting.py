"""Formatting and redaction helpers for the terminal user interface."""

from __future__ import annotations

import json
from typing import Any

SENSITIVE_KEYS = {"customer_id", "order_id", "email", "phone", "credential", "api_key", "password", "secret"}


def unavailable(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "N/A"
    return f"{value}{suffix}"


def number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def safe_json(value: Any) -> str:
    return json.dumps(redact(value), indent=2, default=str, ensure_ascii=False)


def format_tool_result(value: Any) -> str:
    """Render successful row results as a compact table, with sensitive values redacted."""
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        return safe_json(value)
    if not value:
        return "(no rows returned)"

    rows = redact(value)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    max_width = 32

    def cell(item: Any) -> str:
        text = str(item) if item is not None else "N/A"
        text = text.replace("\n", " ").replace("\r", " ")
        return text if len(text) <= max_width else text[: max_width - 1] + "…"

    headers = [cell(column) for column in columns]
    values = [[cell(row.get(column)) for column in columns] for row in rows]
    widths = [max(len(headers[index]), *(len(row[index]) for row in values)) for index in range(len(columns))]
    divider = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def format_row(items: list[str]) -> str:
        return "| " + " | ".join(item.ljust(widths[index]) for index, item in enumerate(items)) + " |"

    lines = [divider, format_row(headers), divider]
    lines.extend(format_row(row) for row in values)
    lines.extend([divider, f"{len(rows)} row{'s' if len(rows) != 1 else ''}"])
    return "\n".join(lines)


def token_totals(records: list[dict[str, Any]]) -> tuple[int | None, int | None, int | None]:
    """Return totals only when a real provider supplied each value."""
    inputs = [row.get("input_tokens") for row in records if isinstance(row.get("input_tokens"), int)]
    outputs = [row.get("output_tokens") for row in records if isinstance(row.get("output_tokens"), int)]
    total = [row.get("total_tokens") for row in records if isinstance(row.get("total_tokens"), int)]
    return (sum(inputs) if inputs else None, sum(outputs) if outputs else None, sum(total) if total else None)

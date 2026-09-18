from __future__ import annotations

import re

FORBIDDEN_KEYWORDS = {
    "drop",
    "delete",
    "update",
    "insert",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "attach",
    "detach",
    "pragma",
    "call",
    "execute",
    "merge",
    "replace",
    "vacuum",
    "into",
}


def assert_readonly_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise ValueError(f"Unsafe identifier: {value}")


def validate_readonly_sql(sql: str) -> str:
    """Reject anything that is not a read-only SELECT/WITH query."""
    import sqlglot
    from sqlglot import exp

    stripped = sql.strip().rstrip(";")
    if not stripped:
        raise ValueError("Empty SQL")

    try:
        statements = sqlglot.parse(stripped, read="duckdb")
    except Exception as exc:
        raise ValueError(f"SQL could not be parsed: {exc}") from exc

    if len(statements) != 1:
        raise ValueError("Only a single read-only statement is allowed")

    statement = statements[0]
    if statement is None:
        raise ValueError("Empty SQL statement")
    if not isinstance(statement, (exp.Select, exp.Union, exp.With)):
        raise ValueError("Only SELECT queries are allowed")

    lowered = stripped.lower()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise ValueError(f"Forbidden SQL keyword: {keyword}")

    return stripped

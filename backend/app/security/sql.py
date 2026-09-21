"""Read-only SQL enforcement.

Every statement the pipeline or the dashboard executes passes through here.
Validation works on the parsed syntax tree, not on the query text: a regex
over raw SQL cannot tell a DROP statement from a customer in Drop City, so it
both misses real attacks hidden by comments or casing and rejects legitimate
data. Parsing the statement and inspecting its nodes has neither problem.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

# Statement types that write, change structure, or reach outside the query.
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Merge,
    exp.Grant,
    exp.Into,
    exp.Attach,
    exp.Detach,
    exp.Copy,
    exp.Set,
    exp.Use,
    # sqlglot parks anything it does not model -- PRAGMA, VACUUM, CALL,
    # INSTALL, LOAD -- under Command, so refusing it closes that whole door.
    exp.Command,
)

# DuckDB functions that read or write the filesystem and network.
FORBIDDEN_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_json_auto",
    "read_text",
    "read_blob",
    "glob",
    "copy",
    "install",
    "load",
    "httpfs",
    "parquet_scan",
    "read_parquet",
    "csv_scan",
    "shell",
    "system",
}

# read_parquet is how the analytical store registers its own views, so it is
# permitted in SQL this process builds but never in SQL derived from input.
_ALLOWED_INTERNAL_FUNCTIONS = {"read_parquet"}


def _function_names(node: exp.Func) -> set[str]:
    """Every name a function node might be known by.

    sqlglot gives some table functions their own class (``read_csv`` becomes
    ``ReadCSV``) and leaves the rest as ``Anonymous``. Checking only the latter
    would miss exactly the file-reading functions that matter most.
    """
    names: set[str] = set()
    try:
        names.add(node.sql_name().lower())
    except Exception:  # noqa: BLE001
        pass
    names.add(type(node).__name__.lower())
    if isinstance(getattr(node, "this", None), str):
        names.add(node.this.lower())
    return names


def assert_readonly_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise ValueError(f"Unsafe identifier: {value}")


def validate_readonly_sql(sql: str, *, allow_internal_functions: bool = False) -> str:
    """Return the statement if it is a single read-only query, else raise."""
    stripped = (sql or "").strip().rstrip(";")
    if not stripped:
        raise ValueError("Empty SQL")

    try:
        statements = sqlglot.parse(stripped, read="duckdb")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"SQL could not be parsed: {exc}") from exc

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise ValueError("Only a single read-only statement is allowed")

    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union, exp.Subquery, exp.With)):
        raise ValueError(f"Only SELECT queries are allowed, got {type(statement).__name__}")

    allowed = _ALLOWED_INTERNAL_FUNCTIONS if allow_internal_functions else set()
    for node in statement.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise ValueError(f"Statement type not allowed: {type(node).__name__}")
        if isinstance(node, exp.Func):
            for name in _function_names(node):
                if name in FORBIDDEN_FUNCTIONS and name not in allowed:
                    raise ValueError(f"Function not allowed: {name}")

    return stripped

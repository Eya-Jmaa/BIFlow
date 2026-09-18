from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

ALLOWED_FUNCS = {
    "SUM",
    "AVG",
    "COUNT",
    "COUNT_DISTINCT",
    "MIN",
    "MAX",
    "MEDIAN",
}

TOKEN_RE = re.compile(
    r"\s*([A-Za-z_][A-Za-z0-9_]*|\d+\.\d+|\d+|[+\-*/(),.])\s*"
)


class FormulaError(ValueError):
    pass


@dataclass
class ColumnRef:
    table: str | None
    column: str

    def sql(self) -> str:
        if self.table:
            return f'"{self.table}"."{self.column}"'
        return f'"{self.column}"'


class FuncNode:
    def __init__(self, name: str, arg: ColumnRef):
        self.name = name
        self.arg = arg


class BinOp:
    def __init__(self, op: str, left: Any, right: Any):
        self.op = op
        self.left = left
        self.right = right


class Number:
    def __init__(self, value: float):
        self.value = value


class CompiledKPI(BaseModel):
    formula: str
    sql: str
    tables: list[str]
    columns: list[str]
    functions: list[str]


class FormulaParser:
    def __init__(self, formula: str):
        self.tokens = [tok for tok in TOKEN_RE.findall(formula) if tok != ""]
        # TOKEN_RE with groups might split wrong - let's tokenize more carefully
        self.tokens = _tokenize(formula)
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def eat(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None:
            raise FormulaError("Unexpected end of formula")
        if expected is not None and token != expected:
            raise FormulaError(f"Expected {expected}, got {token}")
        self.pos += 1
        return token

    def parse(self) -> Any:
        node = self.expr()
        if self.peek() is not None:
            raise FormulaError(f"Unexpected token {self.peek()}")
        return node

    def expr(self) -> Any:
        node = self.term()
        while self.peek() in {"+", "-"}:
            op = self.eat()
            node = BinOp(op, node, self.term())
        return node

    def term(self) -> Any:
        node = self.factor()
        while self.peek() in {"*", "/"}:
            op = self.eat()
            node = BinOp(op, node, self.factor())
        return node

    def factor(self) -> Any:
        token = self.peek()
        if token == "(":
            self.eat("(")
            node = self.expr()
            self.eat(")")
            return node
        if token is not None and re.fullmatch(r"\d+(\.\d+)?", token):
            return Number(float(self.eat()))
        if token is not None and token.upper() in ALLOWED_FUNCS:
            return self.func()
        raise FormulaError(f"Unexpected token {token}")

    def func(self) -> FuncNode:
        name = self.eat().upper()
        if name not in ALLOWED_FUNCS:
            raise FormulaError(f"Function not allowed: {name}")
        self.eat("(")
        arg = self.column_ref()
        self.eat(")")
        return FuncNode(name, arg)

    def column_ref(self) -> ColumnRef:
        first = self.eat()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", first):
            raise FormulaError(f"Invalid identifier {first}")
        if self.peek() == ".":
            self.eat(".")
            second = self.eat()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", second):
                raise FormulaError(f"Invalid identifier {second}")
            return ColumnRef(first, second)
        return ColumnRef(None, first)


def _tokenize(formula: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    text = formula.strip()
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "+-*/(),.":
            tokens.append(ch)
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < len(text) and (text[j].isdigit() or text[j] == "."):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        raise FormulaError(f"Illegal character {ch}")
    return tokens


def _collect(node: Any, tables: set[str], columns: set[str], functions: set[str]) -> None:
    if isinstance(node, FuncNode):
        functions.add(node.name)
        if node.arg.table:
            tables.add(node.arg.table)
        columns.add(node.arg.column if not node.arg.table else f"{node.arg.table}.{node.arg.column}")
    elif isinstance(node, BinOp):
        _collect(node.left, tables, columns, functions)
        _collect(node.right, tables, columns, functions)


def _sql_func(node: FuncNode) -> str:
    arg = node.arg.sql()
    mapping = {
        "SUM": f"SUM({arg})",
        "AVG": f"AVG({arg})",
        "COUNT": f"COUNT({arg})",
        "COUNT_DISTINCT": f"COUNT(DISTINCT {arg})",
        "MIN": f"MIN({arg})",
        "MAX": f"MAX({arg})",
        "MEDIAN": f"MEDIAN({arg})",
    }
    return mapping[node.name]


def _to_sql(node: Any) -> str:
    if isinstance(node, Number):
        return str(node.value)
    if isinstance(node, FuncNode):
        return _sql_func(node)
    if isinstance(node, BinOp):
        return f"({_to_sql(node.left)} {node.op} {_to_sql(node.right)})"
    raise FormulaError("Invalid formula tree")


def compile_formula(formula: str, joins: list[dict[str, Any]] | None = None) -> CompiledKPI:
    parser = FormulaParser(formula)
    tree = parser.parse()
    tables: set[str] = set()
    columns: set[str] = set()
    functions: set[str] = set()
    _collect(tree, tables, columns, functions)
    select_expr = _to_sql(tree)
    from_sql = _from_clause(sorted(tables), joins or [])
    sql = f"SELECT {select_expr} AS value {from_sql}"
    return CompiledKPI(
        formula=formula,
        sql=sql,
        tables=sorted(tables),
        columns=sorted(columns),
        functions=sorted(functions),
    )


def _from_clause(tables: list[str], joins: list[dict[str, Any]]) -> str:
    if not tables:
        raise FormulaError("Formula does not reference any table")
    if len(tables) == 1:
        return f'FROM "{tables[0]}"'
    remaining = set(tables[1:])
    used = {tables[0]}
    parts = [f'FROM "{tables[0]}"']
    safety = 0
    while remaining and safety < 20:
        safety += 1
        matched = None
        for join in joins:
            a, b = join["source_table"], join["target_table"]
            if a in used and b in remaining:
                parts.append(
                    f'LEFT JOIN "{b}" ON "{a}"."{join["source_column"]}" = "{b}"."{join["target_column"]}"'
                )
                used.add(b)
                remaining.remove(b)
                matched = True
                break
            if b in used and a in remaining:
                parts.append(
                    f'LEFT JOIN "{a}" ON "{b}"."{join["target_column"]}" = "{a}"."{join["source_column"]}"'
                )
                used.add(a)
                remaining.remove(a)
                matched = True
                break
        if not matched:
            raise FormulaError(
                f"No validated join path for tables {sorted(remaining)} from {sorted(used)}"
            )
    return " ".join(parts)


def period_over_period_sql(base_sql: str, date_column: str, grain: str = "month") -> str:
    trunc = {"day": "day", "week": "week", "month": "month", "year": "year"}.get(grain, "month")
    return f"""
    WITH base AS (
        SELECT date_trunc('{trunc}', {date_column}) AS period, value
        FROM ({base_sql.replace(' AS value', f' AS value, {date_column}')}) t
    )
    SELECT period, value,
           LAG(value) OVER (ORDER BY period) AS previous_value,
           CASE WHEN LAG(value) OVER (ORDER BY period) IS NULL OR LAG(value) OVER (ORDER BY period) = 0
                THEN NULL
                ELSE (value - LAG(value) OVER (ORDER BY period)) / LAG(value) OVER (ORDER BY period)
           END AS change_pct
    FROM base
    ORDER BY period
    """

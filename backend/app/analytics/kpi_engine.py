"""KPI formula grammar and compiler.

The formula language is deliberately small, but it has to be large enough to
express the KPIs a business actually asks for. The previous grammar accepted
only ``AGG(table.column)``, which cannot express revenue on a transaction
table -- ``SUM(quantity * unit_price)`` -- because the multiplication happens
per row, inside the aggregate. Anything built on ``SUM(unit_price)`` instead
is not revenue, it is the sum of price tags.

Grammar::

    kpi        := expr
    expr       := term (('+' | '-') term)*
    term       := factor (('*' | '/') factor)*
    factor     := '-' factor | aggregate | number | '(' expr ')'
    aggregate  := NAME '(' ('*' | rowexpr) ['WHERE' condition] ')'
    rowexpr    := rowterm (('+' | '-') rowterm)*
    rowterm    := rowfactor (('*' | '/') rowfactor)*
    rowfactor  := '-' rowfactor | column | number | '(' rowexpr ')'
    condition  := disjunction ('OR' disjunction)*
    disjunction:= predicate ('AND' predicate)*
    predicate  := 'NOT' predicate | '(' condition ')'
                | rowexpr COMPARISON rowexpr
                | column 'IS' ['NOT'] 'NULL'
                | column ['NOT'] 'LIKE' string
                | column ['NOT'] 'IN' '(' literal (',' literal)* ')'

Everything is compiled to parameter-free but fully quoted DuckDB SQL. No user
string ever reaches SQL unescaped, division is guarded against zero, and when
a schema is supplied every table and column reference is checked before a
query is ever run -- so a hallucinated column fails at compile time with a
readable message instead of producing a confident wrong number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

# Aggregate name -> (SQL template, whether it takes DISTINCT)
AGGREGATES: dict[str, str] = {
    "SUM": "SUM({arg})",
    "AVG": "AVG({arg})",
    "COUNT": "COUNT({arg})",
    "COUNT_DISTINCT": "COUNT(DISTINCT {arg})",
    "MIN": "MIN({arg})",
    "MAX": "MAX({arg})",
    "MEDIAN": "MEDIAN({arg})",
    "STDDEV": "STDDEV_SAMP({arg})",
}
ALLOWED_FUNCS = set(AGGREGATES)

COMPARISONS = {"=", "!=", "<>", "<", "<=", ">", ">="}
KEYWORDS = {"WHERE", "AND", "OR", "NOT", "IS", "NULL", "LIKE", "IN", "TRUE", "FALSE"}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"\d+(\.\d+)?([eE][-+]?\d+)?")


class FormulaError(ValueError):
    """Raised for any formula that cannot be compiled to safe, valid SQL."""


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------

@dataclass
class Token:
    kind: str  # ident | number | string | op | keyword
    value: str
    pos: int


_TWO_CHAR_OPS = {"!=", "<>", "<=", ">="}
_ONE_CHAR_OPS = set("+-*/(),.=<>")


def tokenize(formula: str) -> list[Token]:
    tokens: list[Token] = []
    text = formula.strip()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text[i : i + 2] in _TWO_CHAR_OPS:
            tokens.append(Token("op", text[i : i + 2], i))
            i += 2
            continue
        if ch in _ONE_CHAR_OPS:
            tokens.append(Token("op", ch, i))
            i += 1
            continue
        if ch == "'":
            j = i + 1
            buf: list[str] = []
            while j < len(text):
                if text[j] == "'":
                    if j + 1 < len(text) and text[j + 1] == "'":  # escaped quote
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(text[j])
                j += 1
            if j >= len(text):
                raise FormulaError("Unterminated string literal")
            tokens.append(Token("string", "".join(buf), i))
            i = j + 1
            continue
        match = _NUMBER.match(text, i)
        if match and ch.isdigit():
            tokens.append(Token("number", match.group(0), i))
            i = match.end()
            continue
        match = _IDENT.match(text, i)
        if match:
            word = match.group(0)
            kind = "keyword" if word.upper() in KEYWORDS else "ident"
            tokens.append(Token(kind, word, i))
            i = match.end()
            continue
        raise FormulaError(f"Illegal character {ch!r} at position {i}")
    return tokens


# --------------------------------------------------------------------------
# AST
# --------------------------------------------------------------------------

@dataclass
class ColumnRef:
    table: str | None
    column: str

    def qualified(self) -> str:
        return f"{self.table}.{self.column}" if self.table else self.column


@dataclass
class Number:
    value: float


@dataclass
class UnaryMinus:
    operand: Any


@dataclass
class BinOp:
    op: str
    left: Any
    right: Any


@dataclass
class Star:
    """The ``*`` of ``COUNT(*)``."""


@dataclass
class Comparison:
    op: str
    left: Any
    right: Any


@dataclass
class NullCheck:
    column: ColumnRef
    negated: bool


@dataclass
class Like:
    column: ColumnRef
    pattern: str
    negated: bool


@dataclass
class InList:
    column: ColumnRef
    values: list[Any]
    negated: bool


@dataclass
class BoolOp:
    op: str  # AND | OR
    operands: list[Any]


@dataclass
class NotOp:
    operand: Any


@dataclass
class StringLiteral:
    value: str


@dataclass
class Aggregate:
    name: str
    argument: Any  # rowexpr or Star
    condition: Any | None = None


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

class FormulaParser:
    def __init__(self, formula: str) -> None:
        self.formula = formula
        self.tokens = tokenize(formula)
        self.pos = 0

    # -- token helpers ----------------------------------------------------
    def peek(self, offset: int = 0) -> Token | None:
        index = self.pos + offset
        return self.tokens[index] if index < len(self.tokens) else None

    def peek_value(self) -> str | None:
        token = self.peek()
        return token.value if token else None

    def at_keyword(self, word: str) -> bool:
        token = self.peek()
        return token is not None and token.kind == "keyword" and token.value.upper() == word

    def at_op(self, *ops: str) -> bool:
        token = self.peek()
        return token is not None and token.kind == "op" and token.value in ops

    def advance(self) -> Token:
        token = self.peek()
        if token is None:
            raise FormulaError("Unexpected end of formula")
        self.pos += 1
        return token

    def expect_op(self, op: str) -> Token:
        token = self.peek()
        if token is None or token.kind != "op" or token.value != op:
            got = token.value if token else "end of formula"
            raise FormulaError(f"Expected {op!r}, got {got!r}")
        return self.advance()

    def expect_keyword(self, word: str) -> Token:
        if not self.at_keyword(word):
            got = self.peek_value() or "end of formula"
            raise FormulaError(f"Expected {word}, got {got!r}")
        return self.advance()

    # -- entry point ------------------------------------------------------
    def parse(self) -> Any:
        if not self.tokens:
            raise FormulaError("Formula is empty")
        node = self.expr()
        if self.peek() is not None:
            raise FormulaError(f"Unexpected trailing token {self.peek_value()!r}")
        return node

    # -- aggregate level --------------------------------------------------
    def expr(self) -> Any:
        node = self.term()
        while self.at_op("+", "-"):
            op = self.advance().value
            node = BinOp(op, node, self.term())
        return node

    def term(self) -> Any:
        node = self.factor()
        while self.at_op("*", "/"):
            op = self.advance().value
            node = BinOp(op, node, self.factor())
        return node

    def factor(self) -> Any:
        if self.at_op("-"):
            self.advance()
            return UnaryMinus(self.factor())
        if self.at_op("+"):
            self.advance()
            return self.factor()
        if self.at_op("("):
            self.advance()
            node = self.expr()
            self.expect_op(")")
            return node
        token = self.peek()
        if token is None:
            raise FormulaError("Unexpected end of formula")
        if token.kind == "number":
            return Number(float(self.advance().value))
        if token.kind == "ident" and token.value.upper() in ALLOWED_FUNCS:
            return self.aggregate()
        if token.kind == "ident":
            raise FormulaError(
                f"{token.value!r} is not an aggregate. Every column must sit inside one of: "
                + ", ".join(sorted(ALLOWED_FUNCS))
            )
        raise FormulaError(f"Unexpected token {token.value!r}")

    def aggregate(self) -> Aggregate:
        name = self.advance().value.upper()
        if name not in ALLOWED_FUNCS:
            raise FormulaError(f"Function not allowed: {name}")
        self.expect_op("(")
        if self.at_op("*"):
            if name not in {"COUNT"}:
                raise FormulaError(f"{name}(*) is not meaningful; only COUNT(*) is allowed")
            self.advance()
            argument: Any = Star()
        else:
            argument = self.row_expr()
        condition = None
        if self.at_keyword("WHERE"):
            self.advance()
            condition = self.condition()
        self.expect_op(")")
        return Aggregate(name, argument, condition)

    # -- row level --------------------------------------------------------
    def row_expr(self) -> Any:
        node = self.row_term()
        while self.at_op("+", "-"):
            op = self.advance().value
            node = BinOp(op, node, self.row_term())
        return node

    def row_term(self) -> Any:
        node = self.row_factor()
        while self.at_op("*", "/"):
            op = self.advance().value
            node = BinOp(op, node, self.row_factor())
        return node

    def row_factor(self) -> Any:
        if self.at_op("-"):
            self.advance()
            return UnaryMinus(self.row_factor())
        if self.at_op("+"):
            self.advance()
            return self.row_factor()
        if self.at_op("("):
            self.advance()
            node = self.row_expr()
            self.expect_op(")")
            return node
        token = self.peek()
        if token is None:
            raise FormulaError("Unexpected end of formula")
        if token.kind == "number":
            return Number(float(self.advance().value))
        if token.kind == "string":
            return StringLiteral(self.advance().value)
        if token.kind == "ident":
            if token.value.upper() in ALLOWED_FUNCS:
                raise FormulaError(
                    f"{token.value.upper()} cannot be nested inside another aggregate"
                )
            return self.column_ref()
        raise FormulaError(f"Unexpected token {token.value!r} inside an aggregate")

    def column_ref(self) -> ColumnRef:
        token = self.advance()
        if token.kind != "ident":
            raise FormulaError(f"Invalid identifier {token.value!r}")
        if self.at_op("."):
            self.advance()
            second = self.advance()
            if second.kind not in {"ident", "keyword"}:
                raise FormulaError(f"Invalid column name {second.value!r}")
            return ColumnRef(token.value, second.value)
        return ColumnRef(None, token.value)

    # -- conditions -------------------------------------------------------
    def condition(self) -> Any:
        node = self.conjunction()
        operands = [node]
        while self.at_keyword("OR"):
            self.advance()
            operands.append(self.conjunction())
        return operands[0] if len(operands) == 1 else BoolOp("OR", operands)

    def conjunction(self) -> Any:
        node = self.predicate()
        operands = [node]
        while self.at_keyword("AND"):
            self.advance()
            operands.append(self.predicate())
        return operands[0] if len(operands) == 1 else BoolOp("AND", operands)

    def predicate(self) -> Any:
        if self.at_keyword("NOT"):
            self.advance()
            return NotOp(self.predicate())
        if self.at_op("("):
            # Could be a grouped condition or a parenthesised row expression.
            save = self.pos
            self.advance()
            try:
                node = self.condition()
                self.expect_op(")")
                return node
            except FormulaError:
                self.pos = save
        left = self.row_expr()
        if self.at_keyword("IS"):
            self.advance()
            negated = False
            if self.at_keyword("NOT"):
                self.advance()
                negated = True
            self.expect_keyword("NULL")
            if not isinstance(left, ColumnRef):
                raise FormulaError("IS NULL requires a column reference")
            return NullCheck(left, negated)
        negated = False
        if self.at_keyword("NOT"):
            self.advance()
            negated = True
        if self.at_keyword("LIKE"):
            self.advance()
            token = self.advance()
            if token.kind != "string":
                raise FormulaError("LIKE requires a quoted pattern")
            if not isinstance(left, ColumnRef):
                raise FormulaError("LIKE requires a column reference")
            return Like(left, token.value, negated)
        if self.at_keyword("IN"):
            self.advance()
            self.expect_op("(")
            values: list[Any] = []
            while True:
                token = self.advance()
                if token.kind == "string":
                    values.append(StringLiteral(token.value))
                elif token.kind == "number":
                    values.append(Number(float(token.value)))
                else:
                    raise FormulaError("IN accepts only literal values")
                if self.at_op(","):
                    self.advance()
                    continue
                break
            self.expect_op(")")
            if not isinstance(left, ColumnRef):
                raise FormulaError("IN requires a column reference")
            if not values:
                raise FormulaError("IN requires at least one value")
            return InList(left, values, negated)
        if negated:
            raise FormulaError("NOT must be followed by LIKE, IN or NULL")
        token = self.peek()
        if token is None or token.kind != "op" or token.value not in COMPARISONS:
            got = token.value if token else "end of formula"
            raise FormulaError(f"Expected a comparison operator, got {got!r}")
        op = self.advance().value
        right = self.row_expr()
        return Comparison(op, left, right)


# --------------------------------------------------------------------------
# Schema resolution
# --------------------------------------------------------------------------

Schema = dict[str, list[str]]


class _Resolver:
    """Binds every column reference to a real table and column.

    Unqualified columns are allowed when exactly one table provides that name;
    an ambiguous name is an error rather than a silent pick.
    """

    def __init__(self, schema: Schema | None) -> None:
        self.schema = schema
        self.lookup: dict[str, dict[str, str]] = {}
        self.table_names: dict[str, str] = {}
        if schema:
            for table, columns in schema.items():
                self.table_names[table.lower()] = table
                self.lookup[table] = {column.lower(): column for column in columns}

    def resolve(self, ref: ColumnRef) -> ColumnRef:
        if not self.schema:
            return ref
        if ref.table:
            table = self.table_names.get(ref.table.lower())
            if table is None:
                raise FormulaError(
                    f"Unknown table {ref.table!r}. Available: {', '.join(sorted(self.schema))}"
                )
            column = self.lookup[table].get(ref.column.lower())
            if column is None:
                raise FormulaError(
                    f"Unknown column {ref.table}.{ref.column}. "
                    f"{table} has: {', '.join(sorted(self.schema[table])[:15])}"
                )
            return ColumnRef(table, column)
        owners = [
            (table, columns[ref.column.lower()])
            for table, columns in self.lookup.items()
            if ref.column.lower() in columns
        ]
        if not owners:
            raise FormulaError(f"Unknown column {ref.column!r} in any table")
        if len(owners) > 1:
            raise FormulaError(
                f"Column {ref.column!r} is ambiguous across "
                f"{', '.join(t for t, _ in owners)}; qualify it as table.column"
            )
        return ColumnRef(owners[0][0], owners[0][1])


# --------------------------------------------------------------------------
# SQL generation
# --------------------------------------------------------------------------

def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _column_sql(ref: ColumnRef) -> str:
    if ref.table:
        return f"{quote_ident(ref.table)}.{quote_ident(ref.column)}"
    return quote_ident(ref.column)


def _row_sql(node: Any) -> str:
    if isinstance(node, ColumnRef):
        return _column_sql(node)
    if isinstance(node, Number):
        return repr(node.value)
    if isinstance(node, StringLiteral):
        return quote_literal(node.value)
    if isinstance(node, UnaryMinus):
        return f"(-{_row_sql(node.operand)})"
    if isinstance(node, BinOp):
        left, right = _row_sql(node.left), _row_sql(node.right)
        if node.op == "/":
            # A zero denominator is a data condition, not a crash.
            return f"({left} / NULLIF({right}, 0))"
        return f"({left} {node.op} {right})"
    raise FormulaError(f"Unsupported row expression node {type(node).__name__}")


def _condition_sql(node: Any) -> str:
    if isinstance(node, BoolOp):
        joiner = f" {node.op} "
        return "(" + joiner.join(_condition_sql(operand) for operand in node.operands) + ")"
    if isinstance(node, NotOp):
        return f"(NOT {_condition_sql(node.operand)})"
    if isinstance(node, Comparison):
        op = "<>" if node.op == "!=" else node.op
        return f"({_row_sql(node.left)} {op} {_row_sql(node.right)})"
    if isinstance(node, NullCheck):
        return f"({_column_sql(node.column)} IS {'NOT ' if node.negated else ''}NULL)"
    if isinstance(node, Like):
        keyword = "NOT LIKE" if node.negated else "LIKE"
        return f"({_column_sql(node.column)} {keyword} {quote_literal(node.pattern)})"
    if isinstance(node, InList):
        keyword = "NOT IN" if node.negated else "IN"
        values = ", ".join(_row_sql(value) for value in node.values)
        return f"({_column_sql(node.column)} {keyword} ({values}))"
    raise FormulaError(f"Unsupported condition node {type(node).__name__}")


def _aggregate_sql(node: Aggregate) -> str:
    if isinstance(node.argument, Star):
        inner = "*"
        if node.condition is not None:
            inner = f"CASE WHEN {_condition_sql(node.condition)} THEN 1 END"
    else:
        inner = _row_sql(node.argument)
        if node.condition is not None:
            inner = f"CASE WHEN {_condition_sql(node.condition)} THEN {inner} END"
    return AGGREGATES[node.name].format(arg=inner)


def _select_sql(node: Any) -> str:
    if isinstance(node, Aggregate):
        return _aggregate_sql(node)
    if isinstance(node, Number):
        return repr(node.value)
    if isinstance(node, UnaryMinus):
        return f"(-{_select_sql(node.operand)})"
    if isinstance(node, BinOp):
        left, right = _select_sql(node.left), _select_sql(node.right)
        if node.op == "/":
            return f"({left} / NULLIF({right}, 0))"
        return f"({left} {node.op} {right})"
    raise FormulaError(f"Unsupported expression node {type(node).__name__}")


# --------------------------------------------------------------------------
# Tree walking
# --------------------------------------------------------------------------

def _walk(node: Any) -> Iterable[Any]:
    yield node
    for attribute in ("operand", "left", "right", "argument", "condition", "column"):
        child = getattr(node, attribute, None)
        if child is not None and not isinstance(child, (str, float, int, bool)):
            yield from _walk(child)
    for collection in ("operands", "values"):
        children = getattr(node, collection, None)
        if isinstance(children, list):
            for child in children:
                yield from _walk(child)


def _rebind(node: Any, resolver: _Resolver) -> Any:
    """Return the tree with every ColumnRef resolved against the schema."""
    if isinstance(node, ColumnRef):
        return resolver.resolve(node)
    for attribute in ("operand", "left", "right", "argument", "condition", "column"):
        child = getattr(node, attribute, None)
        if child is not None and not isinstance(child, (str, float, int, bool)):
            setattr(node, attribute, _rebind(child, resolver))
    for collection in ("operands", "values"):
        children = getattr(node, collection, None)
        if isinstance(children, list):
            setattr(node, collection, [_rebind(child, resolver) for child in children])
    return node


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

class CompiledKPI(BaseModel):
    """A formula compiled to SQL, plus everything needed to re-shape it.

    ``sql`` answers "what is the number". ``grouped_sql`` answers "by what",
    reusing the same select expression and FROM clause instead of rewriting
    the query text, so a breakdown can never drift from the headline value.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    formula: str
    sql: str
    select_expr: str
    from_sql: str
    tables: list[str]
    columns: list[str]
    functions: list[str]
    has_filter: bool = False
    # How the metric behaves when split by a dimension:
    #   additive      - segment values sum to the total (SUM, COUNT)
    #   semi_additive - a valid per-segment value, but segments overlap and do
    #                   not sum to the total (COUNT DISTINCT)
    #   non_additive  - segment values cannot be summed or shared at all
    #                   (averages, medians, any ratio)
    # Share-of-total statements are only ever made about additive metrics.
    additivity: str = "additive"

    def grouped_sql(
        self,
        dimension_sql: str,
        *,
        alias: str = "dimension",
        where: str | None = None,
        order_by: str | None = "value DESC",
        limit: int | None = None,
        exclude_null_dimension: bool = True,
    ) -> str:
        clauses = [f"SELECT {dimension_sql} AS {quote_ident(alias)}, {self.select_expr} AS value"]
        clauses.append(self.from_sql)
        conditions = [c for c in [where] if c]
        if exclude_null_dimension:
            conditions.append(f"{dimension_sql} IS NOT NULL")
        if conditions:
            clauses.append("WHERE " + " AND ".join(f"({c})" for c in conditions))
        clauses.append("GROUP BY 1")
        if order_by:
            clauses.append(f"ORDER BY {order_by}")
        if limit:
            clauses.append(f"LIMIT {int(limit)}")
        return " ".join(clauses)

    def scalar_sql(self, where: str | None = None) -> str:
        clauses = [f"SELECT {self.select_expr} AS value", self.from_sql]
        if where:
            clauses.append(f"WHERE ({where})")
        return " ".join(clauses)


def compile_formula(
    formula: str,
    joins: list[dict[str, Any]] | None = None,
    schema: Schema | None = None,
) -> CompiledKPI:
    """Parse, validate and compile a KPI formula to read-only DuckDB SQL.

    ``schema`` (table -> columns) is optional but strongly recommended: with it,
    an invented column is rejected here rather than becoming a failed query or,
    worse, a plausible number from the wrong column.
    """
    if not formula or not formula.strip():
        raise FormulaError("Formula is empty")

    tree = FormulaParser(formula).parse()
    resolver = _Resolver(schema)
    tree = _rebind(tree, resolver)

    tables: set[str] = set()
    columns: set[str] = set()
    functions: set[str] = set()
    has_filter = False
    for node in _walk(tree):
        if isinstance(node, ColumnRef):
            if node.table:
                tables.add(node.table)
            columns.add(node.qualified())
        elif isinstance(node, Aggregate):
            functions.add(node.name)
            if node.condition is not None:
                has_filter = True

    if not functions:
        raise FormulaError("A KPI must contain at least one aggregate")

    if not tables:
        # COUNT(*) names no column, so the table has to come from the schema.
        if schema and len(schema) == 1:
            tables.add(next(iter(schema)))
        elif schema:
            raise FormulaError(
                "COUNT(*) is ambiguous across "
                f"{', '.join(sorted(schema))}; count a column instead, e.g. COUNT(table.column)"
            )
        else:
            raise FormulaError("Formula does not reference any table")

    select_expr = _select_sql(tree)
    from_sql = _from_clause(sorted(tables), joins or [])
    additivity = _additivity(tree)
    return CompiledKPI(
        additivity=additivity,
        formula=formula,
        sql=f"SELECT {select_expr} AS value {from_sql}",
        select_expr=select_expr,
        from_sql=from_sql,
        tables=sorted(tables),
        columns=sorted(columns),
        functions=sorted(functions),
        has_filter=has_filter,
    )


NON_ADDITIVE_AGGREGATES = {"AVG", "MEDIAN", "STDDEV", "MIN", "MAX"}


def _additivity(node: Any) -> str:
    """Classify how the metric may be split across a dimension.

    Getting this wrong is how dashboards end up claiming that one country is
    "48% of average unit price" -- a statement with no meaning, because
    averages do not add up.
    """
    if isinstance(node, Aggregate):
        if node.name in NON_ADDITIVE_AGGREGATES:
            return "non_additive"
        if node.name == "COUNT_DISTINCT":
            return "semi_additive"
        return "additive"
    if isinstance(node, Number):
        return "additive"
    if isinstance(node, UnaryMinus):
        return _additivity(node.operand)
    if isinstance(node, BinOp):
        if node.op in {"*", "/"}:
            # A ratio or a scaled aggregate never redistributes across segments.
            return "non_additive"
        left, right = _additivity(node.left), _additivity(node.right)
        for level in ("non_additive", "semi_additive"):
            if level in (left, right):
                return level
        return "additive"
    return "non_additive"


def _from_clause(tables: list[str], joins: list[dict[str, Any]]) -> str:
    if not tables:
        raise FormulaError("Formula does not reference any table")
    if len(tables) == 1:
        return f"FROM {quote_ident(tables[0])}"
    remaining = set(tables[1:])
    used = {tables[0]}
    parts = [f"FROM {quote_ident(tables[0])}"]
    while remaining:
        matched = False
        for join in joins:
            source, target = join["source_table"], join["target_table"]
            if source in used and target in remaining:
                parts.append(_join_sql(target, source, join["source_column"], target, join["target_column"]))
                used.add(target)
                remaining.discard(target)
                matched = True
                break
            if target in used and source in remaining:
                parts.append(_join_sql(source, target, join["target_column"], source, join["source_column"]))
                used.add(source)
                remaining.discard(source)
                matched = True
                break
        if not matched:
            raise FormulaError(
                f"No validated join path reaches {sorted(remaining)} from {sorted(used)}. "
                "A KPI may only span tables the profiler proved are related."
            )
    return " ".join(parts)


def _join_sql(new_table: str, left_table: str, left_column: str, right_table: str, right_column: str) -> str:
    return (
        f"LEFT JOIN {quote_ident(new_table)} ON "
        f"{quote_ident(left_table)}.{quote_ident(left_column)} = "
        f"{quote_ident(right_table)}.{quote_ident(right_column)}"
    )


def describe_grammar() -> dict[str, Any]:
    """Machine-readable grammar summary, used in agent prompts and the UI."""
    return {
        "aggregates": sorted(ALLOWED_FUNCS),
        "operators": ["+", "-", "*", "/", "unary -", "parentheses"],
        "row_level_arithmetic": True,
        "conditional_aggregates": "AGG(expr WHERE condition)",
        "predicates": ["=", "!=", "<", "<=", ">", ">=", "IS [NOT] NULL", "[NOT] LIKE", "[NOT] IN"],
        "examples": [
            "SUM(sales.quantity * sales.unit_price)",
            "SUM(sales.quantity * sales.unit_price) / COUNT_DISTINCT(sales.invoice_no)",
            "SUM(sales.quantity WHERE sales.quantity < 0)",
            "COUNT_DISTINCT(sales.invoice_no WHERE sales.invoice_no LIKE 'C%') / COUNT_DISTINCT(sales.invoice_no)",
            "COUNT(*)",
        ],
        "rules": [
            "Every column must sit inside an aggregate.",
            "Columns must be written table.column exactly as provided.",
            "Division is guarded: a zero denominator yields NULL, never an error.",
        ],
    }

"""Bind physical columns to business roles.

A KPI catalog cannot be written against column names, because every dataset
spells them differently: ``UnitPrice``, ``price_unitaire``, ``item_price``.
It can be written against *roles* -- "the unit price column" -- provided
something binds roles to columns first, with evidence and a confidence score.

Binding uses the profile, not just the name: a column called ``total`` that is
95% unique and monotonically increasing is an identifier, not a measure. Every
binding records why it was chosen so the auditor can show its work.
"""

from __future__ import annotations

import re
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

from app.data.profiler import ColumnProfile, TableProfile

# role -> (name patterns, required logical types, anti-patterns)
ROLE_RULES: dict[str, dict[str, Any]] = {
    "order_id": {
        "patterns": [r"invoice", r"order", r"transaction", r"receipt", r"basket", r"ticket"],
        "types": {"identifier", "categorical", "text", "numeric"},
        "anti": [r"date", r"time", r"item", r"line", r"detail", r"status"],
        "kind": "identifier",
    },
    "customer_id": {
        "patterns": [r"customer", r"client", r"buyer", r"user", r"account", r"member"],
        "types": {"identifier", "categorical", "text", "numeric"},
        "anti": [r"date", r"name", r"city", r"state", r"country", r"segment", r"type"],
        "kind": "identifier",
    },
    "product_id": {
        "patterns": [r"product", r"item", r"sku", r"stock", r"article", r"material"],
        "types": {"identifier", "categorical", "text", "numeric"},
        "anti": [r"date", r"categ", r"name", r"desc", r"weight", r"qty", r"quantity"],
        "kind": "identifier",
    },
    "quantity": {
        "patterns": [r"quantity", r"\bqty\b", r"units?\b", r"volume", r"count\b", r"pieces"],
        "types": {"quantity", "numeric", "currency"},
        "anti": [r"price", r"amount", r"total", r"id$", r"code"],
        "kind": "measure",
    },
    "unit_price": {
        "patterns": [r"unit[_ ]?price", r"^price$", r"price", r"rate", r"tarif"],
        "types": {"currency", "numeric"},
        "anti": [r"total", r"amount", r"sum", r"discount", r"qty", r"quantity"],
        "kind": "measure",
    },
    "amount": {
        "patterns": [r"amount", r"revenue", r"total", r"sales", r"turnover", r"payment", r"value", r"gmv"],
        "types": {"currency", "numeric"},
        "anti": [r"id$", r"code", r"count", r"qty", r"unit[_ ]?price"],
        "kind": "measure",
    },
    "cost": {
        "patterns": [r"cost", r"cogs", r"expense", r"purchase[_ ]?price"],
        "types": {"currency", "numeric"},
        "anti": [r"id$"],
        "kind": "measure",
    },
    "discount": {
        "patterns": [r"discount", r"rebate", r"promo"],
        "types": {"currency", "numeric"},
        "anti": [r"id$", r"flag"],
        "kind": "measure",
    },
    "freight": {
        "patterns": [r"freight", r"shipping", r"delivery[_ ]?(cost|fee|price)"],
        "types": {"currency", "numeric"},
        "anti": [r"date", r"id$"],
        "kind": "measure",
    },
    "event_date": {
        "patterns": [r"date", r"time", r"timestamp", r"created", r"ordered", r"purchase"],
        "types": {"datetime"},
        "anti": [r"deliver", r"ship", r"approv", r"estimat"],
        "kind": "dimension",
    },
    "geo": {
        "patterns": [r"country", r"region", r"state", r"city", r"province", r"zone", r"market"],
        "types": {"geo", "categorical", "text"},
        "anti": [r"code$", r"id$", r"zip", r"postal"],
        "kind": "dimension",
    },
    "category": {
        "patterns": [r"categ", r"segment", r"type", r"class", r"family", r"group", r"department"],
        "types": {"categorical", "text"},
        "anti": [r"id$", r"date"],
        "kind": "dimension",
    },
    "status": {
        "patterns": [r"status", r"state$", r"stage", r"phase"],
        "types": {"categorical", "text"},
        "anti": [r"id$", r"date"],
        "kind": "dimension",
    },
    "channel": {
        "patterns": [r"channel", r"source", r"medium", r"platform", r"store"],
        "types": {"categorical", "text"},
        "anti": [r"id$", r"date"],
        "kind": "dimension",
    },
    "description": {
        "patterns": [r"desc", r"name", r"label", r"title"],
        "types": {"text", "categorical"},
        "anti": [r"id$"],
        "kind": "dimension",
    },
}

# A dimension people can usefully read on a chart axis. Beyond this many
# distinct values a bar chart is noise, and the column is really a key.
MAX_DIMENSION_CARDINALITY = 200


class RoleBinding(BaseModel):
    role: str
    table: str
    column: str
    confidence: float
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    @property
    def ref(self) -> str:
        return f"{self.table}.{self.column}"


class ReturnsConvention(BaseModel):
    """How this dataset represents a cancellation or refund.

    Retail extracts almost always contain them, and summing straight through
    them silently nets returns against sales. Detecting the convention lets
    the catalog publish gross, net and returned as three separate KPIs.
    """

    has_negative_quantity: bool = False
    negative_quantity_rows: int = 0
    cancel_prefix: str | None = None
    cancel_prefix_rows: int = 0
    evidence: dict[str, Any] = Field(default_factory=dict)

    @property
    def detected(self) -> bool:
        return self.has_negative_quantity or self.cancel_prefix is not None


class SemanticBinding(BaseModel):
    roles: dict[str, RoleBinding] = Field(default_factory=dict)
    returns: ReturnsConvention = Field(default_factory=ReturnsConvention)
    dimensions: list[RoleBinding] = Field(default_factory=list)
    unbound_notes: list[str] = Field(default_factory=list)

    def ref(self, role: str) -> str | None:
        binding = self.roles.get(role)
        return binding.ref if binding else None

    def has(self, *roles: str) -> bool:
        return all(role in self.roles for role in roles)


def _score_role(role: str, rules: dict[str, Any], column: ColumnProfile, profile: TableProfile) -> tuple[float, str]:
    name = column.name.lower()
    if any(re.search(pattern, name) for pattern in rules["anti"]):
        return 0.0, ""
    name_hit = next((p for p in rules["patterns"] if re.search(p, name)), None)
    if not name_hit:
        return 0.0, ""

    score = 0.55
    reasons = [f"name matches /{name_hit}/"]

    if column.logical_type in rules["types"]:
        score += 0.25
        reasons.append(f"logical type {column.logical_type}")
    else:
        score -= 0.2
        reasons.append(f"logical type {column.logical_type} is unusual for this role")

    kind = rules["kind"]
    if kind == "identifier":
        # An identifier repeats (many lines per order) but is not unique per row
        # unless the grain is the entity itself.
        if 0 < column.distinct_count < profile.row_count:
            score += 0.15
            reasons.append(f"{column.distinct_count} distinct values below the row count")
        if column.null_pct > 50:
            score -= 0.25
            reasons.append(f"{column.null_pct:.1f}% null")
    elif kind == "measure":
        if column.stats.get("mean") is not None:
            score += 0.1
            reasons.append("numeric statistics available")
        if column.is_candidate_pk:
            score -= 0.5
            reasons.append("unique per row, so it behaves like a key")
    elif kind == "dimension":
        if column.logical_type == "datetime":
            score += 0.1
        elif column.distinct_count > MAX_DIMENSION_CARDINALITY:
            score -= 0.3
            reasons.append(f"{column.distinct_count} distinct values is too many to chart")
        else:
            score += 0.1
            reasons.append(f"{column.distinct_count} distinct values")

    # An exact name match is close to conclusive.
    if name in {role, role.replace("_", ""), role.replace("_id", "")}:
        score += 0.2
        reasons.append("name matches the role exactly")

    return max(0.0, min(1.0, score)), "; ".join(reasons)


def detect_returns(
    frames: dict[str, pl.DataFrame],
    quantity: RoleBinding | None,
    order_id: RoleBinding | None,
) -> ReturnsConvention:
    convention = ReturnsConvention()
    if quantity is not None:
        frame = frames.get(quantity.table)
        if frame is not None and quantity.column in frame.columns:
            series = frame[quantity.column]
            if series.dtype.is_numeric():
                negatives = int((series < 0).sum())
                if negatives:
                    convention.has_negative_quantity = True
                    convention.negative_quantity_rows = negatives
                    convention.evidence["negative_quantity_share"] = round(
                        negatives / max(frame.height, 1), 6
                    )

    if order_id is not None:
        frame = frames.get(order_id.table)
        if frame is not None and order_id.column in frame.columns:
            series = frame[order_id.column].drop_nulls().cast(pl.Utf8, strict=False).drop_nulls()
            if series.len():
                # A single leading letter on a minority of ids is the common
                # "cancellation" marker in retail exports.
                prefixed = series.filter(series.str.contains(r"^[A-Za-z]"))
                if 0 < prefixed.len() < series.len() * 0.5:
                    letters = prefixed.str.slice(0, 1).value_counts().sort("count", descending=True)
                    if letters.height:
                        top = letters.to_dicts()[0]
                        letter = str(top[letters.columns[0]])
                        count = int(top["count"])
                        convention.cancel_prefix = letter
                        convention.cancel_prefix_rows = count
                        convention.evidence["prefix_share"] = round(count / series.len(), 6)
    return convention


def bind_roles(profiles: dict[str, TableProfile], frames: dict[str, pl.DataFrame]) -> SemanticBinding:
    """Choose the best column for each business role across all tables."""
    candidates: dict[str, list[RoleBinding]] = {}
    for table, profile in profiles.items():
        for column in profile.columns:
            for role, rules in ROLE_RULES.items():
                score, reason = _score_role(role, rules, column, profile)
                if score <= 0.5:
                    continue
                candidates.setdefault(role, []).append(
                    RoleBinding(
                        role=role,
                        table=table,
                        column=column.name,
                        confidence=round(score, 4),
                        evidence={
                            "logical_type": column.logical_type,
                            "distinct_count": column.distinct_count,
                            "null_pct": column.null_pct,
                        },
                        reason=reason,
                    )
                )

    binding = SemanticBinding()
    taken: set[tuple[str, str]] = set()
    # Resolve roles in a fixed order so a column cannot be claimed by a weaker
    # role first. Measures before dimensions, specific before generic.
    order = [
        "quantity",
        "unit_price",
        "cost",
        "discount",
        "freight",
        "amount",
        "order_id",
        "customer_id",
        "product_id",
        "event_date",
        "geo",
        "category",
        "status",
        "channel",
        "description",
    ]
    for role in order:
        pool = sorted(candidates.get(role, []), key=lambda b: -b.confidence)
        for candidate in pool:
            key = (candidate.table, candidate.column)
            if key in taken:
                continue
            binding.roles[role] = candidate
            taken.add(key)
            break

    binding.returns = detect_returns(
        frames, binding.roles.get("quantity"), binding.roles.get("order_id")
    )

    # Chartable dimensions, ranked. A dimension with more distinct values than
    # MAX_DIMENSION_CARDINALITY is a key wearing a dimension's name.
    dimension_pool: list[RoleBinding] = []
    for table, profile in profiles.items():
        for column in profile.columns:
            if column.logical_type == "datetime":
                score = 0.9
            elif column.logical_type in {"geo", "categorical"} and column.distinct_count <= MAX_DIMENSION_CARDINALITY:
                # Fewer, more balanced categories make a better axis.
                score = 0.8 - min(0.3, column.distinct_count / (MAX_DIMENSION_CARDINALITY * 4))
            else:
                continue
            if column.is_candidate_pk:
                continue
            dimension_pool.append(
                RoleBinding(
                    role="dimension",
                    table=table,
                    column=column.name,
                    confidence=round(score, 4),
                    evidence={
                        "logical_type": column.logical_type,
                        "distinct_count": column.distinct_count,
                    },
                    reason=f"{column.logical_type} with {column.distinct_count} distinct values",
                )
            )
    binding.dimensions = sorted(dimension_pool, key=lambda d: -d.confidence)

    for role in ("quantity", "unit_price", "amount", "order_id", "event_date"):
        if role not in binding.roles:
            binding.unbound_notes.append(
                f"No column bound to role '{role}'; KPIs that need it were not generated."
            )
    return binding

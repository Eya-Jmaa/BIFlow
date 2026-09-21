"""Domain KPI catalog.

KPIs are declared once, against business roles rather than column names, and
instantiated for whatever dataset arrives. A template only produces a KPI when
every role it needs was actually bound, so a dataset without a cost column
simply yields no margin KPI instead of a fabricated one.

The catalog is the deterministic floor. An LLM may add to it, but never
replaces it, so the headline numbers are the same on every run with or without
a model configured.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.analytics.roles import SemanticBinding


class KPITemplate(BaseModel):
    slug: str
    name: str
    description: str
    business_meaning: str
    formula: str
    # Used instead of ``formula`` once a cancellation convention is detected,
    # so counts and averages can exclude cancellation documents rather than
    # quietly treating a refund as another order.
    formula_when_returns: str | None = None
    unit: str
    # Roles that must be bound for this template to apply.
    requires: list[str] = Field(default_factory=list)
    # At least one group must be fully bound (used for revenue, which can come
    # from a single amount column or from quantity x unit price).
    requires_any: list[list[str]] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=lambda: ["*"])
    needs_returns: bool = False
    needs_cancel_prefix: bool = False
    # Used when a name is only accurate once returns are known to exist:
    # "Revenue" on a dataset with no returns is simply revenue, but on one
    # with returns it has to be labelled net of them.
    name_when_returns: str | None = None
    description_when_returns: str | None = None
    higher_is_better: bool | None = True
    priority: int = 50
    confidence: float = 0.95
    format: dict[str, Any] = Field(default_factory=dict)


# "{revenue}" is a macro expanded below, because revenue itself has two
# possible shapes depending on what the dataset provides.
REVENUE_MACRO = "{revenue}"

TEMPLATES: list[KPITemplate] = [
    KPITemplate(
        slug="net_revenue",
        name="Revenue",
        name_when_returns="Net Revenue",
        description="Total value of every transaction line.",
        description_when_returns=(
            "Total value of every transaction line, after returns are deducted."
        ),
        business_meaning=(
            "The headline top line, and the figure that ties to the ledger. Computed "
            "per row before aggregation, because revenue is quantity times price on "
            "each line, not the sum of price tags. Return lines carry negative "
            "quantities, so they deduct themselves here."
        ),
        formula=REVENUE_MACRO,
        unit="currency",
        requires_any=[["amount"], ["quantity", "unit_price"]],
        domains=["ecommerce", "retail", "general"],
        priority=1,
        format={"style": "currency", "decimals": 0},
    ),
    KPITemplate(
        slug="gross_revenue",
        name="Gross Revenue",
        description="Revenue before returns, excluding cancellation documents.",
        business_meaning=(
            "What was sold before anything came back. Reported separately from net "
            "revenue because a single blended figure hides whether a soft quarter was "
            "weak selling or heavy returns."
        ),
        formula=REVENUE_MACRO + " WHERE_NOT_CANCELLED",
        unit="currency",
        requires_any=[["amount"], ["quantity", "unit_price"]],
        needs_cancel_prefix=True,
        domains=["ecommerce", "retail"],
        priority=2,
        format={"style": "currency", "decimals": 0},
    ),
    KPITemplate(
        slug="returned_value",
        name="Returned Value",
        description="Value of returned or cancelled lines (negative quantities).",
        business_meaning="The monetary cost of returns, which gross revenue silently absorbs.",
        formula=REVENUE_MACRO + " WHERE_RETURNED",
        unit="currency",
        requires_any=[["quantity", "unit_price"]],
        requires=["quantity"],
        needs_returns=True,
        higher_is_better=False,
        domains=["ecommerce", "retail"],
        priority=6,
        format={"style": "currency", "decimals": 0},
    ),
    KPITemplate(
        slug="order_count",
        name="Orders",
        description="Number of distinct orders or invoices.",
        description_when_returns=(
            "Number of distinct orders, excluding cancellation documents."
        ),
        business_meaning=(
            "Transaction volume, independent of basket value. Cancellation documents "
            "are excluded where the dataset marks them, so a refund does not count as "
            "a second sale."
        ),
        formula="COUNT_DISTINCT({order_id})",
        formula_when_returns="COUNT_DISTINCT({order_id} WHERE_NOT_CANCELLED)",
        unit="count",
        requires=["order_id"],
        priority=3,
        format={"style": "integer"},
    ),
    KPITemplate(
        slug="cancelled_orders",
        name="Cancelled Orders",
        description="Number of distinct cancellation documents.",
        business_meaning="Volume of refunds and cancellations, the counterweight to order count.",
        formula="COUNT_DISTINCT({order_id} WHERE_IS_CANCELLED)",
        unit="count",
        requires=["order_id"],
        needs_cancel_prefix=True,
        higher_is_better=False,
        domains=["ecommerce", "retail"],
        priority=6,
        format={"style": "integer"},
    ),
    KPITemplate(
        slug="unique_customers",
        name="Unique Customers",
        description="Number of distinct customers.",
        business_meaning="Size of the active customer base in the period.",
        formula="COUNT_DISTINCT({customer_id})",
        unit="count",
        requires=["customer_id"],
        priority=4,
        format={"style": "integer"},
    ),
    KPITemplate(
        slug="average_order_value",
        name="Average Order Value",
        description="Revenue divided by number of distinct orders.",
        business_meaning=(
            "How much a typical order is worth. The classic retail basket metric; "
            "moves with pricing, bundling and promotion strategy. Where cancellations "
            "are identifiable, both sides of the ratio exclude them, so the average is "
            "over real orders."
        ),
        formula=REVENUE_MACRO + " / COUNT_DISTINCT({order_id})",
        formula_when_returns=(
            REVENUE_MACRO + " WHERE_NOT_CANCELLED / COUNT_DISTINCT({order_id} WHERE_NOT_CANCELLED)"
        ),
        unit="currency",
        requires=["order_id"],
        requires_any=[["amount"], ["quantity", "unit_price"]],
        priority=5,
        format={"style": "currency", "decimals": 2},
    ),
    KPITemplate(
        slug="revenue_per_customer",
        name="Revenue per Customer",
        description="Revenue divided by number of distinct customers.",
        business_meaning="Average value extracted per customer; a floor for lifetime value.",
        formula=REVENUE_MACRO + " / COUNT_DISTINCT({customer_id})",
        unit="currency",
        requires=["customer_id"],
        requires_any=[["amount"], ["quantity", "unit_price"]],
        priority=7,
        format={"style": "currency", "decimals": 2},
    ),
    KPITemplate(
        slug="units_sold",
        name="Units Sold",
        description="Total quantity sold, excluding returned lines.",
        business_meaning="Physical volume moved, the denominator behind unit economics.",
        formula="SUM({quantity} WHERE {quantity} > 0)",
        unit="units",
        requires=["quantity"],
        priority=8,
        format={"style": "integer"},
    ),
    KPITemplate(
        slug="units_per_order",
        name="Units per Order",
        description="Average number of units in an order.",
        business_meaning="Basket size in volume terms; rises with cross-selling.",
        formula="SUM({quantity} WHERE {quantity} > 0) / COUNT_DISTINCT({order_id})",
        unit="units",
        requires=["quantity", "order_id"],
        priority=9,
        format={"style": "decimal", "decimals": 2},
    ),
    KPITemplate(
        slug="order_return_rate",
        name="Order Return Rate",
        description="Share of orders that are cancellations.",
        business_meaning=(
            "Operational quality signal. A rising return rate erodes margin even "
            "while gross revenue looks healthy."
        ),
        formula="COUNT_DISTINCT({order_id} WHERE_IS_CANCELLED) / COUNT_DISTINCT({order_id}) * 100",
        unit="percent",
        requires=["order_id"],
        needs_cancel_prefix=True,
        higher_is_better=False,
        domains=["ecommerce", "retail"],
        priority=10,
        format={"style": "percent", "decimals": 2},
    ),
    KPITemplate(
        slug="active_products",
        name="Active Products",
        description="Number of distinct products sold.",
        business_meaning="Assortment breadth actually moving, not catalogue size.",
        formula="COUNT_DISTINCT({product_id})",
        unit="count",
        requires=["product_id"],
        priority=11,
        format={"style": "integer"},
    ),
    KPITemplate(
        slug="average_unit_price",
        name="Average Unit Price",
        description="Mean price across transaction lines.",
        business_meaning="Price positioning; read together with units sold to separate price from volume effects.",
        formula="AVG({unit_price})",
        unit="currency",
        requires=["unit_price"],
        priority=12,
        format={"style": "currency", "decimals": 2},
    ),
    KPITemplate(
        slug="gross_margin",
        name="Gross Margin",
        description="Revenue minus cost of goods sold.",
        business_meaning="What is left after the cost of what was sold; the real profitability line.",
        formula=REVENUE_MACRO + " - SUM({quantity} * {cost})",
        unit="currency",
        requires=["quantity", "cost"],
        requires_any=[["amount"], ["quantity", "unit_price"]],
        domains=["ecommerce", "retail", "general"],
        priority=13,
        format={"style": "currency", "decimals": 0},
    ),
    KPITemplate(
        slug="transaction_lines",
        name="Transaction Lines",
        description="Number of rows in the transaction table.",
        business_meaning="Raw record volume; the grain of the fact table.",
        formula="COUNT(*)",
        unit="count",
        priority=40,
        confidence=0.9,
        format={"style": "integer"},
    ),
    # --- other domains, to keep the catalog genuinely domain-aware ---------
    KPITemplate(
        slug="freight_cost",
        name="Freight Cost",
        description="Total shipping cost.",
        business_meaning="Logistics spend, a direct deduction from contribution margin.",
        formula="SUM({freight})",
        unit="currency",
        requires=["freight"],
        higher_is_better=False,
        domains=["ecommerce", "retail", "transport"],
        priority=14,
        format={"style": "currency", "decimals": 0},
    ),
    KPITemplate(
        slug="discount_given",
        name="Discount Given",
        description="Total discount granted.",
        business_meaning="Promotional investment; compare against incremental revenue.",
        formula="SUM({discount})",
        unit="currency",
        requires=["discount"],
        higher_is_better=False,
        domains=["ecommerce", "retail", "marketing"],
        priority=15,
        format={"style": "currency", "decimals": 0},
    ),
]


class InstantiatedKPI(BaseModel):
    slug: str
    name: str
    description: str
    business_meaning: str
    formula: str
    unit: str
    confidence: float
    priority: int
    higher_is_better: bool | None = True
    dimensions: list[str] = Field(default_factory=list)
    format: dict[str, Any] = Field(default_factory=dict)
    source: str = "catalog"
    provenance: dict[str, Any] = Field(default_factory=dict)


def _revenue_expression(binding: SemanticBinding) -> tuple[str, str] | None:
    """Return (expression, explanation) for revenue, or None if impossible."""
    if binding.has("quantity", "unit_price"):
        quantity, price = binding.ref("quantity"), binding.ref("unit_price")
        return (
            f"SUM({quantity} * {price})",
            f"quantity x unit price summed per line ({quantity} * {price})",
        )
    if binding.has("amount"):
        amount = binding.ref("amount")
        return f"SUM({amount})", f"a pre-computed line amount ({amount})"
    return None


def _cancel_predicate(binding: SemanticBinding, negate: bool) -> str | None:
    prefix = binding.returns.cancel_prefix
    order_id = binding.ref("order_id")
    if prefix and order_id:
        keyword = "NOT LIKE" if negate else "LIKE"
        return f"{order_id} {keyword} '{prefix}%'"
    quantity = binding.ref("quantity")
    if binding.returns.has_negative_quantity and quantity:
        return f"{quantity} {'>=' if negate else '<'} 0"
    return None


def _expand(template: KPITemplate, binding: SemanticBinding) -> tuple[str, dict[str, Any]] | None:
    revenue = _revenue_expression(binding)
    returns_known = _cancel_predicate(binding, negate=False) is not None
    formula = (
        template.formula_when_returns
        if returns_known and template.formula_when_returns
        else template.formula
    )
    provenance: dict[str, Any] = {}
    filters: list[str] = []

    if REVENUE_MACRO in formula:
        if revenue is None:
            return None
        expression, explanation = revenue
        provenance["revenue_basis"] = explanation
        # A filter on revenue applies per row, before summation, so the
        # predicate is pushed inside the aggregate rather than appended after it.
        for token, predicate in (
            ("WHERE_NOT_CANCELLED", _cancel_predicate(binding, negate=True)),
            ("WHERE_RETURNED", f"{binding.ref('quantity')} < 0" if binding.ref("quantity") else None),
        ):
            marker = f"{REVENUE_MACRO} {token}"
            if marker in formula:
                if predicate is None:
                    return None
                formula = formula.replace(marker, expression[:-1] + f" WHERE {predicate})")
                filters.append(predicate)
        formula = formula.replace(REVENUE_MACRO, expression)

    # Remaining markers sit inside an aggregate's parentheses already.
    for token, negate in (("WHERE_NOT_CANCELLED", True), ("WHERE_IS_CANCELLED", False)):
        if token in formula:
            predicate = _cancel_predicate(binding, negate=negate)
            if predicate is None:
                return None
            formula = formula.replace(f" {token}", f" WHERE {predicate}")
            filters.append(predicate)

    for role, bound in binding.roles.items():
        formula = formula.replace("{" + role + "}", bound.ref)
    if "{" in formula:
        return None
    if filters:
        provenance["filters"] = sorted(set(filters))
    return formula, provenance


def instantiate_catalog(binding: SemanticBinding, domain: str) -> list[InstantiatedKPI]:
    """Build every KPI the bound roles can actually support."""
    results: list[InstantiatedKPI] = []
    time_dimension = next(
        (d.ref for d in binding.dimensions if d.evidence.get("logical_type") == "datetime"), None
    )
    chart_dimensions = [
        d.ref for d in binding.dimensions if d.evidence.get("logical_type") != "datetime"
    ][:3]

    for template in TEMPLATES:
        if "*" not in template.domains and domain not in template.domains:
            continue
        if template.requires and not binding.has(*template.requires):
            continue
        if template.requires_any and not any(
            binding.has(*group) for group in template.requires_any
        ):
            continue
        if template.needs_returns and not binding.returns.detected:
            continue
        if template.needs_cancel_prefix and _cancel_predicate(binding, negate=False) is None:
            continue

        expanded = _expand(template, binding)
        if expanded is None:
            continue
        formula, provenance = expanded

        returns_known = binding.returns.detected
        name = template.name_when_returns if returns_known and template.name_when_returns else template.name
        description = (
            template.description_when_returns
            if returns_known and template.description_when_returns
            else template.description
        )

        dimensions = [d for d in [time_dimension, *chart_dimensions] if d]
        results.append(
            InstantiatedKPI(
                slug=template.slug,
                name=name,
                description=description,
                business_meaning=template.business_meaning,
                formula=formula,
                unit=template.unit,
                confidence=template.confidence,
                priority=template.priority,
                higher_is_better=template.higher_is_better,
                dimensions=dimensions,
                format=template.format,
                source="catalog",
                provenance={
                    "template": template.slug,
                    "domain": domain,
                    "roles": {
                        role: bound.ref
                        for role, bound in binding.roles.items()
                        if "{" + role + "}" in template.formula
                        or role in {"quantity", "unit_price", "amount"}
                    },
                    **provenance,
                },
            )
        )

    results.sort(key=lambda k: k.priority)
    return results


def generic_fallback(measures: list[dict[str, Any]], identifiers: list[str]) -> list[InstantiatedKPI]:
    """Last-resort KPIs for a dataset no role matched.

    Deliberately plain: these are described as sums and averages, never dressed
    up as revenue, because nothing here establishes what the numbers mean.
    """
    results: list[InstantiatedKPI] = []
    for index, measure in enumerate(measures[:6]):
        reference = f"{measure['table_name']}.{measure['column_name']}"
        aggregation = measure.get("aggregation", "SUM")
        results.append(
            InstantiatedKPI(
                slug=f"{aggregation.lower()}_{measure['column_name']}".lower(),
                name=f"{aggregation.title()} of {measure['column_name']}",
                description=f"{aggregation} over {reference}.",
                business_meaning=(
                    f"No business role matched {reference}, so it is reported as a plain "
                    f"{aggregation.lower()} without further interpretation."
                ),
                formula=f"{aggregation}({reference})",
                unit=measure.get("unit") or "units",
                confidence=0.5,
                priority=60 + index,
                source="fallback",
                provenance={"reason": "no_role_match", "column": reference},
            )
        )
    for index, identifier in enumerate(identifiers[:2]):
        results.append(
            InstantiatedKPI(
                slug=f"distinct_{identifier.split('.')[-1]}".lower(),
                name=f"Distinct {identifier.split('.')[-1]}",
                description=f"Number of distinct values in {identifier}.",
                business_meaning=f"Cardinality of {identifier}.",
                formula=f"COUNT_DISTINCT({identifier})",
                unit="count",
                confidence=0.6,
                priority=70 + index,
                source="fallback",
                provenance={"reason": "identifier_cardinality", "column": identifier},
            )
        )
    return results

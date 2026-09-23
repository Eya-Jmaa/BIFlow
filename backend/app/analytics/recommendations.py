"""Recommendations derived from measured findings.

A recommendation is only useful if it follows from something the pipeline
actually measured. Each rule here takes the numbers behind one finding and
returns the action they imply, quoting those numbers back, plus a ``basis``
naming the rule that fired — so a reader can audit the advice the same way
they audit a KPI.

Two deliberate constraints:

* **Not every finding gets one.** A metric that simply exists, or a small
  routine move, has no action attached. A recommendation on every row is
  indistinguishable from none.
* **No causal claims.** The pipeline measures association and magnitude, not
  cause. Rules say what to check or quantify, never why something happened.
"""

from __future__ import annotations

from typing import Any

# A move smaller than this is noise in most business series; recommending
# action on it would train people to ignore the column.
MATERIAL_CHANGE = 0.15
# Below this, "concentration" is just an ordinary distribution.
CONCENTRATION_FLOOR = 0.4


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 1:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:,.4g}"


def concentration(
    *, segment: str, share: float, metric: str, segment_value: float | None
) -> tuple[str, str] | None:
    """One segment dominates an additive metric.

    Quantifies the exposure rather than asserting it is bad: a dominant home
    market is normal, a dominant single customer is not, and the pipeline
    cannot tell which this is.
    """
    if share < CONCENTRATION_FLOOR:
        return None
    exposure = segment_value * 0.1 if segment_value is not None else None
    sentence = (
        f"{segment} carries {share * 100:.1f}% of {metric}. "
        + (
            f"A 10% fall there removes about {_money(exposure)} — size that against your plan "
            if exposure is not None
            else "Size the downside of a fall there against your plan "
        )
        + "before treating the total as stable. If this concentration is not deliberate, "
        "look at what limits the other segments: coverage, pricing, or supply."
    )
    return sentence, "concentration>=40% of an additive metric"


def adverse_move(
    *, metric: str, change_pct: float, previous: float | None, current: float | None, period: str
) -> tuple[str, str] | None:
    """A material period-over-period move in the unfavourable direction."""
    if abs(change_pct) < MATERIAL_CHANGE:
        return None
    direction = "rose" if change_pct > 0 else "fell"
    sentence = (
        f"{metric} {direction} {abs(change_pct) * 100:.1f}% in {period} "
        f"({_money(previous)} → {_money(current)}). Break the same two periods down by segment: "
        "a move spread across segments points at pricing or demand, one confined to a single "
        "segment usually points at that account or channel."
    )
    return sentence, f"period-over-period move >= {MATERIAL_CHANGE:.0%}, unfavourable"


def favourable_move(
    *, metric: str, change_pct: float, period: str, r2: float | None
) -> tuple[str, str] | None:
    """A material move in the favourable direction — confirm before planning on it."""
    if abs(change_pct) < MATERIAL_CHANGE:
        return None
    fit = (
        f"The trend fit over the full series is R²={r2:.2f}, "
        + ("so the series is consistent enough to plan against. " if r2 >= 0.5 else
           "which is weak, so treat the level as provisional. ")
        if r2 is not None
        else ""
    )
    sentence = (
        f"{metric} improved {abs(change_pct) * 100:.1f}% in {period}. {fit}"
        "Check the same period a year earlier before reading it as growth rather than seasonality."
    )
    return sentence, f"period-over-period move >= {MATERIAL_CHANGE:.0%}, favourable"


def anomaly(
    *, metric: str, period: str, value: float | None, method: str, periods_tested: int
) -> tuple[str, str]:
    """A point the statistical tests flagged."""
    sentence = (
        f"{metric} reached {_money(value)} in {period}, outside the range of the other "
        f"{max(periods_tested - 1, 0)} periods by the {method} test. Confirm the cause before "
        "treating it as signal — a partial load, a single large order and a genuine promotion "
        "all look like this."
    )
    return sentence, f"{method} outlier"


def pareto(
    *, dimension: str, measure: str, cutoff: int, total_segments: int
) -> tuple[str, str] | None:
    """A small share of one dimension drives most of a measure."""
    if cutoff >= total_segments:
        return None
    sentence = (
        f"{cutoff} of {total_segments} {dimension} values produce 80% of {measure}. "
        f"Give those {cutoff} explicit coverage, and decide deliberately whether the remaining "
        f"{total_segments - cutoff} earn their servicing cost or should be simplified."
    )
    return sentence, "pareto 80% cutoff"


def correlation(*, left: str, right: str, coefficient: float) -> tuple[str, str] | None:
    """A strong linear association between two numeric columns."""
    if abs(coefficient) < 0.5:
        return None
    sentence = (
        f"{left} and {right} move together at r={coefficient:.2f}. This is association, not "
        "cause: check whether one drives the other or both follow a third factor such as "
        "seasonality, before using one to forecast the other."
    )
    return sentence, "|pearson r| >= 0.5"


def seasonality(
    *, metric: str, peak: str, trough: str, amplitude_pct: float
) -> tuple[str, str] | None:
    """A large swing between the strongest and weakest observed period."""
    if amplitude_pct < 50:
        return None
    sentence = (
        f"{metric} swings {amplitude_pct:.0f}% between {trough} and {peak}. Plan stock, staffing "
        f"and cash to the {peak} peak rather than to the average, and judge any month against the "
        "same month last year rather than the one before it."
    )
    return sentence, "peak/trough spread >= 50%"


def return_rate(*, rate_pct: float, returned_value: float | None) -> tuple[str, str] | None:
    """Returns are material enough to erode the top line."""
    if rate_pct < 5:
        return None
    sentence = (
        f"{rate_pct:.1f}% of orders are cancellations"
        + (f", worth {_money(abs(returned_value) if returned_value else None)}" if returned_value else "")
        + ". Split them by product and by country: a rate concentrated in a few SKUs is a "
        "listing or quality problem, one spread evenly is usually fulfilment or expectation."
    )
    return sentence, "order return rate >= 5%"


def data_caveat(*, issue: str) -> tuple[str, str]:
    """A quality condition that limits how far the numbers can be trusted."""
    return (
        f"{issue} Resolve this at the source before the affected figures are used for a decision; "
        "the pipeline reports them but cannot repair them.",
        "data quality caveat",
    )


def attach(insight: Any, rule: tuple[str, str] | None) -> Any:
    """Apply a rule's output to an insight, leaving it untouched when no rule fired."""
    if rule is not None:
        insight.recommendation, insight.recommendation_basis = rule
    return insight

"""Deterministic, auditable schema inference.

Silent type guessing is the most dangerous step in an automated BI pipeline: a
misread date format does not raise, it quietly produces nulls, and every
downstream trend is then computed on a mutilated series.

This module never guesses silently. It scores explicit candidate formats
against a sample, requires a minimum parse rate, and returns the evidence
(chosen format, parse rate, rejected alternatives, ambiguity warnings) so the
profiler and the auditor can surface it.
"""

from __future__ import annotations

import re
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

# Ordered candidates. Day-first and month-first variants are always both
# offered so the sample decides, never the author's locale.
DATETIME_FORMATS: list[str] = [
    "%Y-%m-%d %H:%M:%S%.f",
    "%Y-%m-%dT%H:%M:%S%.f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%m/%d/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m/%d/%y %H:%M",
    "%d/%m/%y %H:%M",
    "%m/%d/%y",
    "%d/%m/%y",
    "%m-%d-%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d, %Y",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
]

MONTH_FIRST = {f for f in DATETIME_FORMATS if "%m/%d" in f or "%m-%d" in f}
DAY_FIRST = {f for f in DATETIME_FORMATS if "%d/%m" in f or "%d-%m" in f or "%d.%m" in f}

# A date column is only reinterpreted when nearly every non-null value parses.
# Anything less is a data problem to report, not a cast to force.
MIN_PARSE_RATE = 0.95

# A numeric cast is held to a stricter standard than a date parse. A date that
# fails to parse leaves a null an analyst can see; a code silently turned into
# a float loses its leading zeros, merges distinct keys and takes its outliers
# with it. The loader therefore casts only when nothing at all is lost, and
# otherwise leaves the column to the quality agent to report and the ETL agent
# to convert explicitly, with lineage.
MIN_NUMERIC_CAST_RATE = 1.0
SAMPLE_SIZE = 20_000

# Names that denote a key or code. Such a column is an identifier even when
# every value happens to be digits, and arithmetic on it is meaningless.
IDENTIFIER_NAME_HINTS = (
    "id",
    "uuid",
    "guid",
    "key",
    "code",
    "ref",
    "sku",
    "isbn",
    "zip",
    "postal",
    "cep",
    "phone",
    "invoice",
    "account",
    "barcode",
)

_DATE_LIKE = re.compile(r"^\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}([ T].*)?$|^\s*\d{1,2}[ -][A-Za-z]{3}")
_NUMERIC_LIKE = re.compile(r"^\s*[-+]?[\d\s,.']*\d([eE][-+]?\d+)?\s*$")
_SEPARATED = re.compile(r"^\s*(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})")
_THOUSANDS = r"[\s,']"
_LEADING_ZERO = re.compile(r"^\s*0\d")


class ColumnInference(BaseModel):
    """What was decided for one column, and on what evidence."""

    column: str
    action: str  # keep | parse_datetime | cast_numeric
    target_type: str | None = None
    format: str | None = None
    parse_rate: float | None = None
    sample_size: int = 0
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reason: str = ""


class SchemaInference(BaseModel):
    table_name: str
    columns: list[ColumnInference] = Field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        return [f"{c.column}: {w}" for c in self.columns for w in c.warnings]

    def by_column(self, name: str) -> ColumnInference | None:
        return next((c for c in self.columns if c.column == name), None)


def _string_sample(series: pl.Series, limit: int = SAMPLE_SIZE) -> pl.Series:
    """Evenly spread sample, so a sorted column is not judged by its first page."""
    values = series.drop_nulls().cast(pl.Utf8, strict=False).drop_nulls()
    if values.len() <= limit:
        return values
    step = max(1, values.len() // limit)
    return values.gather_every(step).head(limit)


def _looks_like(sample: pl.Series, pattern: re.Pattern[str], threshold: float = 0.8) -> bool:
    if sample.len() == 0:
        return False
    head = sample.head(200).to_list()
    hits = sum(1 for v in head if v is not None and pattern.match(v))
    return hits / len(head) >= threshold


def _ordering_evidence(sample: pl.Series) -> tuple[bool, bool]:
    """Inspect the numeric date components directly.

    Returns (day_first_proven, month_first_proven). A first component above 12
    can only be a day; a second component above 12 can only be a day. Either
    observation settles day-first vs month-first without relying on parse-rate
    luck.
    """
    day_first = month_first = False
    for value in sample.head(5_000).to_list():
        if value is None:
            continue
        match = _SEPARATED.match(value)
        if not match:
            continue
        first, second, third = match.groups()
        if len(first) == 4:  # year-first, not ambiguous
            continue
        if len(third) not in (2, 4):
            continue
        if int(first) > 12:
            day_first = True
        if int(second) > 12:
            month_first = True
        if day_first and month_first:
            break
    return day_first, month_first


def _counterpart(fmt: str) -> str | None:
    if fmt in MONTH_FIRST:
        return fmt.replace("%m/%d", "%d/%m").replace("%m-%d", "%d-%m")
    if fmt in DAY_FIRST:
        return fmt.replace("%d/%m", "%m/%d").replace("%d-%m", "%m-%d")
    return None


def infer_datetime_format(
    sample: pl.Series,
) -> tuple[str | None, float, list[dict[str, Any]], list[str]]:
    """Score every candidate format against the sample.

    Returns (best_format, parse_rate, rejected_candidates, warnings).
    """
    if sample.len() == 0:
        return None, 0.0, [], []

    day_first_proven, month_first_proven = _ordering_evidence(sample)
    warnings: list[str] = []
    excluded: set[str] = set()
    if day_first_proven and not month_first_proven:
        excluded = MONTH_FIRST
    elif month_first_proven and not day_first_proven:
        excluded = DAY_FIRST
    elif day_first_proven and month_first_proven:
        warnings.append(
            "Both day-first and month-first evidence present; the column mixes date conventions."
        )

    total = sample.len()
    scored: list[tuple[str, float]] = []
    for fmt in DATETIME_FORMATS:
        if fmt in excluded:
            continue
        parsed = sample.str.to_datetime(fmt, strict=False)
        rate = (total - parsed.null_count()) / total
        if rate > 0:
            scored.append((fmt, rate))
        if rate == 1.0:
            break  # candidates are ordered; a perfect early match wins

    if not scored:
        return None, 0.0, [], warnings

    scored.sort(key=lambda item: item[1], reverse=True)
    best_format, best_rate = scored[0]

    if not (day_first_proven or month_first_proven):
        counterpart = _counterpart(best_format)
        if counterpart:
            counter_rate = next((r for f, r in scored if f == counterpart), None)
            if counter_rate is None:
                # The scoring loop stops at the first perfect match, so the
                # opposite ordering may never have been tried. It has to be,
                # or a fully ambiguous column is reported as certain.
                counter_parsed = sample.str.to_datetime(counterpart, strict=False)
                counter_rate = (total - counter_parsed.null_count()) / total
                if counter_rate > 0:
                    scored.append((counterpart, counter_rate))
            if abs(counter_rate - best_rate) < 1e-9:
                warnings.append(
                    f"Ambiguous date order: every sampled value also parses as {counterpart}. "
                    "No value exceeds 12 in either position, so the order cannot be proven "
                    "from the data alone."
                )

    rejected = [{"format": fmt, "parse_rate": round(rate, 4)} for fmt, rate in scored[1:6]]
    return best_format, best_rate, rejected, warnings


def _numeric_parse_rate(sample: pl.Series) -> tuple[float, bool]:
    """Parse rate for a numeric cast. Second element: whether stripping helped."""
    total = sample.len()
    if total == 0:
        return 0.0, False
    direct = sample.cast(pl.Float64, strict=False)
    direct_rate = (total - direct.null_count()) / total
    cleaned = sample.str.replace_all(_THOUSANDS, "").cast(pl.Float64, strict=False)
    cleaned_rate = (total - cleaned.null_count()) / total
    if cleaned_rate > direct_rate:
        return cleaned_rate, True
    return direct_rate, False


def _identifier_named(name: str) -> bool:
    lowered = name.lower()
    tokens = set(re.split(r"[^a-z0-9]+", lowered))
    if tokens & {"no", "nr", "num"}:
        return True
    return any(hint in lowered for hint in IDENTIFIER_NAME_HINTS)


def _has_leading_zeros(sample: pl.Series) -> bool:
    """Leading zeros carry meaning in codes and are erased by a numeric cast."""
    return any(
        value is not None and _LEADING_ZERO.match(value) for value in sample.head(2_000).to_list()
    )


def infer_and_apply(frame: pl.DataFrame, table_name: str) -> tuple[pl.DataFrame, SchemaInference]:
    """Re-type string columns that are provably dates or numbers.

    Columns that do not clear MIN_PARSE_RATE are left untouched, so the quality
    agent reports them as a problem instead of the loader hiding them as nulls.
    """
    inference = SchemaInference(table_name=table_name)
    expressions: list[pl.Expr] = []

    for name in frame.columns:
        series = frame[name]
        if series.dtype not in (pl.Utf8, pl.String):
            inference.columns.append(
                ColumnInference(
                    column=name,
                    action="keep",
                    target_type=str(series.dtype),
                    reason="Source already provides a non-string type.",
                )
            )
            continue

        sample = _string_sample(series)
        if sample.len() == 0:
            inference.columns.append(
                ColumnInference(
                    column=name,
                    action="keep",
                    target_type="String",
                    reason="Column is entirely null.",
                )
            )
            continue

        if _looks_like(sample, _DATE_LIKE):
            fmt, rate, rejected, warnings = infer_datetime_format(sample)
            if fmt and rate >= MIN_PARSE_RATE:
                if rate < 1.0:
                    warnings = warnings + [
                        f"{(1 - rate):.2%} of sampled values do not match {fmt} and become null. "
                        "Any series built on this column is computed on the remainder."
                    ]
                expressions.append(pl.col(name).str.to_datetime(fmt, strict=False).alias(name))
                inference.columns.append(
                    ColumnInference(
                        column=name,
                        action="parse_datetime",
                        target_type="Datetime",
                        format=fmt,
                        parse_rate=round(rate, 6),
                        sample_size=sample.len(),
                        rejected=rejected,
                        warnings=warnings,
                        reason=f"{rate:.2%} of sampled values parse as {fmt}.",
                    )
                )
                continue
            inference.columns.append(
                ColumnInference(
                    column=name,
                    action="keep",
                    target_type="String",
                    format=fmt,
                    parse_rate=round(rate, 6) if fmt else None,
                    sample_size=sample.len(),
                    rejected=rejected,
                    warnings=warnings
                    + [
                        f"Looks like a date but no format reaches {MIN_PARSE_RATE:.0%} "
                        f"(best {fmt or 'none'} at {rate:.2%}); kept as text rather than "
                        "discarding values."
                    ],
                    reason="No candidate format was conclusive.",
                )
            )
            continue

        if _looks_like(sample, _NUMERIC_LIKE):
            rate, stripped = _numeric_parse_rate(sample)
            blockers: list[str] = []
            if _identifier_named(name):
                blockers.append(
                    "the name denotes a key or code, so its digits are an identity, not a quantity"
                )
            if _has_leading_zeros(sample):
                blockers.append("values carry leading zeros that a numeric cast would erase")
            if rate < MIN_NUMERIC_CAST_RATE:
                blockers.append(
                    f"only {rate:.2%} of sampled values are numeric, so a cast would discard the rest"
                )

            if not blockers:
                column = pl.col(name)
                if stripped:
                    column = column.str.replace_all(_THOUSANDS, "")
                expressions.append(column.cast(pl.Float64, strict=False).alias(name))
                inference.columns.append(
                    ColumnInference(
                        column=name,
                        action="cast_numeric",
                        target_type="Float64",
                        parse_rate=round(rate, 6),
                        sample_size=sample.len(),
                        reason="Every sampled value is numeric"
                        + (" once thousands separators are removed." if stripped else "."),
                    )
                )
                continue

            inference.columns.append(
                ColumnInference(
                    column=name,
                    action="keep",
                    target_type="String",
                    parse_rate=round(rate, 6),
                    sample_size=sample.len(),
                    warnings=[
                        "Digits kept as text because " + "; ".join(blockers) + "."
                    ]
                    if rate < MIN_NUMERIC_CAST_RATE
                    else [],
                    reason="Numeric-looking, but kept as text: " + "; ".join(blockers) + ".",
                )
            )
            continue

        inference.columns.append(
            ColumnInference(
                column=name,
                action="keep",
                target_type="String",
                sample_size=sample.len(),
                reason="No provable temporal or numeric interpretation.",
            )
        )

    if expressions:
        frame = frame.with_columns(expressions)
    return frame, inference

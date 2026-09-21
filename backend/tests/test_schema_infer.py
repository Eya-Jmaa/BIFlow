"""Type inference is where a BI pipeline silently loses data.

These tests exist because the loader once passed ``try_parse_dates=True`` to
Polars on a M/D/Y file: the format was inferred from the first rows, every row
whose day exceeded 12 failed to parse, and 57% of a 541,909-row dataset became
null without a single warning. Every trend in the product was then computed on
the surviving 43%.
"""

from __future__ import annotations

import polars as pl
import pytest

from app.data.schema_infer import infer_and_apply, infer_datetime_format


def test_month_first_dates_are_resolved_from_the_data():
    # 3/25 can only be month-first: there is no 25th month.
    sample = pl.Series(["12/1/2010 8:26", "3/25/2011 14:05", "7/31/2011 9:00"])
    fmt, rate, _rejected, warnings = infer_datetime_format(sample)
    assert fmt == "%m/%d/%Y %H:%M"
    assert rate == 1.0
    assert warnings == []


def test_day_first_dates_are_resolved_from_the_data():
    sample = pl.Series(["25/12/2010 8:26", "13/4/2011 14:05", "5/6/2011 9:00"])
    fmt, rate, _rejected, warnings = infer_datetime_format(sample)
    assert fmt == "%d/%m/%Y %H:%M"
    assert rate == 1.0
    assert warnings == []


def test_unprovable_date_order_is_reported_not_guessed_silently():
    # Every component is <= 12, so both orderings parse every value. The
    # pipeline still has to pick one, but it must say that it could not prove it.
    sample = pl.Series(["01/02/2020", "03/04/2020", "05/06/2020"])
    fmt, rate, _rejected, warnings = infer_datetime_format(sample)
    assert fmt is not None and rate == 1.0
    assert any("Ambiguous date order" in warning for warning in warnings)


def test_dates_are_not_silently_dropped_by_a_wrong_format():
    frame = pl.DataFrame(
        {"InvoiceDate": ["12/1/2010 8:26", "12/9/2011 12:50", "7/31/2011 9:00", "1/12/2011 14:05"]}
    )
    typed, inference = infer_and_apply(frame, "t")
    assert typed["InvoiceDate"].null_count() == 0
    decision = inference.by_column("InvoiceDate")
    assert decision is not None and decision.action == "parse_datetime"
    assert decision.parse_rate == 1.0


def test_identifier_columns_keep_their_digits():
    # Casting InvoiceNo to a float would null every cancellation document and
    # turn an identity into a quantity.
    frame = pl.DataFrame({"InvoiceNo": ["536365", "536366", "C536379", "536380"]})
    typed, inference = infer_and_apply(frame, "t")
    assert typed["InvoiceNo"].dtype == pl.String
    assert typed.filter(pl.col("InvoiceNo").str.starts_with("C")).height == 1
    assert inference.by_column("InvoiceNo").action == "keep"


def test_leading_zeros_are_never_cast_away():
    frame = pl.DataFrame({"postal": ["01234", "00567", "09876"]})
    typed, inference = infer_and_apply(frame, "t")
    assert typed["postal"].to_list() == ["01234", "00567", "09876"]
    assert "leading zeros" in inference.by_column("postal").reason


def test_a_partially_numeric_column_is_reported_rather_than_coerced():
    frame = pl.DataFrame({"amount_paid": ["1.5", "2.5", "n/a", "4.0"]})
    typed, inference = infer_and_apply(frame, "t")
    # Coercing would discard "n/a" as null and hide a real data problem.
    assert typed["amount_paid"].dtype == pl.String
    assert inference.by_column("amount_paid").action == "keep"


def test_clean_numeric_columns_are_cast_with_separators_removed():
    frame = pl.DataFrame({"revenue": ["1,234.50", "2,000", "3.25"]})
    typed, inference = infer_and_apply(frame, "t")
    assert typed["revenue"].to_list() == [1234.5, 2000.0, 3.25]
    assert inference.by_column("revenue").action == "cast_numeric"


@pytest.mark.parametrize(
    "values",
    [
        ["2011-01-02 03:04:05", "2011-06-07 08:09:10"],
        ["2011-01-02T03:04:05", "2011-06-07T08:09:10"],
        ["2011-01-02T03:04:05.123", "2011-06-07T08:09:10.456"],
        ["2011-01-02", "2011-06-07"],
    ],
)
def test_iso_formats_parse_to_the_right_instants(values):
    """The chosen format string is an implementation detail; the parsed value is not."""
    fmt, rate, _rejected, _warnings = infer_datetime_format(pl.Series(values))
    assert fmt is not None and rate == 1.0
    parsed = pl.Series(values).str.to_datetime(fmt, strict=False)
    assert parsed.null_count() == 0
    assert parsed[0].year == 2011 and parsed[0].month == 1 and parsed[0].day == 2
    assert parsed[1].month == 6 and parsed[1].day == 7

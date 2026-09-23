# Source dataset — UCI Online Retail

The dataset BIFlow is demonstrated on. It is the **only** dataset this project
uses; every figure in the README, the demo script and `tests/test_real_dataset.py`
comes from it.

## Provenance

| | |
| --- | --- |
| **Source** | UCI Machine Learning Repository, *Online Retail* (ID 352) |
| **URL** | <https://archive.ics.uci.edu/dataset/352/online+retail> |
| **Donated by** | Dr Daqing Chen, London South Bank University |
| **Licence** | CC BY 4.0 — free to use with attribution |
| **Domain** | E-commerce / retail (spec §6) |
| **Period covered** | 2010-12-01 → 2011-12-09 |
| **Size** | 541,909 rows × 8 columns |

A UK-based, registered non-store online retailer selling giftware, mostly to
wholesalers. One row is one invoice line.

```bash
python scripts/download_demo_data.py    # downloads and extracts into data/raw/
```

The original file is never modified. BIFlow keeps it in the RAW layer and writes
derived Parquet under `data/processed/{run_id}/`.

## Schema, as the Data Profiler reads it

| Column | Storage type | Logical type | Null % | Distinct | Bound role |
| --- | --- | --- | --- | --- | --- |
| `InvoiceNo` | String | categorical | 0.00% | 25,900 | `order_id` |
| `StockCode` | String | categorical | 0.00% | 4,070 | `product_id` |
| `Description` | String | categorical | 0.27% | 4,224 | `description` |
| `Quantity` | Int64 | quantity | 0.00% | 722 | `quantity` |
| `InvoiceDate` | Datetime | datetime | 0.00% | 23,260 | `event_date` |
| `UnitPrice` | Float64 | currency | 0.00% | 1,630 | `unit_price` |
| `CustomerID` | Int64 | numeric | 24.93% | 4,373 | `customer_id` |
| `Country` | String | geo | 0.00% | 38 | `geo` |

Nothing in this mapping is hard-coded. The profiler binds roles from column
names, logical types and cardinality, and records a confidence score and its
reasoning for each — visible on the **03 Model** screen.

## Known quirks, and how BIFlow handles them

This file is a good demonstration precisely because it is messy in ways that
break naive pipelines.

**Dates are `M/D/YYYY H:MM`, not `D/M/YYYY`.** Letting a library infer the
format produces `%d/%m/%Y`, which silently nulls every row whose day exceeds 12
— 308,950 of 541,909. BIFlow resolves the ordering from the data (a value above
12 in the second position can only be a day), records the chosen format and its
100% parse rate, and reports the rejected candidates.

**Cancellations are encoded twice.** 9,288 rows carry an `InvoiceNo` prefixed
with `C`, and 10,624 rows have a negative `Quantity`. Both conventions are
detected. Gross revenue, net revenue, returned value and return rate are
published as separate KPIs rather than blended into one figure.

**`InvoiceNo` and `StockCode` look numeric but are not.** 98.19% and 89.84% of
their values parse as numbers. Casting either would destroy the cancellation
documents and any leading zeros, so both are kept as text and the decision is
reported as a quality issue.

**`CustomerID` is 24.93% null.** Guest checkouts. It is reported, not imputed;
`COUNT(DISTINCT)` excludes nulls, so customer counts are of identified
customers only.

**5,268 exact duplicate rows.** Removed by the ETL agent, with the count and
reason recorded in the transformation lineage.

**The last month is incomplete.** The extract stops on 9 December 2011, so
December is a partial month. Comparing it against a full November would show a
collapse in every metric at once; it is flagged and excluded from
period-over-period comparisons, trend fits, anomaly tests and seasonality.

**Two negative `UnitPrice` values** ("Adjust bad debt"). Flagged as impossible
values for a currency column, not silently dropped.

## Ground truth

Computed directly from the source file with Polars, independently of the
pipeline, and asserted in `backend/tests/test_real_dataset.py`:

| Figure | Value |
| --- | --- |
| Net Revenue | 9,747,747.93 |
| Gross Revenue | 10,644,560.42 |
| Returned Value | −896,812.49 |
| Orders (excl. cancellations) | 22,064 |
| Cancelled Orders | 3,836 |
| Unique Customers | 4,372 |
| Average Order Value | 482.44 |

Gross + Returned = Net exactly, and Orders + Cancelled = the 25,900 distinct
documents in the file. Those identities are the check that matters: the numbers
reconcile because they come from one semantic layer, not from independent
queries.

## Other sources

The spec (§7) lists several alternatives — Olist, AdventureWorks, Telco Churn,
NYC Taxi. BIFlow is dataset-agnostic and will run on any of them without code
changes, but **only UCI Online Retail is used in this project**, so only it is
documented here.

Note that a single-table source leaves join discovery largely unexercised: the
profiler validates relationships by value overlap, type compatibility and
uniqueness, and with one table there is nothing to join. A multi-table source
such as Olist would exercise that path.

# BIFlow architecture

## System

```
┌────────────┐     REST / SSE      ┌────────────────┐     RQ      ┌─────────────────┐
│  Next.js   │ ◄──────────────────► │    FastAPI     │ ──────────► │  Worker / RQ    │
│  frontend  │                      │  API + events  │             │  LangGraph run  │
└────────────┘                      └───────┬────────┘             └────────┬────────┘
                                            │                               │
                                            ▼                               ▼
                                     ┌────────────┐                 ┌──────────────┐
                                     │ PostgreSQL │                 │ Polars/DuckDB│
                                     │  metadata  │                 │  analytics   │
                                     └────────────┘                 └──────────────┘
                                            ▲
                                     ┌────────────┐
                                     │   Redis    │
                                     │ jobs+events│
                                     └────────────┘
```

The frontend never computes a KPI. It renders artefacts a run persisted, and for
interactive slices it calls an endpoint that recompiles the stored formula server-side.

PostgreSQL and Redis are the production choices, not requirements. Column types are
declared through `app/db/types.py`, which maps to `JSONB`/`uuid` on PostgreSQL and to
`JSON`/`CHAR(36)` elsewhere, so the schema also runs on SQLite; the event bus falls back
to a bounded in-process buffer when Redis is unreachable. Both fallbacks exist so the
pipeline can be demonstrated end to end without infrastructure.

## The agent graph

`app/agents/graph_def.py` owns control flow. `app/pipeline/executor.py` owns the work and
knows nothing about routing.

```
START → orchestrator → profiler → quality → semantic → analyst → dashboard → auditor → publish → END
                                     ▲          ▲                               │
                                     └──────────┴───────────────────────────────┘
                                          auditor feedback edges
```

The auditor returns one of four verdicts:

| Verdict | Condition | Next |
| --- | --- | --- |
| `VALID` | KPI success ratio ≥ 60%, quality ≥ 55, dashboard bound | `publish` |
| `retry_semantic` | Too few KPIs computed | `semantic` |
| `retry_quality` | Data too poor to publish | `quality` |
| `INVALID` | No widgets could be produced | `publish`, unpublished |

Two properties make this work in practice:

**The retry budget is consumed inside the node, not the edge.** LangGraph merges the
state a *node* returns; a counter incremented inside a conditional-edge function is
discarded. The auditor therefore decides, records the decision in the state it returns,
and the routing function only reads the verdict. Getting this wrong produces an infinite
loop that terminates at the recursion limit — there is a regression test for it.

**Every agent is idempotent.** Because the auditor can send a run back, an agent may
execute more than once within one run. Each clears its own artefacts for that run before
writing new ones, so three passes through the semantic agent leave one semantic model and
one KPI catalog, not three.

When a budget is exhausted the run publishes with its caveats attached. A labelled
partial result is more useful to an analyst than no result.

| Agent | Deterministic engine | LLM role (optional) |
| --- | --- | --- |
| Orchestrator | Domain inference from objective + columns | Plan summary, risks |
| Profiler | Polars statistics, PII, join discovery, role binding | Interpret warnings |
| Quality / ETL | Five-axis scorecard, allowed transforms only | Plan notes |
| Semantic / KPI | Role binding → catalog → formula compiler → DuckDB | Propose extra KPIs |
| Analyst | Trend, z-score, IQR, seasonality, Pareto, correlation | Word insights from evidence |
| Dashboard | Widget spec bound to computed metrics | Layout suggestions |
| Auditor | Formula, SQL and binding checks | Validation narrative |

## Data layers

1. **RAW** — uploaded files, never mutated
2. **CLEANED** — Parquet written after recorded transformations, one directory per run
3. **ANALYTICAL** — DuckDB views over that Parquet; all KPI SQL executes here

Join candidates require value overlap, type compatibility *and* uniqueness. Name
similarity alone is never sufficient.

## Type inference

`app/data/schema_infer.py`. A silent type guess is the most dangerous step in the
pipeline, because it fails without raising.

1. Sample non-null values evenly across the column, so a sorted column is not judged by
   its first page.
2. For date-shaped columns, inspect the numeric components first: a value above 12 in the
   first position proves day-first, in the second position proves month-first. That
   settles the ordering from the data rather than from parse-rate luck.
3. Score the surviving candidate formats and take the best, requiring ≥ 95% parse rate.
4. If neither ordering can be proven, choose one and attach an ambiguity warning that
   becomes a high-severity quality issue.
5. Numeric casts are held to a stricter bar: nothing may be lost, the column name must not
   denote a key or code, and the values must carry no leading zeros.

Every decision — action, format, parse rate, rejected alternatives, reasoning — is stored
on the column profile and surfaced through the auditor and the evaluation report.

## Semantic layer

`app/analytics/roles.py` binds business roles to physical columns using the profile, not
just names: a column called `total` that is unique per row is a key, not a measure. Each
binding carries a confidence score and its reasoning.

`app/analytics/kpi_catalog.py` declares KPIs against those roles. A template is
instantiated only when every role it needs is bound, so a dataset with no cost column
produces no margin KPI. Where a cancellation convention is detected — negative quantities
or a letter-prefixed document number — the catalog publishes gross, net, returned value
and return rate separately, and excludes cancellation documents from order counts and
average order value.

## KPI formula grammar

`app/analytics/kpi_engine.py`.

```
kpi        := expr
expr       := term (('+' | '-') term)*
term       := factor (('*' | '/') factor)*
factor     := '-' factor | aggregate | number | '(' expr ')'
aggregate  := NAME '(' ('*' | rowexpr) ['WHERE' condition] ')'
rowexpr    := arithmetic over columns and literals, evaluated per row
condition  := comparisons, IS [NOT] NULL, [NOT] LIKE, [NOT] IN, AND/OR/NOT
```

Row-level arithmetic inside an aggregate is the point: revenue on a transaction table is
`SUM(quantity * unit_price)`, which the previous grammar could not express.

The compiler:

- resolves every column against the run's real schema, so an invented column raises at
  compile time instead of producing a plausible number
- quotes every identifier and escapes every literal
- guards division, so a zero denominator is `NULL` rather than an error
- classifies additivity (`additive` / `semi_additive` / `non_additive`), which decides
  whether a share-of-total statement may be made about the metric
- exposes `grouped_sql()` so breakdowns and time series reuse the same select expression
  as the headline value, instead of rewriting the query text

## Analysis

Statistics run on complete periods only. The final bucket of a series is flagged partial
when the data stops more than one unit of resolution before the period ends; it is drawn
hollow, excluded from period-over-period comparison, trend fitting, anomaly tests and
seasonality, and named in the insight text.

Insights are scored by category, severity, confidence and effect size, capped per metric
and de-duplicated, because sixty mechanical observations are not an analysis.

## Interactive queries

`POST /api/projects/{id}/query` recompiles the stored formula and appends predicates built
from a whitelisted filter grammar (`eq`, `in`, `between`, `contains`, …). The browser
never sends SQL. Columns are validated against the run's schema, literals are escaped, and
the finished statement still passes the read-only validator. The SQL is returned with the
result so any number on the dashboard can be traced.

## SQL safety

`app/security/sql.py` validates the parsed syntax tree, not the query text. Regexes over
raw SQL cannot distinguish a `DROP` statement from a customer in "Drop City", and miss
attacks hidden by comments or casing. The validator requires a single `SELECT`/`WITH`/
`UNION`, rejects every write or DDL node — including `Command`, where sqlglot parks
`PRAGMA`, `ATTACH`, `INSTALL` and anything else it does not model — and blocks DuckDB's
file-reading functions.

## LLM interaction

- Provider selected by `LLM_PROVIDER`; JSON-object responses only
- Datasets are never sent in full — schema, statistics and compact evidence only
- A proposed KPI is compiled against the real schema before it is accepted
- A proposed insight is kept only if its metric and value match a computed one within 5%
- Token usage and latency are recorded per agent run
- With no key configured every `interpret_*` call returns `None` and the run proceeds
  deterministically; `GET /health` reports why

## Evaluation

Each run scores its agents into `evaluation_results`: KPI formula validity, insight
groundedness, profiler coverage, type-inference resolution, auditor confidence, and a
comparison against a naive baseline — one `SUM`/`AVG` per numeric column, which is what a
non-agentic script produces and which cannot express revenue, average order value or
return rate at all.

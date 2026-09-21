# BIFlow

A multi-agent Business Intelligence pipeline: give it a raw dataset and a business
objective, and seven agents profile the data, fix what they can, infer a semantic model,
build and compute a KPI catalog, analyse the results, generate a dashboard, and audit
every number back to the SQL that produced it.

```
RAW DATA → PROFILER → QUALITY / ETL → SEMANTIC → KPI ENGINE → ANALYST → DASHBOARD → AUDIT / XAI
```

**No number shown to a user is produced by a language model.** Polars, DuckDB and a
validated SQL grammar compute every value. The LLM, when configured, reads evidence the
tools computed and proposes structure — an extra KPI, a phrasing, a widget layout — and
every proposal is re-checked against the real schema or the real computed values before
it can reach the screen. With no API key set, the pipeline produces the same numbers.

## What the agents do

| Agent | Responsibility |
| --- | --- |
| **BI Orchestrator** | Infers the business domain, plans the run, records the configuration |
| **Data Profiler** | Types, statistics, missingness, duplicates, PII, join discovery, business-role binding |
| **Data Quality / ETL** | Scores quality on five axes, applies only conservative recorded transformations |
| **Semantic / KPI** | Builds the dimension/measure model and instantiates the domain KPI catalog |
| **BI Analyst** | Trend, anomaly, seasonality, Pareto, concentration and correlation; ranks the findings |
| **Dashboard Generator** | Chooses widgets and binds each to a computed metric |
| **BI Auditor / XAI** | Validates every artefact, explains it, and decides whether the run may publish |

The orchestration is a real [LangGraph](https://langchain-ai.github.io/langgraph/) state
graph, not a sequence of calls. The auditor's verdict can route the run **back** to the
quality or semantic agent; each feedback edge is bounded by `PIPELINE_MAX_RETRIES`, and
when a budget is spent the run publishes with its caveats attached rather than looping or
discarding the work. Every agent is idempotent, because it can execute more than once in
a single run. See [docs/architecture.md](docs/architecture.md).

## Design decisions that matter

**Type inference is evidence-based and auditable.** The loader never asks a library to
guess a date format. It scores explicit candidate formats against a spread sample,
resolves day-first vs month-first from the data itself (a value above 12 in either
position settles it), requires a 95% parse rate, and records the chosen format, its parse
rate and the rejected alternatives. When no ordering can be proven, it says so rather than
picking one silently. A numeric cast is held to a stricter bar still — it must lose
nothing, and it never touches a column whose name denotes a key or whose values carry
leading zeros.

**The KPI grammar can express real business metrics.** Aggregates take row-level
expressions and optional filters, so revenue is `SUM(quantity * unit_price)`, not the sum
of a price column. Formulas compile to parameter-free, fully quoted DuckDB SQL; every
column is checked against the real schema at compile time, so an invented column fails
with a readable message instead of becoming a plausible wrong number.

```
SUM(sales.quantity * sales.unit_price WHERE sales.invoice_no NOT LIKE 'C%')
  / COUNT_DISTINCT(sales.invoice_no WHERE sales.invoice_no NOT LIKE 'C%')
```

**KPIs are declared against business roles, not column names.** The profiler binds roles
(`quantity`, `unit_price`, `order_id`, `customer_id`, `event_date`, `geo`, …) to columns
with a confidence score and its reasoning. The catalog is written against those roles and
instantiates only the KPIs whose roles were actually bound — a dataset without a cost
column yields no margin KPI rather than a fabricated one.

**Returns are business facts, not dirt.** Negative quantities and cancellation-prefixed
document numbers are detected, and gross revenue, net revenue, returned value and return
rate are published separately, because a single blended figure hides whether a soft
quarter was weak selling or heavy returns.

**Incomplete periods are never compared against complete ones.** An extract that stops
on the 9th of a month makes that month look like a collapse in every metric at once. The
final bucket is flagged, excluded from period-over-period comparisons, trend fits,
anomaly tests and seasonality, and drawn hollow on the chart.

**Shares are only claimed where they mean something.** Each KPI is classified as
additive, semi-additive or non-additive. "The UK is 85% of revenue" is a valid statement;
"Singapore is 48% of average unit price" is not, and is never generated.

## Quick start

### Docker (full stack)

```bash
cp .env.example .env
docker compose up --build
```

Then open <http://localhost:3000>. API docs at <http://localhost:8000/docs>.

### Without Docker

PostgreSQL and Redis are optional. The schema runs on SQLite, and the event bus falls
back to an in-process buffer, so the whole pipeline can be demonstrated on a laptop:

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
DATABASE_URL="sqlite:///./biflow.db" uvicorn app.main:app --port 8000

cd ../frontend
npm install && npm run dev
```

## Demo

```bash
python scripts/download_demo_data.py    # fetches UCI Online Retail
```

1. Create a project, for example **E-Commerce BI Analysis**.
2. Set the objective: *Analyse e-commerce sales performance, customer behaviour, product
   mix and revenue evolution across countries.*
3. Upload the dataset and click **Run pipeline**.
4. Watch the agents complete on the Pipeline screen, then work through Data Quality,
   Semantic Model, KPIs, Insights, Dashboard, Audit/XAI and Lineage.
5. On the Dashboard, filter by period and country — every tile re-queries the same slice —
   and use **Explore** on any metric to break it down and read the SQL that produced it.

On the real UCI file (541,909 rows) the run takes about 8 seconds and produces 14 KPIs.
The headline figures are pinned in `tests/test_real_dataset.py`:

| KPI | Value |
| --- | --- |
| Net Revenue | 9,747,747.93 |
| Gross Revenue | 10,644,560.42 |
| Returned Value | −896,812.49 |
| Orders | 22,064 |
| Cancelled Orders | 3,836 |
| Unique Customers | 4,372 |
| Average Order Value | 482.44 |

A second, unrelated schema runs through the same agents without code changes.

## Tests

```bash
cd backend && pytest -q
```

95 tests. They cover date-format resolution and the value-loss guards, the formula
grammar and its rejection of invented columns and injected SQL, additivity
classification, KPI catalog reconciliation (gross − returns = net), partial-period
handling, insight ranking, the read-only SQL validator, LLM output grounding, and the
agent graph end to end — including that the auditor's feedback edge fires, that the retry
budget terminates it, and that re-running an agent does not duplicate its artefacts.

`tests/test_real_dataset.py` asserts the exact figures above against the real UCI file and
skips when it is absent.

## Configuration

See `.env.example`. The keys that change behaviour:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL or SQLite |
| `REDIS_URL` | Event bus and job queue; optional |
| `LLM_PROVIDER` | `openai`, `groq` or `local` — **must match the key you set** |
| `OPENAI_API_KEY` / `GROQ_API_KEY` | Never sent to the frontend |
| `LLM_ENABLED` | `false` runs fully deterministically |
| `PIPELINE_MAX_RETRIES` | Bound on each auditor feedback edge |
| `DATA_DIR`, `MAX_UPLOAD_MB` | Storage and upload limits |

`GET /health` reports whether the LLM is active and, if not, why — a provider that does
not match the key you set is otherwise invisible, since every agent simply falls back to
deterministic output.

## Security

- Generated SQL is parsed with sqlglot and rejected unless it is a single read-only
  `SELECT`; validation inspects the syntax tree, not the query text, so a customer in
  "Drop City" is not mistaken for a `DROP` statement and a comment cannot smuggle one past
- Dashboard filters are a whitelisted grammar, never user SQL: columns are checked against
  the run's schema, literals are escaped, and DuckDB's file-reading functions are blocked
- Uploads are type- and size-validated with path-traversal protection
- Datasets are never sent to the LLM in full — schema, statistics and compact evidence only
- Secrets stay in environment variables; CORS and rate limiting are enabled

## Limitations

- Large files are profiled with Polars and DuckDB but still need adequate worker memory
- Map widgets render only when a geographic dimension and widget data both exist
- Authentication is modelled (`users` table) but the demo API is open on the local network
- Role binding is heuristic; the Semantic Model screen shows every binding and its
  confidence so a wrong one can be spotted
- A date column whose ordering cannot be proven is parsed under a stated assumption and
  raised as a high-severity quality issue, not resolved automatically

## License

Application code is provided for this project. Third-party datasets remain under their
original licenses.

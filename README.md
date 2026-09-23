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

## Running it

You need **Python 3.11+** and **Node 20+**. PostgreSQL, Redis and Docker are all
optional — the schema runs on SQLite and the event bus falls back to an in-process
buffer, so the whole pipeline works on a laptop with nothing else installed.

### Option A — no Docker (fastest)

Two terminals.

**Terminal 1 — API**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate             # Windows
# source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt

# SQLite keeps everything in one file; delete it to start clean.
DATABASE_URL="sqlite:///./biflow.db" uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, set the variable first:

```powershell
$env:DATABASE_URL = "sqlite:///./biflow.db"
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — web app**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. API docs are at <http://localhost:8000/docs>.

### Option B — Docker (Postgres + Redis + worker)

```bash
cp .env.example .env
docker compose up --build
```

Same URLs. Use this when you want the queue and the multi-process event stream.

### First run

1. Get the demo dataset: `python scripts/download_demo_data.py`
   (or bring any CSV, Parquet or Excel file).
2. Create a project on the home page — the default objective is already filled in.
3. Open **Datasets**, drop the file in.
4. Click **Run pipeline** in the header. It takes about 8 seconds on the 541k-row
   UCI file; the Pipeline screen shows each agent as it completes.
5. Work through the pipeline: 01 Profile → 02 Clean → 03 Model → 04 Measure →
   05 Analyze → 06 Visualize → 07 Audit. Press ⌘K / Ctrl-K anywhere to jump.

### Tests

```bash
cd backend && pytest -q          # 127 tests
cd frontend && npx tsc --noEmit  # type check
```

### Troubleshooting

| Symptom | Cause |
| --- | --- |
| "Cannot reach the API" in the browser | The backend is not running, or not on port 8000. `NEXT_PUBLIC_API_URL` overrides the default. |
| `redis_unavailable_using_memory_events` in the log | Expected without Redis. Events fall back to an in-process buffer; the pipeline is unaffected. |
| Pipeline finishes but the dashboard is empty | The run produced no computed KPIs — check **Audit / XAI** for the verdict and its reasoning. |
| "LLM interpretation is off" at startup | `LLM_PROVIDER` does not match the API key you set. The message names the fix. Deterministic output is unaffected. |

## What it produces

On the real UCI Online Retail file (541,909 rows) a run takes about 8 seconds and
produces 14 KPIs. These figures were computed independently of the pipeline and are
asserted in `backend/tests/test_real_dataset.py`:

| KPI | Value |
| --- | --- |
| Net Revenue | 9,747,747.93 |
| Gross Revenue | 10,644,560.42 |
| Returned Value | -896,812.49 |
| Orders | 22,064 |
| Cancelled Orders | 3,836 |
| Unique Customers | 4,372 |
| Average Order Value | 482.44 |

Gross + Returned = Net exactly, and Orders + Cancelled Orders = the 25,900 distinct
documents in the file. Those identities are the point: the numbers reconcile rather than
being independent guesses.

A second, unrelated schema runs through the same agents with no code changes. Where no
business role matches, the catalog falls back to plainly labelled sums and averages
instead of dressing them up as revenue.

[docs/demo.md](docs/demo.md) is a ten-minute walkthrough that shows the agents
disagreeing, not just the output.

### What the tests cover

127 tests: date-format resolution and the value-loss guards, the formula grammar and its
rejection of invented columns and injected SQL, additivity classification, KPI catalog
reconciliation, partial-period handling, insight ranking, the read-only SQL validator,
LLM output grounding, agent evaluation metrics, and the agent graph end to end —
including that the auditor's feedback edge fires, that the retry budget terminates it,
and that re-running an agent does not duplicate its artefacts.

`tests/test_real_dataset.py` asserts the figures above against the real file and skips
when it is absent, so a green suite does not by itself prove they still hold — check it
did not skip.

## The interface

The app is organised around the pipeline: each agent's stage is a screen,
numbered in execution order, and the sidebar doubles as a map of how far the
run got. A few things worth calling out:

- **The homepage hero is the product.** The pipeline graph and the engine
  readout bind to the most recent real project; hovering a stage shows what that
  agent actually produced on the last run. With no project yet, they render an
  idle state rather than a staged demo.
- **Every number opens.** Click a KPI anywhere and the inspector shows its
  definition, formula, compiled SQL, source tables, historical series, the agent
  that produced it and the auditor's verdict.
- **The audit screen traces one number end to end** — run → raw → transform →
  clean → semantic model → KPI → SQL — from the lineage the backend records.
- **⌘K / Ctrl-K** opens a command palette built from real state: the projects
  that exist, the stages of this project, and the KPIs this run computed.
- **Dark mode is a selected theme**, not an inversion: chart colours are
  re-stepped for the dark surface and validated against it.
- **Nothing is mocked.** Where a capability is not implemented — live database
  connectors, for example — the UI says so plainly instead of faking a screen.


## Deliverables

The brief (§10) lists nine. Where each one lives:

| Deliverable | In the app | In the export |
| --- | --- | --- |
| Source code and architecture | — | [docs/architecture.md](docs/architecture.md) |
| Automated BI pipeline | **Pipeline runs** | `run` + `agent_versions` |
| Dataset and source documentation | **Datasets** | [data/documentation/](data/documentation/uci-online-retail.md) |
| Data Quality Report | **02 Clean** | `data_quality` · *Data quality* sheet |
| KPI catalogue and formulas | **04 Measure** | `kpis` · *KPI catalogue* sheet · CSV |
| Interactive BI dashboard | **06 Visualize** | — (interactive by nature) |
| Insights and recommendations | **05 Analyze** | `insights` · *Insights* sheet |
| Evaluation and XAI report | **07 Audit** | `evaluation`, `xai` · both sheets |
| Multi-agent demonstration | Agent activity drawer | [docs/demo.md](docs/demo.md) |

Every export format is built from one assembled report, so JSON, Excel and PDF
cannot disagree about a number. CSV is the exception — it is a flat table, so it
carries the KPI catalogue alone.

### Recommendations

Findings carry an action where one follows from what was measured. Each
recommendation is produced by a rule in `app/analytics/recommendations.py`,
quotes the numbers behind it, and records which rule fired — so the advice is
auditable the same way a KPI is:

> **United Kingdom accounts for 85.1% of Net Revenue**
> United Kingdom carries 85.1% of Net Revenue. A 10% fall there removes about
> 816,713 — size that against your plan before treating the total as stable. If
> this concentration is not deliberate, look at what limits the other segments:
> coverage, pricing, or supply.
> *Rule: concentration>=40% of an additive metric*

Not every finding gets one. A rule stays silent below its threshold, because a
recommendation on every row is indistinguishable from none.


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
- There is no authentication: the API is open on the local network
- Recommendations are rule-based, not generated. Each is a template attached to a
  measured condition, so they are auditable and never hallucinated — but they are
  general BI practice, not advice specific to your business context
- Only file upload is implemented; there are no live database or API connectors
- Join discovery is implemented and tested, but a single-table source leaves it
  largely unexercised in this project
- Role binding is heuristic; the Semantic Model screen shows every binding and its
  confidence so a wrong one can be spotted
- A date column whose ordering cannot be proven is parsed under a stated assumption and
  raised as a high-severity quality issue, not resolved automatically

## License

Application code is provided for this project. Third-party datasets remain under their
original licenses.

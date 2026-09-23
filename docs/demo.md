# BIFlow demo script

A 10-minute walkthrough that shows the multi-agent behaviour, not just the output.

## Setup

```bash
docker compose up --build          # or the SQLite path in the README
python scripts/download_demo_data.py
```

Open <http://localhost:3000>.

## 1. Start a run

1. Create project **E-Commerce BI Analysis**.
2. Objective: *Analyse e-commerce sales performance, customer behaviour, product mix and
   revenue evolution across countries.*
3. Upload the UCI Online Retail file (541,909 rows).
4. Click **Run pipeline** and stay on the Pipeline screen.

Each agent reports live over SSE. The run takes about 8 seconds. Point out that the
orchestrator inferred the `ecommerce` domain from the objective and the column names —
nothing was hard-coded for this dataset.

## 2. Show that the data was understood, not just read

**02 Clean** — nine issues on this file. The ones worth stopping on:

- `returns_present` on Quantity: 10,624 rows. The agent flagged returns as a business
  fact to report rather than an error to clean away.
- `ambiguous_type` on InvoiceNo and StockCode: the loader refused to cast them to numbers.
  Had it done so, every `C`-prefixed cancellation document would have become null.

**03 Model** — eight business roles bound to columns, each with a confidence score
and the reasoning behind it. `InvoiceNo → order_id` at 0.95, `Country → geo` at 0.90.
Note that `InvoiceNo` (25,900 distinct) is *not* offered as a chart dimension: it is a key.

## 3. The KPIs are real business metrics

**04 Measure** — 14 computed, each with its formula:

```
Net Revenue   SUM(online_retail.Quantity * online_retail.UnitPrice)          9,747,747.93
Gross Revenue SUM(... WHERE online_retail.InvoiceNo NOT LIKE 'C%')          10,644,560.42
Returned Val  SUM(... WHERE online_retail.Quantity < 0)                       -896,812.49
```

Gross + Returned = Net, exactly. Orders (22,064) + Cancelled Orders (3,836) = 25,900
documents. The reconciliation is the point: these are not independent guesses.

Worth saying out loud: revenue is `quantity × price` summed **per row**. A grammar that
can only aggregate a single column cannot express this, and would report the sum of the
price column — 2.5M instead of 9.7M.

Open any KPI to see its formula, compiled SQL, lineage and XAI explanation.

## 4. The dashboard is interactive

- Click **Last 3 months** — every tile re-queries the same slice. Net Revenue goes from
  £9.7M to £3.7M.
- Add **France** — £78.6K. The header states how many filters are scoping the page.
- Note the hollow marker at the end of the revenue line: the extract stops on 9 December,
  so that month is incomplete and is excluded from every comparison. Without this, all 14
  KPIs report a ~70% collapse that did not happen.
- Click **Explore** on Net Revenue, switch the breakdown dimension, and expand
  **SQL executed** — the exact query behind the chart.
- Toggle **Table** on any chart for the underlying numbers.

## 4b. Insights carry actions, not just facts

On **05 Analyze**, the header states how many findings are grounded and how many
carry a recommendation. Open a risk: the recommendation sits beside the evidence
and names the rule that produced it — for the UK concentration it quantifies the
exposure ("a 10% fall removes about 816,713") rather than asserting that
concentration is bad.

Point out that only some findings carry one. The rules have thresholds, so a 4%
move gets no advice; that is deliberate.

## 5. Show the agents disagreeing

This is the part that distinguishes a graph from a script.

In **07 Audit**, show the verdict and its reasoning, then the per-KPI explanations:
what happened, how it was calculated, which roles were bound, what filter was applied, and
what the quality caveats are.

To demonstrate the feedback edge live, run the orchestration test:

```bash
cd backend && pytest tests/test_orchestration.py -k feedback -v
```

It forces the auditor to reject the run and asserts that the graph routes back to the
semantic agent, retries within budget, then publishes with caveats instead of looping.
`agent_runs` records every attempt, so the Pipeline screen shows the repeated steps.

## 6. Dataset-agnosticism

Create a second project with an unrelated schema and run it. The same seven agents bind
different roles, instantiate a different subset of the catalog, and produce a different
dashboard — with no code change. Where no role matches, the catalog falls back to plainly
labelled sums and averages rather than dressing them up as revenue.

## 7. Evaluation

**Settings → Export** produces JSON, CSV, Excel or PDF, all built from one report so
they cannot disagree. The Excel workbook has a sheet per deliverable — KPI catalogue,
Data quality, Transformations, Insights (with recommendations), Evaluation, XAI and the
semantic model.

The evaluation sheet scores each agent, including `vs_naive_baseline`: what a
non-agentic script gets by summing every numeric column, which has no revenue, no
average order value and no return rate at any count.

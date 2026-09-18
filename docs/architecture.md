# BIFlow architecture

## System architecture

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

The frontend never computes KPIs. It renders artifacts persisted by a pipeline run.

## Agent architecture

LangGraph defines the control graph:

`START → orchestrator → profiler → quality ⇄ profiler (retry) → semantic ⇄ semantic (retry) → analyst → dashboard → auditor → publish → END`

Retry counts are bounded by `pipeline_max_retries`. The executor records each node as `pipeline_steps` + `agent_runs`.

| Agent | Deterministic engine | LLM role |
| --- | --- | --- |
| Orchestrator | Domain inference from objective + columns | Plan summary |
| Profiler | Polars statistics | Interpret warnings |
| Quality / ETL | Measurable scorecard + allowed transforms | Plan notes |
| Semantic / KPI | Role inference + formula compiler + DuckDB | Propose KPI formulas |
| Analyst | Trend, z-score, IQR, Pareto, correlation | Word insights from evidence |
| Dashboard | Trusted widget spec + computed series | Layout suggestions |
| Auditor | Formula/SQL/status checks | Validation narrative |

## Data architecture

Layers:

1. **RAW** — uploaded files, never mutated
2. **CLEANED** — parquet written after recorded transformations
3. **ANALYTICAL** — DuckDB views over parquet; KPI SQL executes here

Join candidates require value overlap, type compatibility and uniqueness — not name matching alone.

## Database

Relational tables cover projects, datasets, files, pipeline runs/steps, agent runs/messages, profiles, quality, transformations, semantic model, KPIs/results, analysis, insights, dashboards, audit events, XAI explanations and evaluation results. JSONB is used for flexible metadata (column stats, widget data, evidence).

## LLM interaction

- Provider selected by `LLM_PROVIDER`
- JSON object responses only
- Payload truncated; samples masked when PII is flagged
- If no API key is present, engines still run and the UI shows real computed artifacts

## Security model

- Read-only SQL validator (`sqlglot` + keyword denylist)
- Identifier allow-list for Postgres adapter
- Upload validation and rooted storage paths
- Rate limiting and CORS
- No secrets in the frontend bundle

## Lineage and audit

Each KPI stores formula, compiled SQL, source tables, run id and an `xai_explanations` row answering what happened, how it was calculated, which data was used, assumptions and quality limitations.

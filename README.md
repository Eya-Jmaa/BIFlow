# BIFlow

BIFlow is a production-oriented multi-agent Business Intelligence platform.

Give it a real dataset and a business objective. The system profiles the data, detects quality issues, applies a recorded transformation plan, infers a semantic model, proposes KPIs, **computes those KPIs deterministically**, analyzes trends and anomalies statistically, generates a dashboard specification, and audits every result with lineage and XAI explanations.

Analytical numbers are never invented by an LLM. Python, Polars, DuckDB and validated SQL produce the numbers. The LLM, when configured, interprets evidence and proposes structure.

## Architecture

```
RAW DATA → PROFILER → QUALITY / ETL → SEMANTIC → KPI ENGINE → ANALYST → DASHBOARD → AUDIT / XAI
```

- **Frontend:** Next.js, TypeScript, Tailwind CSS, TanStack Query, Recharts
- **Backend:** FastAPI, SQLAlchemy 2, Alembic, Polars, DuckDB, scikit-learn, LangGraph
- **Datastore:** PostgreSQL
- **Jobs / events:** Redis + RQ, Server-Sent Events
- **LLM:** OpenAI-compatible provider abstraction (OpenAI, Groq, local). Optional.

See [docs/architecture.md](docs/architecture.md) for the system design.

## Features

- Dataset-agnostic ingestion (CSV, Parquet, Excel; Postgres/API adapters included)
- Deterministic profiling, PII flags, join discovery with statistical validation
- Conservative ETL with full transformation lineage
- Safe KPI formula grammar compiled to read-only SQL
- Evidence-grounded insights (unsupported LLM claims are rejected)
- Structured dashboard specs rendered by trusted widgets
- Audit events, XAI explanations, evaluation metrics, exports (CSV / Excel / JSON / PDF)
- Real-time pipeline status from actual agent execution

## Quick start (Docker)

1. Copy environment defaults:

```bash
cp .env.example .env
```

2. Set `OPENAI_API_KEY` or `GROQ_API_KEY` if you want LLM interpretation. The pipeline still computes real analytics without a key.

3. Start the stack:

```bash
docker compose up --build
```

4. Open [http://localhost:3000](http://localhost:3000)

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Demo workflow

1. Create a project named **E-Commerce BI Analysis**.
2. Enter a business objective, for example: *Analyze e-commerce sales performance, customer behavior, delivery performance and revenue evolution.*
3. Upload real Olist CSVs (see [data/documentation/olist.md](data/documentation/olist.md)) or the UCI Online Retail file.
4. Click **Run pipeline**.
5. Watch agent steps complete on the Pipeline screen.
6. Inspect Data Quality, Semantic Model, KPI catalog, Insights, Dashboard, Audit/XAI, and Lineage.
7. Open a KPI to view formula, SQL, lineage and explanation.
8. Export the report from Settings.

A second, unrelated schema (for example UCI Online Retail) should run through the same agents without code changes.

```bash
python scripts/download_demo_data.py
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# PostgreSQL + Redis must be reachable; docker compose up postgres redis
alembic upgrade head
uvicorn app.main:app --reload --port 8000
python -m app.worker
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment variables

See `.env.example`. Important keys:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL |
| `REDIS_URL` | RQ / pub-sub |
| `LLM_PROVIDER` | `openai`, `groq`, or `local` |
| `LLM_MODEL` | Model name |
| `OPENAI_API_KEY` / `GROQ_API_KEY` | Never sent to the frontend |
| `DATA_DIR` | RAW / processed storage |
| `MAX_UPLOAD_MB` | Upload limit |

## Testing

```bash
cd backend
pytest -q
```

Tests cover profiling, quality detection, ETL, join discovery, KPI SQL execution on real in-memory tables, SQL safety, evaluation metrics, and API health/OpenAPI. Fixture tables are infrastructure-only and are not seeded as production business data.

## Security

- Secrets stay in environment variables
- Generated SQL is parsed and restricted to a single SELECT
- Uploads are type/size validated with path-traversal protection
- Datasets are not sent in full to the LLM; schema, statistics and compact evidence only
- CORS and rate limiting are enabled

## Limitations

- Very large files are profiled with Polars/DuckDB but still require adequate worker memory
- Geospatial map widgets render only when a geo dimension and widget data exist
- Authentication is modeled (`users` table) but the demo API is open on the local network
- LLM insight wording is used only when values match computed evidence

## License

Application code is provided for this project. Third-party datasets remain under their original licenses.

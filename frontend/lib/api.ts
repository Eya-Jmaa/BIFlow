export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type Project = {
  id: string;
  name: string;
  description: string | null;
  business_objective: string;
  domain: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type Dataset = {
  id: string;
  name: string;
  table_name: string;
  layer: string;
  source_type: string;
  row_count: number | null;
  column_count: number | null;
  status: string;
  created_at: string;
};

export type PipelineRun = {
  id: string;
  project_id: string;
  status: string;
  business_objective: string;
  current_step: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  created_at: string;
};

export type PipelineStep = {
  id: string;
  name: string;
  display_name: string;
  status: string;
  sequence: number;
  duration_ms: number | null;
  output_summary: Record<string, unknown>;
  error: string | null;
};

export type KPI = {
  id: string;
  name: string;
  slug: string;
  description: string;
  business_meaning: string;
  formula: string;
  unit: string | null;
  confidence: number;
  validation_status: string;
  query_sql: string | null;
  value: number | null;
  previous_value: number | null;
  change_pct: number | null;
};

export type Insight = {
  id: string;
  title: string;
  description: string;
  category: string;
  evidence: Record<string, unknown>;
  metric: string | null;
  value: number | null;
  comparison: string | null;
  period: string | null;
  severity: string;
  confidence: number;
  query_sql: string | null;
  grounded: boolean;
};

export type Widget = {
  id: string;
  widget_type: string;
  title: string;
  query_sql: string | null;
  kpi_id: string | null;
  dimensions: unknown[];
  measures: unknown[];
  format: Record<string, unknown>;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
  data: {
    value?: number | null;
    previous_value?: number | null;
    change_pct?: number | null;
    series?: { period: string; value: number | null; partial?: boolean }[];
    breakdown?: { dimension: string; value: number | null }[];
    unit?: string | null;
    format?: { style?: "currency" | "percent" | "integer" | "decimal"; decimals?: number };
    rows?: { name: string; value: number | null; unit: string | null; formula: string }[];
    anomalies?: {
      metric: string;
      anomalies?: {
        value: number;
        method: string;
        zscore?: number;
        period?: string | null;
        unit?: string | null;
      }[];
    }[];
  };
  explanation: string | null;
};

export type Dashboard = {
  id: string;
  title: string;
  layout: Record<string, unknown>;
  published: boolean;
  audit_status: string;
  widgets: Widget[];
};


export type DashboardFilter = {
  column: string;
  op: "eq" | "ne" | "in" | "not_in" | "gt" | "gte" | "lt" | "lte" | "between" | "contains" | "is_null" | "not_null";
  values: (string | number)[];
};

export type FilterDimension = {
  name: string;
  label: string;
  table: string;
  column: string;
  type: string;
  logical_type: string | null;
  values?: string[];
  min?: string | null;
  max?: string | null;
  grains?: string[];
};

export type FilterOptions = {
  run_id: string;
  dimensions: FilterDimension[];
  kpis: {
    slug: string;
    name: string;
    unit: string | null;
    additivity: "additive" | "semi_additive" | "non_additive";
    tables: string[];
    format: { style?: string; decimals?: number };
  }[];
};

export type QueryResult = {
  kpi: string;
  unit: string | null;
  rows: { dimension?: string; value: number | null }[];
  sql: string;
  filters_applied: string[];
  additivity: string;
  truncated: boolean;
};

export type QueryRequest = {
  kpi_slug: string;
  dimension?: string | null;
  grain?: string | null;
  filters?: DashboardFilter[];
  limit?: number;
};

export const api = {
  health: () => request<{ status: string }>("/health"),
  projects: () => request<Project[]>("/api/projects"),
  project: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (body: { name: string; business_objective: string; description?: string; domain?: string }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  deleteProject: (id: string) => request(`/api/projects/${id}`, { method: "DELETE" }),
  datasets: (id: string) => request<Dataset[]>(`/api/projects/${id}/datasets`),
  uploadDataset: async (id: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    let response: Response;
    try {
      response = await fetch(`${API_URL}/api/projects/${id}/datasets`, { method: "POST", body: data });
    } catch {
      throw new Error("Cannot reach the API. Confirm the backend is running at http://localhost:8000.");
    }
    if (!response.ok) {
      let detail = `Upload failed (${response.status})`;
      try {
        const payload = await response.json();
        detail = payload.detail || JSON.stringify(payload);
      } catch {
        detail = await response.text();
      }
      throw new Error(detail);
    }
    return response.json() as Promise<Dataset>;
  },
  runPipeline: (id: string) => request<PipelineRun>(`/api/projects/${id}/pipeline/run`, { method: "POST" }),
  runs: (id: string) => request<PipelineRun[]>(`/api/projects/${id}/pipeline-runs`),
  run: (runId: string) => request<PipelineRun>(`/api/pipeline-runs/${runId}`),
  steps: (runId: string) => request<PipelineStep[]>(`/api/pipeline-runs/${runId}/steps`),
  events: (runId: string) => request<unknown[]>(`/api/pipeline-runs/${runId}/events`),
  quality: (id: string) => request<unknown[]>(`/api/projects/${id}/quality`),
  transformations: (id: string) => request<unknown[]>(`/api/projects/${id}/transformations`),
  profile: (id: string) => request<unknown[]>(`/api/projects/${id}/profile`),
  semantic: (id: string) => request<unknown>(`/api/projects/${id}/semantic-model`),
  kpis: (id: string) => request<KPI[]>(`/api/projects/${id}/kpis`),
  kpi: (id: string, kpiId: string) => request<unknown>(`/api/projects/${id}/kpis/${kpiId}`),
  insights: (id: string) => request<Insight[]>(`/api/projects/${id}/insights`),
  analysis: (id: string) => request<unknown[]>(`/api/projects/${id}/analysis`),
  dashboard: (id: string) => request<Dashboard>(`/api/projects/${id}/dashboard`),
  audit: (id: string) => request<unknown>(`/api/projects/${id}/audit`),
  lineage: (id: string) => request<unknown>(`/api/projects/${id}/lineage`),
  agentRuns: (id: string) => request<unknown[]>(`/api/projects/${id}/agent-runs`),
  evaluation: (id: string) => request<unknown[]>(`/api/projects/${id}/evaluation`),
  filterOptions: (id: string) => request<FilterOptions>(`/api/projects/${id}/filter-options`),
  queryKpi: (id: string, body: QueryRequest) =>
    request<QueryResult>(`/api/projects/${id}/query`, { method: "POST", body: JSON.stringify(body) }),
  exportUrl: (id: string, format: "json" | "csv" | "xlsx" | "pdf") => `${API_URL}/api/projects/${id}/export/${format}`,
  streamUrl: (runId: string) => `${API_URL}/api/pipeline-runs/${runId}/stream`,
};

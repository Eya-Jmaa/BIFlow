/**
 * Turn backend run records into the shape the pipeline UI renders.
 *
 * Every figure here comes from an agent's own `output_summary`, which the
 * executor writes when the agent completes. Nothing is derived optimistically:
 * a stage with no agent run reports no metrics rather than zeros, because "0
 * issues" and "never checked" are very different claims in an audit tool.
 */

import type { StageId, StageStatus } from "@/lib/pipeline";
import type { StageMetric, StageState } from "@/components/pipeline-graph";

export type AgentRun = {
  id: string;
  agent_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  llm_model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  retry_count: number;
  output_summary: Record<string, unknown> | null;
  error: string | null;
};

const integer = new Intl.NumberFormat("en-GB");

function num(source: Record<string, unknown> | null, key: string): number | null {
  const value = source?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function metric(label: string, value: number | null, suffix = ""): StageMetric | null {
  if (value === null) return null;
  return { label, value: `${integer.format(value)}${suffix}` };
}

function toStatus(status: string | undefined): StageStatus {
  if (status === "completed") return "completed";
  if (status === "running") return "running";
  if (status === "failed") return "failed";
  return "pending";
}

/**
 * Map agent runs onto the seven pipeline stages.
 *
 * `semantic` backs both Model and Measure, so its one run drives two stages
 * with different slices of its summary.
 */
export function stageStatesFromRuns(
  runs: AgentRun[] | undefined,
): Partial<Record<StageId, StageState>> {
  if (!runs?.length) return {};

  // Latest attempt wins: a retried agent should report its final state.
  const latest = new Map<string, AgentRun>();
  for (const run of runs) latest.set(run.agent_name, run);

  const build = (
    agent: string,
    metrics: (summary: Record<string, unknown> | null) => (StageMetric | null)[],
  ): StageState | undefined => {
    const run = latest.get(agent);
    if (!run) return undefined;
    return {
      status: toStatus(run.status),
      latencyMs: run.latency_ms,
      metrics: metrics(run.output_summary).filter((item): item is StageMetric => item !== null),
    };
  };

  const states: Partial<Record<StageId, StageState>> = {};

  const profiler = build("profiler", (summary) => [
    metric("Rows", num(summary, "rows")),
    metric("Tables", num(summary, "tables")),
    metric("Roles bound", num(summary, "roles_bound")),
    metric("Joins found", num(summary, "joins")),
    metric("PII flags", num(summary, "pii_flags")),
  ]);
  if (profiler) states.profile = profiler;

  const quality = build("quality", (summary) => [
    metric("Issues", num(summary, "issues")),
    metric("Transformations", num(summary, "transformations")),
    (() => {
      const score = num(summary, "overall_score");
      return score === null ? null : { label: "Quality score", value: score.toFixed(2) };
    })(),
  ]);
  if (quality) states.clean = quality;

  const model = build("semantic", (summary) => [
    metric("Dimensions", num(summary, "dimensions")),
    metric("Measures", num(summary, "measures")),
  ]);
  if (model) states.model = model;

  const measure = build("semantic", (summary) => [
    metric("KPIs computed", num(summary, "kpis_computed")),
    metric("Failed", num(summary, "kpis_failed")),
  ]);
  if (measure) states.measure = measure;

  const analyst = build("analyst", (summary) => [
    metric("Insights kept", num(summary, "insights")),
    metric("Generated", num(summary, "insights_generated")),
    metric("Metrics analysed", num(summary, "metrics_analysed")),
  ]);
  if (analyst) states.analyze = analyst;

  const dashboard = build("dashboard", (summary) => [
    metric("Widgets", num(summary, "widgets")),
    metric("Bound KPIs", num(summary, "kpis")),
  ]);
  if (dashboard) states.visualize = dashboard;

  const auditor = build("auditor", (summary) => {
    const ratio = num(summary, "kpi_success_ratio");
    const verdict = summary?.["status"];
    return [
      metric("Checks", num(summary, "findings")),
      ratio === null ? null : { label: "KPIs valid", value: `${(ratio * 100).toFixed(0)}%` },
      typeof verdict === "string" ? { label: "Verdict", value: verdict } : null,
    ];
  });
  if (auditor) states.audit = auditor;

  return states;
}

/** Total wall-clock time across the agents of one run. */
export function runtimeMs(runs: AgentRun[] | undefined): number | null {
  if (!runs?.length) return null;
  const total = runs.reduce((sum, run) => sum + (run.latency_ms ?? 0), 0);
  return total > 0 ? total : null;
}

/** LLM token usage, when a model was configured. Null means fully deterministic. */
export function tokenUsage(runs: AgentRun[] | undefined): number | null {
  if (!runs?.length) return null;
  const total = runs.reduce(
    (sum, run) => sum + (run.prompt_tokens ?? 0) + (run.completion_tokens ?? 0),
    0,
  );
  return total > 0 ? total : null;
}

/** "42 sec ago" / "4 min ago". Returns null for an absent timestamp. */
export function relativeTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).getTime();
  if (Number.isNaN(then)) return null;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return `${seconds} sec ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

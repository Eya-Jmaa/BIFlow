"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Loader2, Minus, X } from "lucide-react";

import { Badge, Code, Eyebrow, StatusDot } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { STAGES, type StageStatus } from "@/lib/pipeline";
import { formatDuration, relativeTime, tokenUsage, type AgentRun } from "@/lib/run-state";
import { cn } from "@/lib/utils";

/**
 * Agent activity.
 *
 * Shows what each agent did on the latest run, including retries — the
 * auditor can send work back to an earlier agent, so the same agent may appear
 * more than once, and hiding that would misrepresent how the system works.
 */

const ICON = { completed: Check, running: Loader2, failed: X, pending: Minus } as const;
const TONE = { completed: "good", running: "brand", failed: "bad", pending: "neutral" } as const;

function toStatus(status: string): StageStatus {
  if (status === "completed") return "completed";
  if (status === "running") return "running";
  if (status === "failed") return "failed";
  return "pending";
}

export function ActivityDrawer({
  projectId,
  open,
  onClose,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
}) {
  const agents = useQuery({
    queryKey: ["agents", projectId],
    queryFn: () => api.agentRuns(projectId) as Promise<AgentRun[]>,
    enabled: open,
    retry: false,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((run) => run.status === "running") ? 2000 : false,
  });

  if (!open) return null;

  const runs = agents.data ?? [];
  const byAgent = new Map<string, AgentRun[]>();
  for (const run of runs) {
    byAgent.set(run.agent_name, [...(byAgent.get(run.agent_name) ?? []), run]);
  }
  const tokens = tokenUsage(runs);
  const retries = runs.filter((run) => run.retry_count > 0).length;

  return (
    <div className="fixed inset-0 z-50">
      <button
        className="bf-fade absolute inset-0 bg-shell/40 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Close agent activity"
      />
      <aside
        className="bf-slide-left absolute inset-y-0 right-0 flex w-full max-w-[24rem] flex-col border-l border-line bg-surface shadow-float"
        role="dialog"
        aria-label="Agent activity"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-ink">BIFlow agents</h2>
            <p className="mt-0.5 text-[0.6875rem] text-ink-muted">
              {runs.length
                ? `${runs.length} agent run${runs.length === 1 ? "" : "s"} in the latest execution`
                : "No run recorded yet"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="grid size-8 place-items-center rounded-lg text-ink-faint transition-colors hover:bg-sunken hover:text-ink"
            aria-label="Close"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {runs.length === 0 ? (
            <p className="rounded-card border border-dashed border-line-strong bg-sunken/50 px-4 py-8 text-center text-[0.8125rem] text-ink-muted">
              Run the pipeline to see each agent report here.
            </p>
          ) : (
            <ol className="space-y-2">
              {STAGES.filter(
                (stage, index, all) => all.findIndex((s) => s.agent === stage.agent) === index,
              ).map((stage) => {
                const attempts = byAgent.get(stage.agent) ?? [];
                const last = attempts[attempts.length - 1];
                const status = last ? toStatus(last.status) : "pending";
                const Icon = ICON[status];

                return (
                  <li
                    key={stage.agent}
                    className="rounded-card border border-line bg-raised p-3 transition-shadow duration-[--duration-fast] hover:shadow-card"
                  >
                    <div className="flex items-start gap-2.5">
                      <span
                        className={cn(
                          "mt-0.5 grid size-6 shrink-0 place-items-center rounded-lg",
                          status === "completed" && "bg-good-soft text-good",
                          status === "running" && "bg-brand-soft text-brand",
                          status === "failed" && "bg-bad-soft text-bad",
                          status === "pending" && "bg-inset text-ink-faint",
                        )}
                      >
                        <Icon
                          className={cn("size-3.5", status === "running" && "animate-spin")}
                          aria-hidden
                        />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-[0.8125rem] font-medium text-ink">
                            {stage.role}
                          </p>
                          {last?.latency_ms != null && (
                            <span className="tnum shrink-0 text-[0.625rem] text-ink-faint">
                              {formatDuration(last.latency_ms)}
                            </span>
                          )}
                        </div>

                        {last?.error ? (
                          <p className="mt-1 text-[0.75rem] leading-snug text-bad">{last.error}</p>
                        ) : (
                          <p className="mt-0.5 text-[0.6875rem] text-ink-muted">
                            {summarise(last?.output_summary) ?? "Waiting"}
                          </p>
                        )}

                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          {attempts.length > 1 && (
                            <Badge tone="warn">{attempts.length} attempts</Badge>
                          )}
                          {last?.llm_model && <Badge tone="brand">{last.llm_model}</Badge>}
                          {last?.completed_at && (
                            <span className="text-[0.625rem] text-ink-faint">
                              {relativeTime(last.completed_at)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}

          {runs.length > 0 && (
            <div className="mt-5 space-y-3">
              <Eyebrow>Run facts</Eyebrow>
              <dl className="grid grid-cols-2 gap-3 text-[0.75rem]">
                <Fact label="Agent runs" value={String(runs.length)} />
                <Fact label="Retries" value={String(retries)} />
                <Fact
                  label="LLM tokens"
                  value={tokens != null ? tokens.toLocaleString("en-GB") : "none — deterministic"}
                />
                <Fact
                  label="Total agent time"
                  value={formatDuration(
                    runs.reduce((sum, run) => sum + (run.latency_ms ?? 0), 0),
                  )}
                />
              </dl>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-sunken px-3 py-2">
      <dt className="text-[0.5625rem] tracking-[0.1em] text-ink-faint uppercase">{label}</dt>
      <dd className="mt-0.5 truncate text-[0.75rem] font-medium text-ink">{value}</dd>
    </div>
  );
}

/** Turn an agent's own output summary into one readable line. */
function summarise(summary: Record<string, unknown> | null | undefined): string | null {
  if (!summary) return null;
  const parts: string[] = [];
  const add = (key: string, label: string) => {
    const value = summary[key];
    if (typeof value === "number") parts.push(`${value.toLocaleString("en-GB")} ${label}`);
  };
  add("rows", "rows");
  add("issues", "issues");
  add("transformations", "transformations");
  add("dimensions", "dimensions");
  add("kpis_computed", "KPIs");
  add("insights", "insights");
  add("widgets", "widgets");
  add("findings", "checks");
  if (typeof summary.status === "string") parts.push(`verdict ${summary.status}`);
  return parts.length ? parts.slice(0, 3).join(" · ") : null;
}

export { Code };

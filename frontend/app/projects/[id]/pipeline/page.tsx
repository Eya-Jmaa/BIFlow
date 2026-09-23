"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { AlertCircle, Check, Loader2, Minus, Workflow } from "lucide-react";

import {
  Badge,
  Code,
  EmptyState,
  Eyebrow,
  Field,
  Panel,
  PanelHeader,
  statusTone,
} from "@/components/ui/primitives";
import { api, type PipelineStep } from "@/lib/api";
import { formatDuration, relativeTime, type AgentRun } from "@/lib/run-state";
import { cn } from "@/lib/utils";

/**
 * Pipeline run monitor.
 *
 * Shows the run as it executed, including repeats: the auditor can route work
 * back to an earlier agent, so the same agent may appear several times. That
 * is the system working as designed, and the trace makes it visible.
 */

const STATUS_ICON = {
  completed: Check,
  running: Loader2,
  failed: AlertCircle,
  pending: Minus,
} as const;

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id), retry: false });
  const latest = runs.data?.[0];
  const live = latest?.status === "running" || latest?.status === "queued";

  const steps = useQuery({
    queryKey: ["steps", latest?.id],
    queryFn: () => api.steps(latest!.id),
    enabled: Boolean(latest),
    refetchInterval: live ? 1500 : false,
    retry: false,
  });
  const agents = useQuery({
    queryKey: ["agents", id],
    queryFn: () => api.agentRuns(id) as Promise<AgentRun[]>,
    enabled: Boolean(latest),
    refetchInterval: live ? 2000 : false,
    retry: false,
  });

  const [selected, setSelected] = useState<string | null>(null);
  const ordered = [...(steps.data ?? [])].sort((a, b) => a.sequence - b.sequence);
  const step = ordered.find((item) => item.name === selected) ?? ordered[0];
  const trace = agents.data ?? [];
  const retried = trace.filter((agent) => agent.retry_count > 0);

  if (!latest) {
    return (
      <EmptyState
        title="No run yet"
        message="Run the pipeline and each agent reports here live as it completes."
        icon={<Workflow className="size-5" />}
      />
    );
  }

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1.2fr_0.8fr]">
      <Panel>
        <PanelHeader
          title="Execution"
          subtitle={
            retried.length
              ? `${trace.length} agent runs — the auditor sent work back ${retried.length} time${retried.length > 1 ? "s" : ""}`
              : `${ordered.length} agents, executed in order`
          }
          icon={<Workflow className="size-4" />}
          action={
            <Badge tone={statusTone(latest.status)} dot pulse={live}>
              {latest.status}
            </Badge>
          }
        />
        <ol className="relative space-y-1">
          {ordered.map((item: PipelineStep, index) => {
            const Icon = STATUS_ICON[item.status as keyof typeof STATUS_ICON] ?? Minus;
            const attempts = trace.filter((agent) => agent.agent_name === item.name).length;
            const isActive = step?.name === item.name;
            return (
              <li key={item.id} className="relative">
                {index < ordered.length - 1 && (
                  <span
                    className="absolute top-10 left-[1.1875rem] h-[calc(100%-1.25rem)] w-px bg-line"
                    aria-hidden
                  />
                )}
                <button
                  onClick={() => setSelected(item.name)}
                  className={cn(
                    "relative flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left",
                    "transition-[background-color,border-color] duration-[--duration-fast]",
                    isActive
                      ? "border-brand/30 bg-brand-soft/60"
                      : "border-transparent hover:bg-sunken",
                  )}
                >
                  <span
                    className={cn(
                      "z-10 grid size-7 shrink-0 place-items-center rounded-full ring-4 ring-surface",
                      item.status === "completed" && "bg-good-soft text-good",
                      item.status === "running" && "bg-brand-soft text-brand",
                      item.status === "failed" && "bg-bad-soft text-bad",
                      item.status === "pending" && "bg-inset text-ink-faint",
                    )}
                  >
                    <Icon
                      className={cn("size-3.5", item.status === "running" && "animate-spin")}
                      aria-hidden
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.8125rem] font-medium text-ink">
                      {item.display_name}
                    </span>
                    <span className="block text-[0.6875rem] text-ink-faint">
                      {formatDuration(item.duration_ms)}
                      {attempts > 1 && ` · ${attempts} attempts`}
                    </span>
                  </span>
                  <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                </button>
              </li>
            );
          })}
        </ol>
      </Panel>

      <div className="space-y-4">
        <Panel>
          <PanelHeader title={step ? step.display_name : "Step detail"} />
          {!step ? (
            <p className="text-[0.8125rem] text-ink-muted">Select an agent.</p>
          ) : (
            <>
              <dl className="mb-3 grid grid-cols-2 gap-3">
                <Field label="Status">{step.status}</Field>
                <Field label="Duration">{formatDuration(step.duration_ms)}</Field>
              </dl>
              {step.error && (
                <p className="mb-3 rounded-lg bg-bad-soft px-3 py-2 text-[0.8125rem] text-bad">
                  {step.error}
                </p>
              )}
              <Eyebrow>Output summary</Eyebrow>
              <Code className="mt-1.5 max-h-72">
                {JSON.stringify(step.output_summary, null, 2)}
              </Code>
            </>
          )}
        </Panel>

        {trace.length > 0 && (
          <Panel>
            <PanelHeader title="Agent trace" subtitle="Every attempt, in order" />
            <ul className="space-y-1.5">
              {trace.map((agent, index) => (
                <li key={agent.id} className="flex items-center gap-2.5 text-[0.8125rem]">
                  <span className="tnum w-5 shrink-0 text-right text-[0.625rem] text-ink-faint">
                    {index + 1}
                  </span>
                  <span className="flex-1 truncate font-medium text-ink">{agent.agent_name}</span>
                  {agent.retry_count > 0 && <Badge tone="warn">retry {agent.retry_count}</Badge>}
                  <span className="tnum shrink-0 text-ink-faint">
                    {formatDuration(agent.latency_ms)}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {runs.data && runs.data.length > 1 && (
          <Panel>
            <PanelHeader title="Run history" subtitle={`${runs.data.length} runs`} />
            <ul className="space-y-1.5">
              {runs.data.slice(0, 8).map((run) => (
                <li key={run.id} className="flex items-center gap-2 text-[0.75rem]">
                  <Badge tone={statusTone(run.status)}>{run.status}</Badge>
                  <span className="font-mono text-[0.625rem] text-ink-faint">
                    {run.id.slice(0, 8)}
                  </span>
                  <span className="ml-auto text-ink-faint">
                    {relativeTime(run.completed_at ?? run.started_at) ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { AlertCircle, Check, Loader2, Minus, Workflow } from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Code, EmptyState, Field } from "@/components/ui/data";
import { api, type PipelineStep } from "@/lib/api";
import { formatDuration } from "@/lib/viz";
import { cn } from "@/lib/utils";

type AgentRun = {
  id: string;
  agent_name: string;
  status: string;
  latency_ms: number | null;
  retry_count: number;
  llm_model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  error: string | null;
};

const STATUS_ICON = {
  completed: Check,
  running: Loader2,
  failed: AlertCircle,
  pending: Minus,
} as const;

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id) });
  const latest = runs.data?.[0];
  const live = latest?.status === "running" || latest?.status === "queued";

  const steps = useQuery({
    queryKey: ["steps", latest?.id],
    queryFn: () => api.steps(latest!.id),
    enabled: Boolean(latest),
    refetchInterval: live ? 1500 : false,
  });
  const agents = useQuery({
    queryKey: ["agents", id],
    queryFn: () => api.agentRuns(id) as Promise<AgentRun[]>,
    enabled: Boolean(latest),
    refetchInterval: live ? 2000 : false,
  });

  const [selected, setSelected] = useState<string | null>(null);
  const ordered = [...(steps.data ?? [])].sort((a, b) => a.sequence - b.sequence);
  const step = ordered.find((item) => item.name === selected) ?? ordered[0];
  const trace = agents.data ?? [];
  // More agent runs than steps means the auditor sent the run back.
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
    <div className="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
      <Card>
        <CardHeader
          title="Agent graph"
          subtitle={
            retried.length
              ? `${trace.length} agent runs — the auditor sent work back ${retried.length} time${retried.length > 1 ? "s" : ""}`
              : `${ordered.length} agents, executed in order`
          }
        />
        <ol className="relative space-y-1.5">
          {ordered.map((item: PipelineStep, index) => {
            const Icon =
              STATUS_ICON[item.status as keyof typeof STATUS_ICON] ?? Minus;
            const attempts = trace.filter((agent) => agent.agent_name === item.name).length;
            const isActive = step?.name === item.name;
            return (
              <li key={item.id} className="relative">
                {index < ordered.length - 1 && (
                  <span
                    className="absolute top-9 left-[1.0625rem] h-[calc(100%-1rem)] w-px bg-line"
                    aria-hidden
                  />
                )}
                <button
                  onClick={() => setSelected(item.name)}
                  className={cn(
                    "relative flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors",
                    isActive
                      ? "border-brand/30 bg-brand-soft/60"
                      : "border-transparent hover:bg-surface-muted",
                  )}
                >
                  <span
                    className={cn(
                      "z-10 grid size-[1.625rem] shrink-0 place-items-center rounded-full ring-4 ring-surface",
                      item.status === "completed" && "bg-good-soft text-good",
                      item.status === "running" && "bg-brand-soft text-brand",
                      item.status === "failed" && "bg-bad-soft text-bad",
                      item.status === "pending" && "bg-surface-sunken text-ink-faint",
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
                    <span className="block text-xs text-ink-faint">
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
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader title={step ? step.display_name : "Step detail"} />
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
              <p className="mb-1.5 text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase">
                Output summary
              </p>
              <Code className="max-h-72">{JSON.stringify(step.output_summary, null, 2)}</Code>
            </>
          )}
        </Card>

        {trace.length > 0 && (
          <Card>
            <CardHeader title="Execution trace" subtitle="Every attempt, in order" />
            <ul className="space-y-1.5">
              {trace.map((agent, index) => (
                <li
                  key={agent.id}
                  className="flex items-center gap-2.5 text-[0.8125rem] text-ink-soft"
                >
                  <span className="w-5 shrink-0 text-right font-mono text-[0.6875rem] text-ink-faint">
                    {index + 1}
                  </span>
                  <span className="flex-1 truncate font-medium text-ink">{agent.agent_name}</span>
                  {agent.retry_count > 0 && (
                    <Badge tone="warning">retry {agent.retry_count}</Badge>
                  )}
                  <span className="shrink-0 tabular-nums text-ink-faint">
                    {formatDuration(agent.latency_ms)}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

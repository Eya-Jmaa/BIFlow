"use client";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { api, type PipelineStep } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id), refetchInterval: 3000 });
  const latest = runs.data?.[0];
  const steps = useQuery({
    queryKey: ["steps", latest?.id],
    queryFn: () => api.steps(latest!.id),
    enabled: Boolean(latest),
    refetchInterval: latest?.status === "running" ? 1500 : false,
  });
  const agents = useQuery({
    queryKey: ["agents", id],
    queryFn: () => api.agentRuns(id),
    enabled: Boolean(latest),
    refetchInterval: latest?.status === "running" ? 2000 : false,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const step = steps.data?.find((s) => s.name === selected) || steps.data?.[0];

  return (
    <div className="grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
      <Card>
        <h2 className="mb-4 text-sm font-semibold">Agent pipeline</h2>
        {!latest && <p className="text-sm text-slate-500">Run the pipeline to see live agent execution.</p>}
        <ol className="space-y-2">
          {steps.data?.map((item: PipelineStep) => (
            <li key={item.id}>
              <button
                className="flex w-full items-center justify-between rounded-md border border-slate-800 px-3 py-2 text-left hover:border-slate-600"
                onClick={() => setSelected(item.name)}
              >
                <div>
                  <p className="text-sm font-medium">{item.display_name}</p>
                  <p className="text-xs text-slate-500">{formatDuration(item.duration_ms)}</p>
                </div>
                <Badge tone={statusTone(item.status)}>{item.status}</Badge>
              </button>
            </li>
          ))}
        </ol>
      </Card>
      <Card>
        <h2 className="text-sm font-semibold">Step detail</h2>
        {!step && <p className="mt-2 text-sm text-slate-500">Select a node.</p>}
        {step && (
          <div className="mt-3 space-y-2 text-sm">
            <p>Status: {step.status}</p>
            <p>Duration: {formatDuration(step.duration_ms)}</p>
            {step.error && <p className="text-red-400">{step.error}</p>}
            <pre className="overflow-auto rounded bg-slate-950 p-3 text-[11px] text-slate-300">
              {JSON.stringify(step.output_summary, null, 2)}
            </pre>
          </div>
        )}
        {Array.isArray(agents.data) && agents.data.length > 0 && (
          <div className="mt-4">
            <h3 className="text-xs uppercase text-slate-500">Agent trace</h3>
            <ul className="mt-2 space-y-1 text-xs text-slate-400">
              {(agents.data as Array<Record<string, unknown>>).map((agent) => (
                <li key={String(agent.id)}>
                  {String(agent.agent_name)} · {String(agent.status)} · {String(agent.latency_ms ?? "—")} ms
                  {agent.llm_model ? ` · ${String(agent.llm_model)}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}

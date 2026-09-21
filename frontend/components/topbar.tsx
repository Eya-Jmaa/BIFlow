"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, RotateCw } from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type PipelineRun, type Project } from "@/lib/api";

const STEP_LABELS: Record<string, string> = {
  orchestrator: "Orchestrator",
  profiler: "Profiler",
  quality: "Quality / ETL",
  semantic: "Semantic / KPI",
  analyst: "Analyst",
  dashboard: "Dashboard",
  auditor: "Auditor / XAI",
  completed: "Completed",
};

export function Topbar({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const runs = useQuery({
    queryKey: ["runs", project.id],
    queryFn: () => api.runs(project.id),
    // Poll while a run is in flight so the header tracks it without a refresh.
    refetchInterval: (query) => {
      const latest = query.state.data?.[0];
      return latest?.status === "running" || latest?.status === "queued" ? 2000 : false;
    },
  });
  const latest: PipelineRun | undefined = runs.data?.[0];
  const busy = latest?.status === "running" || latest?.status === "queued";

  const run = useMutation({
    mutationFn: () => api.runPipeline(project.id),
    onSuccess: () => {
      // A new run invalidates every artefact on every screen.
      queryClient.invalidateQueries();
    },
  });

  const status = latest?.status || project.status;

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 pb-1">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <h1 className="truncate text-lg font-semibold tracking-tight text-ink">{project.name}</h1>
          <Badge tone={statusTone(status)} dot>
            {busy ? "running" : status.replace(/_/g, " ")}
          </Badge>
        </div>
        <p className="mt-0.5 max-w-2xl truncate text-[0.8125rem] text-ink-muted">
          {project.business_objective}
        </p>
      </div>

      <div className="flex items-center gap-3">
        {busy && latest?.current_step && (
          <span className="flex items-center gap-1.5 text-xs text-ink-muted">
            <Loader2 className="size-3.5 animate-spin text-brand" aria-hidden />
            {STEP_LABELS[latest.current_step] ?? latest.current_step}
          </span>
        )}
        <Button onClick={() => run.mutate()} disabled={run.isPending || busy}>
          {run.isPending || busy ? (
            <RotateCw className="animate-spin" aria-hidden />
          ) : (
            <Play aria-hidden />
          )}
          {busy ? "Running…" : latest ? "Re-run pipeline" : "Run pipeline"}
        </Button>
      </div>

      {run.error && (
        <p className="w-full text-[0.8125rem] text-bad">{(run.error as Error).message}</p>
      )}
    </header>
  );
}

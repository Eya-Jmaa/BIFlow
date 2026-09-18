"use client";

import { api, type PipelineRun, type Project } from "@/lib/api";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export function Topbar({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: ["runs", project.id], queryFn: () => api.runs(project.id) });
  const latest: PipelineRun | undefined = runs.data?.[0];
  const run = useMutation({
    mutationFn: () => api.runPipeline(project.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs", project.id] });
    },
  });

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-[#0d1526] px-4 py-3">
      <div>
        <h1 className="text-sm font-semibold text-slate-100">{project.name}</h1>
        <p className="max-w-3xl truncate text-xs text-slate-400">{project.business_objective}</p>
      </div>
      <div className="flex items-center gap-3">
        <Badge tone={statusTone(latest?.status || project.status)}>{latest?.status || project.status}</Badge>
        {latest?.current_step && <span className="text-xs text-slate-400">Step: {latest.current_step}</span>}
        <Button onClick={() => run.mutate()} disabled={run.isPending || latest?.status === "running" || latest?.status === "queued"}>
          {run.isPending ? "Starting…" : "Run pipeline"}
        </Button>
      </div>
    </header>
  );
}

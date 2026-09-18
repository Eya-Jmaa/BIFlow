"use client";

import { Card } from "@/components/ui/card";
import { Badge, statusTone } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const datasets = useQuery({ queryKey: ["datasets", id], queryFn: () => api.datasets(id) });
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id) });
  const kpis = useQuery({ queryKey: ["kpis", id], queryFn: () => api.kpis(id), retry: false });
  const insights = useQuery({ queryKey: ["insights", id], queryFn: () => api.insights(id), retry: false });
  const latest = runs.data?.[0];

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Stat label="Datasets" value={String(datasets.data?.length ?? 0)} />
        <Stat label="Pipeline runs" value={String(runs.data?.length ?? 0)} />
        <Stat label="Computed KPIs" value={String(kpis.data?.length ?? 0)} />
        <Stat label="Insights" value={String(insights.data?.length ?? 0)} />
      </div>
      <Card>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Latest run</h2>
          {latest && <Badge tone={statusTone(latest.status)}>{latest.status}</Badge>}
        </div>
        {!latest && <p className="mt-2 text-sm text-slate-500">No pipeline has been executed yet. Upload datasets, then run the pipeline.</p>}
        {latest && (
          <div className="mt-3 space-y-1 text-sm text-slate-300">
            <p>Run ID: {latest.id}</p>
            <p>Model: {latest.llm_model || "deterministic engines only"}</p>
            <p>Current step: {latest.current_step || "—"}</p>
            {latest.error && <p className="text-red-400">{latest.error}</p>}
            <Link className="text-blue-400 hover:underline" href={`/projects/${id}/pipeline`}>
              Open pipeline
            </Link>
          </div>
        )}
      </Card>
      {kpis.data && kpis.data.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold">KPI snapshot</h2>
          <div className="grid gap-3 md:grid-cols-3">
            {kpis.data.slice(0, 6).map((kpi) => (
              <div key={kpi.id} className="rounded border border-slate-800 p-3">
                <p className="text-xs text-slate-500">{kpi.name}</p>
                <p className="text-xl font-semibold">{formatNumber(kpi.value)}</p>
                <p className="font-mono text-[11px] text-slate-500">{kpi.formula}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </Card>
  );
}

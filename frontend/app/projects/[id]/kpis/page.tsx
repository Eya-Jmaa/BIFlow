"use client";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { api, type KPI } from "@/lib/api";
import { formatNumber, formatPct } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

export default function KpiPage() {
  const { id } = useParams<{ id: string }>();
  const kpis = useQuery({ queryKey: ["kpis", id], queryFn: () => api.kpis(id), retry: false });
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["kpi", id, selected],
    queryFn: () => api.kpi(id, selected!),
    enabled: Boolean(selected),
  });

  if (kpis.isError) return <Card><p className="text-sm text-slate-400">KPI catalog is not available yet.</p></Card>;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-3">
        {kpis.data?.map((kpi: KPI) => (
          <button key={kpi.id} className="block w-full text-left" onClick={() => setSelected(kpi.id)}>
            <Card className="hover:border-slate-600">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{kpi.name}</p>
                  <p className="text-xs text-slate-500">{kpi.business_meaning}</p>
                </div>
                <Badge tone={statusTone(kpi.validation_status)}>{kpi.validation_status}</Badge>
              </div>
              <p className="mt-2 text-2xl font-semibold">{formatNumber(kpi.value)}</p>
              <p className="text-xs text-slate-400">{formatPct(kpi.change_pct)}</p>
              <p className="mt-2 font-mono text-[11px] text-slate-500">{kpi.formula}</p>
            </Card>
          </button>
        ))}
      </div>
      <Card>
        <h2 className="text-sm font-semibold">KPI explanation</h2>
        {!selected && <p className="mt-2 text-sm text-slate-500">Select a KPI to inspect formula, SQL, lineage and XAI.</p>}
        {detail.data ? <Detail payload={detail.data as Record<string, unknown>} /> : null}
      </Card>
    </div>
  );
}

function Detail({ payload }: { payload: Record<string, unknown> }) {
  const result = payload.result as Record<string, unknown>;
  const lineage = payload.lineage as Record<string, unknown>;
  const explanation = payload.explanation as Record<string, string> | null;
  return (
    <div className="mt-3 space-y-3 text-sm">
      <p>Value: {formatNumber(result.value as number)}</p>
      <p>SQL</p>
      <pre className="overflow-auto rounded bg-slate-950 p-3 text-[11px] text-slate-300">{String(result.query_sql || "")}</pre>
      <p>Tables: {JSON.stringify(lineage.tables)}</p>
      {explanation && (
        <div className="space-y-1 text-slate-300">
          <p><span className="text-slate-500">What happened:</span> {explanation.what_happened}</p>
          <p><span className="text-slate-500">How calculated:</span> {explanation.how_calculated}</p>
          <p><span className="text-slate-500">Data used:</span> {explanation.data_used}</p>
          <p><span className="text-slate-500">Assumptions:</span> {explanation.assumptions}</p>
          <p><span className="text-slate-500">Limitations:</span> {explanation.quality_limitations}</p>
          <p><span className="text-slate-500">Agents:</span> {explanation.producer_agent} → {explanation.validator_agent}</p>
        </div>
      )}
    </div>
  );
}

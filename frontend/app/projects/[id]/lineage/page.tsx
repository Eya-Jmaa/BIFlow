"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { ArrowRight, Waypoints } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/data";
import { api } from "@/lib/api";

type Graph = {
  kpi_name?: string;
  nodes: { id: string; label: string; type?: string }[];
  edges: { source: string; target: string; label: string }[];
};

export default function LineagePage() {
  const { id } = useParams<{ id: string }>();
  const lineage = useQuery({
    queryKey: ["lineage", id],
    queryFn: () => api.lineage(id) as Promise<{ kpis: Graph[] }>,
    retry: false,
  });

  if (lineage.isError) {
    return (
      <EmptyState
        title="No lineage yet"
        message="Once KPIs are computed, each one records the path from raw file to final number."
        icon={<Waypoints className="size-5" />}
      />
    );
  }

  const graphs = lineage.data?.kpis ?? [];

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader
          title="Data lineage"
          subtitle="Every KPI traced back through the layers it was computed from"
        />
        <p className="text-[0.8125rem] text-ink-muted">
          Raw files are never modified. Each stage below writes a new layer, so any number can be
          followed back to the bytes it came from.
        </p>
      </Card>

      {graphs.map((graph, index) => (
        <Card key={index}>
          {graph.kpi_name && (
            <p className="mb-3 text-[0.8125rem] font-medium text-ink">{graph.kpi_name}</p>
          )}
          <ol className="flex flex-wrap items-center gap-y-2">
            {graph.nodes.map((node, position) => (
              <li key={node.id} className="flex items-center">
                <span className="rounded-lg border border-line bg-surface-muted px-2.5 py-1.5 font-mono text-[0.6875rem] text-ink-soft">
                  {node.label}
                </span>
                {position < graph.nodes.length - 1 && (
                  <ArrowRight className="mx-1.5 size-3 shrink-0 text-ink-faint" aria-hidden />
                )}
              </li>
            ))}
          </ol>
        </Card>
      ))}
    </div>
  );
}

"use client";

import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function LineagePage() {
  const { id } = useParams<{ id: string }>();
  const lineage = useQuery({ queryKey: ["lineage", id], queryFn: () => api.lineage(id), retry: false });
  if (lineage.isError) return <Card><p className="text-sm text-slate-400">Lineage is not available yet.</p></Card>;
  const payload = lineage.data as { kpis?: Array<{ nodes: Array<{ id: string; label: string }>; edges: Array<{ source: string; target: string; label: string }> }> };

  return (
    <div className="space-y-4">
      {(payload?.kpis || []).map((graph, index) => (
        <Card key={index}>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {graph.nodes.map((node, i) => (
              <span key={node.id} className="flex items-center gap-2">
                <span className="rounded border border-slate-700 px-2 py-1">{node.label}</span>
                {i < graph.nodes.length - 1 && <span className="text-slate-600">→</span>}
              </span>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

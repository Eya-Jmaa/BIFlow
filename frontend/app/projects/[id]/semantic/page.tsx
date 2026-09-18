"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

type Semantic = {
  domain: string;
  summary: string;
  dimensions: Array<{ name: string; table_name: string; column_name: string; dim_type: string }>;
  measures: Array<{ name: string; table_name: string; column_name: string; aggregation: string; unit: string | null }>;
  relationships: Array<{
    source_table: string;
    source_column: string;
    target_table: string;
    target_column: string;
    cardinality: string;
    confidence: number;
    validated: boolean;
    overlap_ratio: number | null;
  }>;
};

export default function SemanticPage() {
  const { id } = useParams<{ id: string }>();
  const semantic = useQuery({ queryKey: ["semantic", id], queryFn: () => api.semantic(id), retry: false });
  if (semantic.isError) return <Card><p className="text-sm text-slate-400">Semantic model not available yet.</p></Card>;
  const model = semantic.data as Semantic | undefined;
  if (!model) return <Card><p className="text-sm text-slate-400">Loading…</p></Card>;

  return (
    <div className="space-y-4">
      <Card>
        <p className="text-xs uppercase text-slate-500">Domain</p>
        <p className="text-lg font-semibold">{model.domain}</p>
        <p className="text-sm text-slate-400">{model.summary}</p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-2 text-sm font-semibold">Dimensions</h2>
          <ul className="space-y-1 text-sm">
            {model.dimensions.map((d) => (
              <li key={d.name} className="flex justify-between gap-2 border-b border-slate-800 py-1">
                <span>{d.name}</span>
                <Badge>{d.dim_type}</Badge>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2 className="mb-2 text-sm font-semibold">Measures</h2>
          <ul className="space-y-1 text-sm">
            {model.measures.map((m) => (
              <li key={m.name} className="flex justify-between gap-2 border-b border-slate-800 py-1">
                <span>{m.name}</span>
                <span className="text-xs text-slate-500">{m.aggregation}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <Card>
        <h2 className="mb-2 text-sm font-semibold">Validated relationships</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="pb-2">Source</th>
              <th>Target</th>
              <th>Cardinality</th>
              <th>Overlap</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {model.relationships.map((r) => (
              <tr key={`${r.source_table}.${r.source_column}-${r.target_table}.${r.target_column}`} className="border-t border-slate-800">
                <td className="py-1.5">{r.source_table}.{r.source_column}</td>
                <td>{r.target_table}.{r.target_column}</td>
                <td>{r.cardinality}</td>
                <td>{r.overlap_ratio ?? "—"}</td>
                <td>{r.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

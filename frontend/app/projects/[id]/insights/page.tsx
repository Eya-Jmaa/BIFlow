"use client";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { api, type Insight } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

const sections = [
  { key: "finding", title: "Key findings" },
  { key: "trend", title: "Trends" },
  { key: "anomaly", title: "Anomalies" },
  { key: "opportunity", title: "Opportunities" },
  { key: "risk", title: "Risks" },
  { key: "quality_caveat", title: "Data quality caveats" },
];

export default function InsightsPage() {
  const { id } = useParams<{ id: string }>();
  const insights = useQuery({ queryKey: ["insights", id], queryFn: () => api.insights(id), retry: false });
  if (insights.isError) return <Card><p className="text-sm text-slate-400">Insights are not available yet.</p></Card>;
  const items = insights.data || [];
  const exec = items.filter((i) => i.category === "finding" || i.category === "trend").slice(0, 3);

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="text-sm font-semibold">Executive summary</h2>
        {exec.length === 0 && <p className="mt-2 text-sm text-slate-500">No grounded insights yet.</p>}
        <ul className="mt-2 space-y-2">
          {exec.map((item) => (
            <li key={item.id} className="text-sm text-slate-300">{item.description}</li>
          ))}
        </ul>
      </Card>
      {sections.map((section) => {
        const group = items.filter((i) => i.category === section.key);
        if (!group.length) return null;
        return (
          <div key={section.key} className="space-y-2">
            <h2 className="text-sm font-semibold">{section.title}</h2>
            {group.map((item) => (
              <InsightCard key={item.id} item={item} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function InsightCard({ item }: { item: Insight }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium">{item.title}</p>
          <p className="mt-1 text-sm text-slate-300">{item.description}</p>
        </div>
        <Badge tone={statusTone(item.severity)}>{item.severity}</Badge>
      </div>
      <dl className="mt-3 grid gap-1 text-xs text-slate-400 md:grid-cols-2">
        <div>Metric: {item.metric || "—"}</div>
        <div>Value: {formatNumber(item.value)}</div>
        <div>Comparison: {item.comparison || "—"}</div>
        <div>Confidence: {item.confidence}</div>
        <div>Grounded: {item.grounded ? "yes" : "no"}</div>
      </dl>
      <pre className="mt-2 overflow-auto rounded bg-slate-950 p-2 text-[11px] text-slate-400">
        {JSON.stringify(item.evidence, null, 2)}
      </pre>
    </Card>
  );
}

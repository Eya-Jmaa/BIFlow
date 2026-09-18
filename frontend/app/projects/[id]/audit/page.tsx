"use client";

import { Card } from "@/components/ui/card";
import { Badge, statusTone } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const audit = useQuery({ queryKey: ["audit", id], queryFn: () => api.audit(id), retry: false });
  const evaluation = useQuery({ queryKey: ["evaluation", id], queryFn: () => api.evaluation(id), retry: false });
  if (audit.isError) return <Card><p className="text-sm text-slate-400">Audit artifacts are not available yet.</p></Card>;
  const data = audit.data as { events?: Array<Record<string, string>>; explanations?: Array<Record<string, string>> } | undefined;

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Validation events</h2>
        <div className="space-y-2">
          {(data?.events || []).map((event) => (
            <div key={event.id} className="flex items-start justify-between gap-3 border-b border-slate-800 pb-2 text-sm">
              <div>
                <p>{event.message}</p>
                <p className="text-xs text-slate-500">{event.event_type} · {event.entity_type}</p>
              </div>
              <Badge tone={statusTone(event.status || event.severity)}>{event.status}</Badge>
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <h2 className="mb-3 text-sm font-semibold">XAI explanations</h2>
        {(data?.explanations || []).map((x) => (
          <div key={x.id} className="mb-4 border-b border-slate-800 pb-3 text-sm">
            <p className="font-medium">{x.entity_type}</p>
            <p className="mt-1 text-slate-300">{x.what_happened}</p>
            <p className="text-slate-400">{x.how_calculated}</p>
            <p className="text-xs text-slate-500">Producer {x.producer_agent} · Validator {x.validator_agent}</p>
          </div>
        ))}
      </Card>
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Evaluation</h2>
        <ul className="space-y-1 text-sm">
          {((evaluation.data as Array<Record<string, unknown>>) || []).map((row, idx) => (
            <li key={idx}>
              {String(row.agent_name)} · {String(row.metric_name)} · score {String(row.score)}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

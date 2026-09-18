"use client";

import { WidgetView } from "@/components/widget-view";
import { Card } from "@/components/ui/card";
import { Badge, statusTone } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const dash = useQuery({ queryKey: ["dashboard", id], queryFn: () => api.dashboard(id), retry: false });
  if (dash.isError) return <Card><p className="text-sm text-slate-400">Dashboard is not available yet. Run the pipeline first.</p></Card>;
  if (!dash.data) return <Card><p className="text-sm text-slate-400">Loading dashboard…</p></Card>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">{dash.data.title}</h2>
        <Badge tone={statusTone(dash.data.audit_status)}>{dash.data.audit_status}</Badge>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {dash.data.widgets.map((widget) => (
          <div key={widget.id} className={widget.width >= 8 ? "md:col-span-2 xl:col-span-3" : widget.width >= 6 ? "md:col-span-2" : ""}>
            <WidgetView widget={widget} />
          </div>
        ))}
      </div>
    </div>
  );
}

"use client";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatNumber, formatPct } from "@/lib/utils";
import type { Widget } from "@/lib/api";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function WidgetView({ widget }: { widget: Widget }) {
  if (widget.widget_type === "kpi") {
    return (
      <Card className="h-full">
        <p className="text-xs uppercase tracking-wide text-slate-500">{widget.title}</p>
        <p className="mt-2 text-2xl font-semibold text-slate-50">{formatNumber(widget.data.value)}</p>
        <p className="mt-1 text-xs text-slate-400">{formatPct(widget.data.change_pct)} vs previous period</p>
      </Card>
    );
  }
  if (widget.widget_type === "line" || widget.widget_type === "area") {
    const data = widget.data.series || [];
    return (
      <Card className="h-full">
        <p className="mb-3 text-sm font-medium text-slate-200">{widget.title}</p>
        {data.length === 0 ? (
          <Empty label="No time dimension available for this KPI" />
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data}>
                <CartesianGrid stroke="#1e293b" />
                <XAxis dataKey="period" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #1e293b" }} />
                <Line type="monotone" dataKey="value" stroke="#3b82f6" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    );
  }
  if (widget.widget_type === "bar" || widget.widget_type === "ranking") {
    const data = widget.data.breakdown || [];
    return (
      <Card className="h-full">
        <p className="mb-3 text-sm font-medium text-slate-200">{widget.title}</p>
        {data.length === 0 ? (
          <Empty label="No categorical breakdown computed" />
        ) : (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid stroke="#1e293b" />
                <XAxis dataKey="dimension" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #1e293b" }} />
                <Bar dataKey="value" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    );
  }
  if (widget.widget_type === "table") {
    const rows = widget.data.breakdown || [];
    return (
      <Card className="h-full overflow-auto">
        <p className="mb-3 text-sm font-medium text-slate-200">{widget.title}</p>
        {rows.length === 0 ? (
          <Empty label="No tabular result" />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="pb-2">Dimension</th>
                <th className="pb-2">Value</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.dimension} className="border-t border-slate-800">
                  <td className="py-1.5">{row.dimension}</td>
                  <td className="py-1.5">{formatNumber(row.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    );
  }
  if (widget.widget_type === "anomaly") {
    return (
      <Card className="h-full">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-slate-200">{widget.title}</p>
          <Badge tone={statusTone("warning")}>statistical</Badge>
        </div>
        <p className="text-sm text-slate-400">
          Anomalies are computed with z-score and IQR on the KPI series. Open Insights for evidence.
        </p>
        {widget.explanation && <p className="mt-2 text-xs text-slate-500">{widget.explanation}</p>}
      </Card>
    );
  }
  return (
    <Card>
      <p className="text-sm font-medium">{widget.title}</p>
      <Empty label={`No renderer for widget type ${widget.widget_type}`} />
    </Card>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="text-sm text-slate-500">{label}</p>;
}

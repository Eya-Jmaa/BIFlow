"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { CHROME, SERIES, STATUS, deltaTone, formatValue, shortPeriod } from "@/lib/viz";
import type { ValueFormat } from "@/lib/viz";
import type { Widget } from "@/lib/api";
import { cn } from "@/lib/utils";

type Point = { period: string; value: number | null; partial?: boolean };
type Segment = { dimension: string; value: number | null };

// Enough bars to show a distribution, few enough that each keeps a readable
// label at card height.
const MAX_BARS = 8;

/**
 * Every chart ships with a table view.
 *
 * A tooltip enhances a chart, it never gates it: the exact numbers behind any
 * plot must be reachable without hovering, for keyboard users, for screen
 * readers, and for anyone printing the page.
 */
function ChartFrame({
  title,
  subtitle,
  children,
  table,
  dim,
  onDrill,
  drillLabel,
}: {
  title: string;
  subtitle?: string | null;
  children: React.ReactNode;
  table: React.ReactNode;
  dim?: boolean;
  onDrill?: () => void;
  drillLabel?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <Card className="flex h-full flex-col">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-200">{title}</p>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 gap-1">
          {onDrill && (
            <button
              type="button"
              onClick={onDrill}
              className="rounded border border-slate-800 px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-900"
            >
              {drillLabel ?? "Drill in"}
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowTable((value) => !value)}
            aria-pressed={showTable}
            className="rounded border border-slate-800 px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-900"
          >
            {showTable ? "Chart" : "Table"}
          </button>
        </div>
      </div>
      {/* Refetching holds the previous render at reduced opacity rather than
          collapsing to a skeleton, so the layout never jumps. */}
      <div className={cn("flex-1 transition-opacity", dim && "opacity-40")}>
        {showTable ? table : children}
      </div>
    </Card>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
  format,
  unit,
  labelFormatter,
}: {
  active?: boolean;
  payload?: { value: number; payload: Record<string, unknown> }[];
  label?: string;
  format?: ValueFormat;
  unit?: string | null;
  labelFormatter?: (value: string) => string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0];
  const partial = Boolean((point.payload as { partial?: boolean }).partial);
  return (
    <div className="rounded border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-xs shadow-lg">
      <p className="text-slate-400">{labelFormatter ? labelFormatter(label ?? "") : label}</p>
      <p className="mt-0.5 font-medium text-slate-100">
        {formatValue(point.value, format, { unit })}
      </p>
      {partial && (
        <p className="mt-1 max-w-48 text-[11px] text-amber-400">
          ⚠ Incomplete period — the data stops part-way through it.
        </p>
      )}
    </div>
  );
}

function ValueTable({
  rows,
  keyLabel,
  format,
  unit,
}: {
  rows: { key: string; value: number | null; note?: string }[];
  keyLabel: string;
  format?: ValueFormat;
  unit?: string | null;
}) {
  if (!rows.length) return <Empty label="No data" />;
  return (
    <div className="max-h-56 overflow-auto">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-950 text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            <th className="pb-1.5 font-medium">{keyLabel}</th>
            <th className="pb-1.5 text-right font-medium">Value</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-slate-800/70">
              <td className="py-1 pr-2 text-slate-300">
                {row.key}
                {row.note && <span className="ml-1 text-amber-500">{row.note}</span>}
              </td>
              <td className="py-1 text-right text-slate-200">
                {formatValue(row.value, format, { unit })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function WidgetView({
  widget,
  dim,
  onDrill,
}: {
  widget: Widget;
  dim?: boolean;
  onDrill?: (kpiId: string | null) => void;
}) {
  const format = (widget.data.format ?? {}) as ValueFormat;
  const unit = widget.data.unit ?? null;

  if (widget.widget_type === "kpi") {
    const delta = deltaTone(widget.data.change_pct, true);
    return (
      <Card className="h-full">
        <p className="truncate text-xs uppercase tracking-wide text-slate-500">{widget.title}</p>
        {/* Hero figure: proportional digits, same sans as the rest of the UI. */}
        <p className="mt-2 text-3xl font-semibold text-slate-50">
          {formatValue(widget.data.value, format, { unit, compact: true })}
        </p>
        {delta ? (
          <p className="mt-1.5 flex items-center gap-1 text-xs">
            {/* Arrow + word, so the direction never rests on colour alone. */}
            <span style={{ color: delta.color }}>{delta.arrow}</span>
            <span style={{ color: delta.color }}>
              {Math.abs((widget.data.change_pct ?? 0) * 100).toFixed(1)}% {delta.label}
            </span>
            <span className="text-slate-500">vs previous period</span>
          </p>
        ) : (
          <p className="mt-1.5 text-xs text-slate-500">No comparable previous period</p>
        )}
        {widget.explanation && (
          <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-slate-600">
            {widget.explanation}
          </p>
        )}
      </Card>
    );
  }

  if (widget.widget_type === "line" || widget.widget_type === "area") {
    const data = (widget.data.series ?? []) as Point[];
    const complete = data.filter((point) => !point.partial);
    const partialCount = data.length - complete.length;
    return (
      <ChartFrame
        title={widget.title}
        subtitle={
          partialCount
            ? `${complete.length} complete periods · last point incomplete, excluded from comparisons`
            : `${data.length} periods`
        }
        dim={dim}
        onDrill={onDrill ? () => onDrill(widget.kpi_id) : undefined}
        drillLabel="Explore"
        table={
          <ValueTable
            keyLabel="Period"
            format={format}
            unit={unit}
            rows={data.map((point) => ({
              key: point.period,
              value: point.value,
              note: point.partial ? "(incomplete)" : undefined,
            }))}
          />
        }
      >
        {data.length === 0 ? (
          <Empty label="No date dimension was bound for this KPI" />
        ) : (
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                <CartesianGrid stroke={CHROME.grid} strokeWidth={1} vertical={false} />
                <XAxis
                  dataKey="period"
                  tickFormatter={shortPeriod}
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={{ stroke: CHROME.axis }}
                  tickLine={false}
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={52}
                  tickFormatter={(value: number) =>
                    formatValue(value, format, { unit, compact: true })
                  }
                />
                <Tooltip
                  cursor={{ stroke: CHROME.axis, strokeWidth: 1 }}
                  content={
                    <ChartTooltip format={format} unit={unit} labelFormatter={shortPeriod} />
                  }
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={SERIES[0]}
                  strokeWidth={2}
                  dot={(props: {
                    cx?: number;
                    cy?: number;
                    payload?: Point;
                    index?: number;
                  }) =>
                    // The incomplete period is drawn hollow: visible, but marked
                    // as not comparable with the rest of the line.
                    props.payload?.partial && props.cx !== undefined && props.cy !== undefined ? (
                      <circle
                        key={props.index}
                        cx={props.cx}
                        cy={props.cy}
                        r={4}
                        fill={CHROME.tooltipBg}
                        stroke={STATUS.warning}
                        strokeWidth={2}
                      />
                    ) : (
                      <g key={props.index} />
                    )
                  }
                  activeDot={{ r: 5, stroke: CHROME.tooltipBg, strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </ChartFrame>
    );
  }

  if (widget.widget_type === "bar" || widget.widget_type === "ranking") {
    const data = (widget.data.breakdown ?? []) as Segment[];
    const visible = data.slice(0, MAX_BARS);
    return (
      <ChartFrame
        title={widget.title}
        subtitle={data.length ? `Top ${Math.min(data.length, MAX_BARS)} of ${data.length} segments` : null}
        dim={dim}
        onDrill={onDrill ? () => onDrill(widget.kpi_id) : undefined}
        drillLabel="Explore"
        table={
          <ValueTable
            keyLabel="Segment"
            format={format}
            unit={unit}
            rows={data.map((segment) => ({ key: segment.dimension, value: segment.value }))}
          />
        }
      >
        {data.length === 0 ? (
          <Empty label="No chartable dimension was found for this KPI" />
        ) : (
          <div style={{ height: Math.max(180, visible.length * 26 + 40) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={visible}
                layout="vertical"
                margin={{ top: 4, right: 12, bottom: 4, left: 4 }}
                barCategoryGap={2}
              >
                <CartesianGrid stroke={CHROME.grid} strokeWidth={1} horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value: number) =>
                    formatValue(value, format, { unit, compact: true })
                  }
                />
                <YAxis
                  type="category"
                  dataKey="dimension"
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={104}
                  // Every bar gets its own label; interval skipping would leave
                  // labels sitting beside the wrong bars.
                  interval={0}
                />
                <Tooltip
                  cursor={{ fill: "#1e293b40" }}
                  content={<ChartTooltip format={format} unit={unit} />}
                />
                {/* One series, one colour. Colouring bars by magnitude would
                    re-encode length as hue and say nothing new. */}
                <Bar
                  dataKey="value"
                  fill={SERIES[0]}
                  radius={[0, 4, 4, 0]}
                  maxBarSize={22}
                  isAnimationActive={false}
                >
                  {visible.map((segment) => (
                    <Cell key={segment.dimension} fill={SERIES[0]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </ChartFrame>
    );
  }

  if (widget.widget_type === "table") {
    const rows = widget.data.rows ?? [];
    return (
      <Card className="h-full">
        <p className="mb-3 text-sm font-medium text-slate-200">{widget.title}</p>
        {rows.length === 0 ? (
          <Empty label="No computed KPIs" />
        ) : (
          <div className="max-h-72 overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-950 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="pb-1.5 font-medium">KPI</th>
                  <th className="pb-1.5 text-right font-medium">Value</th>
                  <th className="hidden pb-1.5 pl-4 font-medium md:table-cell">Formula</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.name} className="border-t border-slate-800/70 align-top">
                    <td className="py-1.5 pr-2 text-slate-300">{row.name}</td>
                    <td className="py-1.5 text-right tabular-nums text-slate-100">
                      {formatValue(row.value, {}, { unit: row.unit })}
                    </td>
                    <td className="hidden py-1.5 pl-4 font-mono text-[11px] text-slate-500 md:table-cell">
                      {row.formula}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    );
  }

  if (widget.widget_type === "anomaly") {
    const groups = widget.data.anomalies ?? [];
    const flagged = groups.flatMap((group) =>
      (group.anomalies ?? []).map((item) => ({ metric: group.metric, ...item })),
    );
    return (
      <Card className="h-full">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium text-slate-200">{widget.title}</p>
          <Badge tone={statusTone(flagged.length ? "warning" : "completed")}>
            {flagged.length ? `${flagged.length} flagged` : "none"}
          </Badge>
        </div>
        {flagged.length === 0 ? (
          <p className="text-xs text-slate-500">
            No point in any KPI series exceeded the z-score or IQR thresholds.
          </p>
        ) : (
          <div className="max-h-56 overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-950 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="pb-1.5 font-medium">Metric</th>
                  <th className="pb-1.5 pl-3 font-medium">Period</th>
                  <th className="pb-1.5 text-right font-medium">Value</th>
                  <th className="pb-1.5 pl-3 font-medium">Test</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {flagged.slice(0, 20).map((item, index) => (
                  <tr key={`${item.metric}-${index}`} className="border-t border-slate-800/70">
                    <td className="py-1 pr-2 text-slate-300">{item.metric}</td>
                    <td className="py-1 pl-3 text-slate-400">
                      {item.period ? shortPeriod(item.period) : "—"}
                    </td>
                    <td className="py-1 text-right text-slate-200">
                      {formatValue(item.value, {}, { unit: item.unit })}
                    </td>
                    <td className="py-1 pl-3 text-slate-500">
                      {item.method}
                      {item.zscore !== undefined && ` z=${item.zscore.toFixed(2)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {widget.explanation && (
          <p className="mt-2 text-[11px] text-slate-600">{widget.explanation}</p>
        )}
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
  return (
    <div className="flex h-full min-h-24 items-center justify-center">
      <p className="text-center text-xs text-slate-500">{label}</p>
    </div>
  );
}

"use client";

import { useState } from "react";
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
import { Maximize2 } from "lucide-react";

import { CHROME, SERIES, STATUS, deltaOf, formatValue, shortPeriod } from "@/lib/viz";
import type { ValueFormat } from "@/lib/viz";
import type { Widget } from "@/lib/api";
import {
  Badge,
  DataTable,
  Panel,
  Segment,
  SegmentGroup,
  Td,
  Tr,
} from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

type Point = { period: string; value: number | null; partial?: boolean };
type SegmentRow = { dimension: string; value: number | null };

// Enough bars to show a distribution, few enough that each keeps a readable
// label at card height.
const MAX_BARS = 8;

/**
 * Every chart ships with a table view.
 *
 * A tooltip enhances a chart, it never gates it: the exact numbers behind any
 * plot stay reachable without hovering — for keyboard users, for screen
 * readers, and for anyone printing the page.
 */
function ChartFrame({
  title,
  subtitle,
  children,
  table,
  dim,
  onDrill,
}: {
  title: string;
  subtitle?: string | null;
  children: React.ReactNode;
  table: React.ReactNode;
  dim?: boolean;
  onDrill?: () => void;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <Panel className="flex h-full flex-col">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[0.9375rem] font-semibold tracking-tight text-ink">{title}</p>
          {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {onDrill && (
            <button
              type="button"
              onClick={onDrill}
              className="grid size-7 place-items-center rounded-md text-ink-faint transition-colors hover:bg-inset hover:text-ink"
              title="Explore this metric"
            >
              <Maximize2 className="size-3.5" aria-hidden />
              <span className="sr-only">Explore</span>
            </button>
          )}
          <div className="flex rounded-lg bg-inset p-0.5">
            <Segment active={!showTable} onClick={() => setShowTable(false)}>
              Chart
            </Segment>
            <Segment active={showTable} onClick={() => setShowTable(true)}>
              Table
            </Segment>
          </div>
        </div>
      </div>
      {/* Refetching holds the previous render at reduced opacity rather than
          collapsing to a skeleton, so the layout never jumps. */}
      <div className={cn("flex-1 transition-opacity duration-200", dim && "opacity-40")}>
        {showTable ? table : children}
      </div>
    </Panel>
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
    <div className="rounded-lg border border-line bg-raised px-3 py-2 shadow-lift">
      <p className="text-[0.6875rem] text-ink-muted">
        {labelFormatter ? labelFormatter(label ?? "") : label}
      </p>
      <p className="mt-0.5 text-sm font-semibold text-ink">
        {formatValue(point.value, format, { unit })}
      </p>
      {partial && (
        <p className="mt-1.5 max-w-52 text-[0.6875rem] leading-snug text-warn">
          Incomplete period — the data stops part-way through it.
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
    <div className="max-h-60 overflow-auto">
      <DataTable
        head={[
          keyLabel,
          <span key="value" className="block text-right">
            Value
          </span>,
        ]}
      >
        {rows.map((row) => (
          <Tr key={row.key}>
            <Td>
              {row.key}
              {row.note && <span className="ml-1.5 text-warn">{row.note}</span>}
            </Td>
            <Td numeric>{formatValue(row.value, format, { unit })}</Td>
          </Tr>
        ))}
      </DataTable>
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
  onDrill?: () => void;
}) {
  const format = (widget.data.format ?? {}) as ValueFormat;
  const unit = widget.data.unit ?? null;

  if (widget.widget_type === "kpi") {
    const delta = deltaOf(widget.data.change_pct, true);
    return (
      <Panel className="h-full">
        <p className="truncate text-[0.8125rem] font-medium text-ink-muted">{widget.title}</p>
        {/* Hero figure: proportional digits, same sans as the rest of the UI. */}
        <p className="mt-2 text-[1.75rem] leading-none font-semibold tracking-tight text-ink">
          {formatValue(widget.data.value, format, { unit, compact: true })}
        </p>
        {delta ? (
          <p className="mt-2.5 flex flex-wrap items-center gap-1.5 text-xs">
            <span
              className={cn(
                "font-medium",
                delta.favourable === null
                  ? "text-ink-muted"
                  : delta.favourable
                    ? "text-good"
                    : "text-bad",
              )}
            >
              {delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "—"} {delta.value}{" "}
              {delta.direction}
            </span>
            <span className="text-ink-faint">vs previous period</span>
          </p>
        ) : (
          <p className="mt-2.5 text-xs text-ink-faint">No comparable previous period</p>
        )}
        {widget.explanation && (
          <p className="mt-3 line-clamp-2 text-[0.6875rem] leading-relaxed text-ink-faint">
            {widget.explanation}
          </p>
        )}
      </Panel>
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
        onDrill={onDrill}
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
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 14, bottom: 4, left: 0 }}>
                <CartesianGrid stroke={CHROME.grid} strokeWidth={1} vertical={false} />
                <XAxis
                  dataKey="period"
                  tickFormatter={shortPeriod}
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={{ stroke: CHROME.axis }}
                  tickLine={false}
                  minTickGap={26}
                  dy={4}
                />
                <YAxis
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={56}
                  tickFormatter={(value: number) =>
                    formatValue(value, format, { unit, compact: true })
                  }
                />
                <Tooltip
                  cursor={{ stroke: CHROME.axis, strokeWidth: 1 }}
                  content={<ChartTooltip format={format} unit={unit} labelFormatter={shortPeriod} />}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={SERIES[0]}
                  strokeWidth={2}
                  dot={(props: { cx?: number; cy?: number; payload?: Point; index?: number }) =>
                    // The incomplete period is drawn hollow: visible, but
                    // marked as not comparable with the rest of the line.
                    props.payload?.partial && props.cx !== undefined && props.cy !== undefined ? (
                      <circle
                        key={props.index}
                        cx={props.cx}
                        cy={props.cy}
                        r={4}
                        fill={CHROME.surface}
                        stroke={STATUS.warn}
                        strokeWidth={2}
                      />
                    ) : (
                      <g key={props.index} />
                    )
                  }
                  activeDot={{ r: 5, stroke: CHROME.surface, strokeWidth: 2 }}
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
    const data = (widget.data.breakdown ?? []) as SegmentRow[];
    const visible = data.slice(0, MAX_BARS);
    return (
      <ChartFrame
        title={widget.title}
        subtitle={
          data.length ? `Top ${Math.min(data.length, MAX_BARS)} of ${data.length} segments` : null
        }
        dim={dim}
        onDrill={onDrill}
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
          <div style={{ height: Math.max(184, visible.length * 28 + 40) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={visible}
                layout="vertical"
                margin={{ top: 4, right: 14, bottom: 4, left: 0 }}
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
                  cursor={{ fill: "#12142a0a" }}
                  content={<ChartTooltip format={format} unit={unit} />}
                />
                {/* One series, one colour. Colouring bars by magnitude would
                    re-encode length as hue and say nothing new. */}
                <Bar
                  dataKey="value"
                  fill={SERIES[0]}
                  radius={[0, 4, 4, 0]}
                  maxBarSize={20}
                  isAnimationActive={false}
                />
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
      <Panel className="h-full">
        <p className="mb-4 text-[0.9375rem] font-semibold tracking-tight text-ink">{widget.title}</p>
        {rows.length === 0 ? (
          <Empty label="No computed KPIs" />
        ) : (
          <div className="max-h-80 overflow-auto">
            <DataTable
              head={[
                "KPI",
                <span key="value" className="block text-right">
                  Value
                </span>,
                <span key="formula" className="hidden md:block">
                  Formula
                </span>,
              ]}
            >
              {rows.map((row) => (
                <Tr key={row.name}>
                  <Td className="font-medium text-ink">{row.name}</Td>
                  <Td numeric>{formatValue(row.value, {}, { unit: row.unit })}</Td>
                  <Td className="hidden font-mono text-[0.625rem] text-ink-faint md:table-cell">
                    {row.formula}
                  </Td>
                </Tr>
              ))}
            </DataTable>
          </div>
        )}
      </Panel>
    );
  }

  if (widget.widget_type === "anomaly") {
    const groups = widget.data.anomalies ?? [];
    const flagged = groups.flatMap((group) =>
      (group.anomalies ?? []).map((item) => ({ metric: group.metric, ...item })),
    );
    return (
      <Panel className="h-full">
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="text-[0.9375rem] font-semibold tracking-tight text-ink">{widget.title}</p>
          <Badge tone={flagged.length ? "warn" : "good"} dot>
            {flagged.length ? `${flagged.length} flagged` : "none"}
          </Badge>
        </div>
        {flagged.length === 0 ? (
          <p className="text-[0.8125rem] text-ink-muted">
            No point in any KPI series exceeded the z-score or IQR thresholds.
          </p>
        ) : (
          <div className="max-h-60 overflow-auto">
            <DataTable
              head={[
                "Metric",
                "Period",
                <span key="value" className="block text-right">
                  Value
                </span>,
                "Test",
              ]}
            >
              {flagged.slice(0, 20).map((item, index) => (
                <Tr key={`${item.metric}-${index}`}>
                  <Td className="font-medium text-ink">{item.metric}</Td>
                  <Td>{item.period ? shortPeriod(item.period) : "—"}</Td>
                  <Td numeric>{formatValue(item.value, {}, { unit: item.unit })}</Td>
                  <Td className="text-ink-faint">
                    {item.method}
                    {item.zscore !== undefined && ` z=${item.zscore.toFixed(2)}`}
                  </Td>
                </Tr>
              ))}
            </DataTable>
          </div>
        )}
        {widget.explanation && (
          <p className="mt-3 text-[0.6875rem] text-ink-faint">{widget.explanation}</p>
        )}
      </Panel>
    );
  }

  return (
    <Panel>
      <p className="text-[0.9375rem] font-semibold text-ink">{widget.title}</p>
      <Empty label={`No renderer for widget type ${widget.widget_type}`} />
    </Panel>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <div className="flex h-full min-h-28 items-center justify-center">
      <p className="max-w-xs text-center text-[0.8125rem] text-ink-faint">{label}</p>
    </div>
  );
}

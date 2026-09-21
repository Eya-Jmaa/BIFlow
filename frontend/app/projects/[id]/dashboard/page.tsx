"use client";

import { useMemo, useState } from "react";
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { LayoutDashboard, X } from "lucide-react";

import { DashboardFilters, EMPTY_FILTERS, buildFilters } from "@/components/dashboard-filters";
import type { FilterState } from "@/components/dashboard-filters";
import { WidgetView } from "@/components/widget-view";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/data";
import { api } from "@/lib/api";
import type { Widget } from "@/lib/api";
import { CHROME, SERIES, formatValue } from "@/lib/viz";
import { cn } from "@/lib/utils";

// The generator lays widgets out on a 12-column grid, so the grid here is 12
// wide too: a w=8 chart and a w=4 chart then share one row, as intended.
// Tailwind needs literal class names, so the span map is spelled out.
const SPAN: Record<number, string> = {
  3: "xl:col-span-3",
  4: "md:col-span-2 xl:col-span-4",
  6: "md:col-span-2 xl:col-span-6",
  8: "md:col-span-2 xl:col-span-8",
  12: "md:col-span-2 xl:col-span-12",
};

export default function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [drill, setDrill] = useState<{ slug: string; name: string } | null>(null);

  const dashboard = useQuery({
    queryKey: ["dashboard", id],
    queryFn: () => api.dashboard(id),
    retry: false,
  });
  const options = useQuery({
    queryKey: ["filter-options", id],
    queryFn: () => api.filterOptions(id),
    retry: false,
  });

  const dateColumn = options.data?.dimensions.find((item) => item.type === "datetime")?.name ?? null;
  const active = buildFilters(filters, dateColumn);
  const filtersOn = active.length > 0;

  const kpiBySlug = useMemo(() => {
    const map = new Map<string, { slug: string; name: string }>();
    for (const kpi of options.data?.kpis ?? []) map.set(kpi.slug, kpi);
    return map;
  }, [options.data]);

  const widgets = dashboard.data?.widgets ?? [];
  const queryable = widgets.filter(
    (widget) => widget.kpi_id && ["kpi", "line", "bar", "ranking"].includes(widget.widget_type),
  );

  const slugFor = (widget: Widget) => {
    const title = widget.title.toLowerCase();
    for (const kpi of options.data?.kpis ?? []) {
      if (title.startsWith(kpi.name.toLowerCase())) return kpi.slug;
    }
    return null;
  };

  // Each widget re-queries against the same slice, so every number on the page
  // describes the same subset of the data.
  const results = useQueries({
    queries: queryable.map((widget) => {
      const slug = slugFor(widget);
      const isSeries = widget.widget_type === "line";
      const isBreakdown = widget.widget_type === "bar" || widget.widget_type === "ranking";
      const dimension = isSeries
        ? dateColumn
        : isBreakdown
          ? (filters.dimension ??
            options.data?.dimensions.find((item) => item.type !== "datetime")?.name ??
            null)
          : null;
      return {
        queryKey: ["widget-query", id, slug, dimension, filters.grain, active],
        queryFn: () =>
          api.queryKpi(id, {
            kpi_slug: slug as string,
            dimension,
            grain: isSeries ? filters.grain : null,
            filters: active,
            limit: 12,
          }),
        enabled: Boolean(slug) && filtersOn && Boolean(options.data),
        placeholderData: keepPreviousData,
        retry: false,
      };
    }),
  });

  const busy = results.some((result) => result.isFetching);

  if (dashboard.isError) {
    return (
      <EmptyState
        title="No dashboard yet"
        message="Run the pipeline and the dashboard agent will build one from the computed KPIs."
        icon={<LayoutDashboard className="size-5" />}
      />
    );
  }

  if (!dashboard.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-full" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }

  /** Overlay the filtered result onto the widget the pipeline precomputed. */
  const withFilters = (widget: Widget): Widget => {
    const index = queryable.indexOf(widget);
    if (index < 0 || !filtersOn) return widget;
    const result = results[index]?.data;
    if (!result) return widget;

    if (widget.widget_type === "kpi") {
      return {
        ...widget,
        data: {
          ...widget.data,
          value: result.rows[0]?.value ?? null,
          // A previous-period comparison does not survive an arbitrary slice,
          // so it is dropped rather than left showing the unfiltered delta.
          change_pct: null,
          previous_value: null,
        },
      };
    }
    if (widget.widget_type === "line") {
      return {
        ...widget,
        data: {
          ...widget.data,
          series: result.rows.map((row) => ({
            period: String(row.dimension ?? ""),
            value: row.value,
          })),
        },
      };
    }
    return {
      ...widget,
      data: {
        ...widget.data,
        breakdown: result.rows.map((row) => ({
          dimension: String(row.dimension ?? ""),
          value: row.value,
        })),
      },
    };
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[0.9375rem] font-semibold tracking-tight text-ink">
            {dashboard.data.title}
          </h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            {filtersOn
              ? `Filtered view — ${active.length} filter${active.length > 1 ? "s" : ""} applied to every tile below`
              : `${widgets.length} widgets, each bound to a computed metric`}
          </p>
        </div>
        <Badge tone={statusTone(dashboard.data.audit_status)} dot>
          {dashboard.data.audit_status}
        </Badge>
      </div>

      {options.data && (
        <DashboardFilters
          dimensions={options.data.dimensions}
          state={filters}
          onChange={setFilters}
          busy={busy}
        />
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-12">
        {widgets.map((widget) => (
          <div key={widget.id} className={cn("min-w-0", SPAN[widget.width] ?? "xl:col-span-3")}>
            <WidgetView
              widget={withFilters(widget)}
              dim={busy}
              onDrill={() => {
                const slug = slugFor(widget);
                const kpi = slug ? kpiBySlug.get(slug) : null;
                if (kpi) setDrill(kpi);
              }}
            />
          </div>
        ))}
      </div>

      {drill && (
        <DrillPanel
          projectId={id}
          kpi={drill}
          filters={active}
          onClose={() => setDrill(null)}
          dimensions={(options.data?.dimensions ?? []).filter((item) => item.type !== "datetime")}
        />
      )}
    </div>
  );
}

function DrillPanel({
  projectId,
  kpi,
  filters,
  dimensions,
  onClose,
}: {
  projectId: string;
  kpi: { slug: string; name: string };
  filters: ReturnType<typeof buildFilters>;
  dimensions: { name: string; label: string }[];
  onClose: () => void;
}) {
  const [dimension, setDimension] = useState(dimensions[0]?.name ?? null);
  const query = useQuery({
    queryKey: ["drill", projectId, kpi.slug, dimension, filters],
    queryFn: () => api.queryKpi(projectId, { kpi_slug: kpi.slug, dimension, filters, limit: 15 }),
    enabled: Boolean(dimension),
    placeholderData: keepPreviousData,
    retry: false,
  });

  const rows = query.data?.rows ?? [];
  const nonAdditive = query.data?.additivity !== "additive";

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[0.9375rem] font-semibold tracking-tight text-ink">
            {kpi.name} — breakdown
          </p>
          {nonAdditive && (
            <p className="mt-1 text-xs text-warn">
              This metric is {query.data?.additivity?.replace("_", "-")}: each segment value is
              computed correctly, but they do not sum to the total.
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <select
            value={dimension ?? ""}
            onChange={(event) => setDimension(event.target.value)}
            className="rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink-soft focus:border-brand"
          >
            {dimensions.map((item) => (
              <option key={item.name} value={item.name}>
                by {item.label}
              </option>
            ))}
          </select>
          <Button variant="ghost" size="icon" onClick={onClose} title="Close">
            <X aria-hidden />
          </Button>
        </div>
      </div>

      {query.isError ? (
        <p className="text-[0.8125rem] text-bad">{(query.error as Error).message}</p>
      ) : rows.length === 0 ? (
        <p className="text-[0.8125rem] text-ink-muted">No rows for this slice.</p>
      ) : rows.length <= 2 ? (
        // One or two segments is not a chart. The current filter has already
        // narrowed the data to a single group, so the number is the answer.
        <div className="flex flex-wrap gap-8">
          {rows.map((row) => (
            <div key={String(row.dimension)}>
              <p className="text-[0.8125rem] font-medium text-ink-muted">
                {String(row.dimension ?? kpi.name)}
              </p>
              <p className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">
                {formatValue(row.value, {}, { unit: query.data?.unit })}
              </p>
            </div>
          ))}
          <p className="basis-full text-xs text-ink-faint">
            Only {rows.length} segment{rows.length > 1 ? "s" : ""} match the active filters — clear
            them to compare across all of{" "}
            {dimensions.find((item) => item.name === dimension)?.label}.
          </p>
        </div>
      ) : (
        <div
          className={cn("transition-opacity duration-200", query.isFetching && "opacity-40")}
        >
          <div style={{ height: Math.max(200, rows.length * 28 + 44) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={rows}
                layout="vertical"
                margin={{ top: 4, right: 16, bottom: 4, left: 0 }}
                barCategoryGap={2}
              >
                <CartesianGrid stroke={CHROME.grid} strokeWidth={1} horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value: number) =>
                    formatValue(value, {}, { unit: query.data?.unit, compact: true })
                  }
                />
                <YAxis
                  type="category"
                  dataKey="dimension"
                  tick={{ fill: CHROME.tick, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={118}
                  interval={0}
                />
                <Tooltip
                  cursor={{ fill: "#12142a0a" }}
                  contentStyle={{
                    background: CHROME.surface,
                    border: `1px solid ${CHROME.border}`,
                    borderRadius: 8,
                    fontSize: 12,
                    boxShadow: "0 16px 40px -16px rgb(18 20 42 / 0.2)",
                  }}
                  formatter={(value) => [
                    formatValue(typeof value === "number" ? value : null, {}, {
                      unit: query.data?.unit,
                    }),
                    kpi.name,
                  ]}
                />
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

          {/* The SQL that produced these numbers, so a reader can verify them. */}
          <details className="mt-4 group">
            <summary className="cursor-pointer text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase transition-colors hover:text-ink-muted">
              SQL executed
            </summary>
            <pre className="mt-2 overflow-auto rounded-lg border border-line bg-surface-sunken p-3 font-mono text-[0.6875rem] leading-relaxed text-ink-soft">
              {query.data?.sql}
            </pre>
          </details>
        </div>
      )}
    </Card>
  );
}

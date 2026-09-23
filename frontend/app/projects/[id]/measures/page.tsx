"use client";

import { useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, ShieldCheck } from "lucide-react";

import {
  Badge,
  EmptyState,
  Panel,
  PanelHeader,
  Segment,
  SegmentGroup,
  Skeleton,
  statusTone,
} from "@/components/ui/primitives";
import { Sparkline } from "@/components/ui/charts";
import { KpiInspector } from "@/components/kpi-inspector";
import { api, type KPI } from "@/lib/api";
import { deltaOf, formatValue } from "@/lib/viz";
import { cn } from "@/lib/utils";

/**
 * KPI catalog.
 *
 * Each card carries its value, movement and the formula it was built from;
 * opening one reveals the full chain down to compiled SQL. Every KPI here was
 * instantiated from a template whose required business roles were actually
 * bound — a dataset without those columns simply yields fewer KPIs.
 */
export default function MeasuresPage() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("kpi"));
  const [filter, setFilter] = useState<"all" | "computed" | "failed">("all");

  const kpis = useQuery({
    queryKey: ["kpis", id],
    queryFn: () => api.kpis(id),
    retry: false,
  });

  if (kpis.isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-44" />
        ))}
      </div>
    );
  }

  if (kpis.isError || !kpis.data?.length) {
    return (
      <EmptyState
        title="No KPI catalog yet"
        message="Run the pipeline. The KPI engine binds business roles to columns, then builds only the metrics those roles can support — and compiles each one to SQL before executing it."
        icon={<BarChart3 className="size-5" />}
      />
    );
  }

  const all = kpis.data;
  const computed = all.filter((kpi) => kpi.validation_status === "computed");
  const failed = all.filter((kpi) => kpi.validation_status !== "computed");
  const shown = filter === "computed" ? computed : filter === "failed" ? failed : all;

  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader
          title="KPI catalog"
          subtitle={`${computed.length} of ${all.length} computed deterministically from the cleaned layer`}
          icon={<BarChart3 className="size-4" />}
          action={
            <SegmentGroup>
              <Segment active={filter === "all"} onClick={() => setFilter("all")}>
                All {all.length}
              </Segment>
              <Segment active={filter === "computed"} onClick={() => setFilter("computed")}>
                Computed {computed.length}
              </Segment>
              {failed.length > 0 && (
                <Segment active={filter === "failed"} onClick={() => setFilter("failed")}>
                  Failed {failed.length}
                </Segment>
              )}
            </SegmentGroup>
          }
        />

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((kpi) => (
            <KpiCard key={kpi.id} projectId={id} kpi={kpi} onOpen={() => setSelected(kpi.id)} />
          ))}
        </div>
      </Panel>

      {selected && (
        <KpiInspector projectId={id} kpiId={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function KpiCard({
  projectId,
  kpi,
  onOpen,
}: {
  projectId: string;
  kpi: KPI;
  onOpen: () => void;
}) {
  const delta = deltaOf(kpi.change_pct, true);
  const computed = kpi.validation_status === "computed";

  // The series is only needed for the sparkline, so it is fetched lazily per
  // card rather than inflating the catalog response.
  const detail = useQuery({
    queryKey: ["kpi", projectId, kpi.id],
    queryFn: () =>
      api.kpi(projectId, kpi.id) as Promise<{
        result: { time_series: { value: number | null }[] };
      }>,
    enabled: computed,
    retry: false,
    staleTime: 60_000,
  });
  const series = detail.data?.result.time_series?.map((point) => point.value) ?? [];

  return (
    <button
      onClick={onOpen}
      className={cn(
        "group/kpi flex flex-col rounded-card border border-line bg-raised p-4 text-left",
        "transition-[box-shadow,border-color,transform] duration-[--duration-fast] ease-[--ease-out-soft]",
        "hover:-translate-y-px hover:border-line-strong hover:shadow-lift",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 truncate text-[0.8125rem] font-medium text-ink">{kpi.name}</p>
        {computed ? (
          <ShieldCheck className="size-3.5 shrink-0 text-good" aria-hidden />
        ) : (
          <Badge tone={statusTone(kpi.validation_status)}>
            {kpi.validation_status.replace(/_/g, " ")}
          </Badge>
        )}
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[1.5rem] leading-none font-semibold tracking-tight text-ink">
            {formatValue(kpi.value, {}, { unit: kpi.unit, compact: true })}
          </p>
          {delta ? (
            <p className="mt-2 text-[0.6875rem]">
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
                {delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "—"}{" "}
                {delta.value}
              </span>
              <span className="ml-1 text-ink-faint">vs previous</span>
            </p>
          ) : (
            <p className="mt-2 text-[0.6875rem] text-ink-faint">no prior period</p>
          )}
        </div>
        {series.length > 1 && (
          <span className="shrink-0 text-brand opacity-70 transition-opacity group-hover/kpi:opacity-100">
            <Sparkline values={series} />
          </span>
        )}
      </div>

      <p className="mt-3 line-clamp-2 border-t border-line pt-2.5 font-mono text-[0.625rem] leading-relaxed text-ink-faint">
        {kpi.formula}
      </p>
    </button>
  );
}

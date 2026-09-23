"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { X } from "lucide-react";

import {
  Badge,
  Code,
  Eyebrow,
  Field,
  Panel,
  Skeleton,
  statusTone,
} from "@/components/ui/primitives";
import { api, type KPI } from "@/lib/api";
import { CHROME, SERIES, formatValue, shortPeriod } from "@/lib/viz";
import { cn } from "@/lib/utils";

/**
 * KPI inspector.
 *
 * The answer to "where did this number come from" — definition, formula,
 * compiled SQL, source tables, the agent that produced it and the audit
 * verdict, all from `/kpis/{id}`. This is the product's core claim made
 * inspectable, so nothing here is summarised away.
 */

type Detail = {
  kpi: KPI & { data_sources: string[]; dimensions: string[]; filters: Record<string, unknown> };
  result: {
    value: number | null;
    previous_value: number | null;
    change_pct: number | null;
    query_sql: string | null;
    breakdown: { dimension: string; value: number | null }[];
    time_series: { period: string; value: number | null; partial?: boolean }[];
    status: string;
  };
  lineage: { tables: string[]; formula: string; sql: string | null; run_id: string };
  explanation: Record<string, string> | null;
};

export function KpiInspector({
  projectId,
  kpiId,
  onClose,
}: {
  projectId: string;
  kpiId: string;
  onClose: () => void;
}) {
  const detail = useQuery({
    queryKey: ["kpi", projectId, kpiId],
    queryFn: () => api.kpi(projectId, kpiId) as Promise<Detail>,
    retry: false,
  });

  const data = detail.data;
  const series = (data?.result.time_series ?? []).filter((point) => point.value !== null);
  const provenance = (data?.kpi.filters ?? {}) as {
    revenue_basis?: string;
    filters?: string[];
    roles?: Record<string, string>;
    additivity?: string;
    template?: string;
  };

  return (
    <div className="fixed inset-0 z-50">
      <button
        className="bf-fade absolute inset-0 bg-shell/40 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Close KPI inspector"
      />
      <aside
        role="dialog"
        aria-modal
        aria-label="KPI detail"
        className="bf-slide-left absolute inset-y-0 right-0 flex w-full max-w-[34rem] flex-col border-l border-line bg-surface shadow-float"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold tracking-tight text-ink">
              {data?.kpi.name ?? "KPI"}
            </h2>
            {data && (
              <p className="mt-0.5 text-[0.75rem] text-ink-muted">{data.kpi.description}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="grid size-8 shrink-0 place-items-center rounded-lg text-ink-faint transition-colors hover:bg-sunken hover:text-ink"
            aria-label="Close"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto p-5">
          {detail.isLoading && (
            <>
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-40 w-full" />
              <Skeleton className="h-32 w-full" />
            </>
          )}

          {data && (
            <>
              {/* Headline value */}
              <section>
                <div className="flex flex-wrap items-end gap-4">
                  <p className="text-[2.25rem] leading-none font-semibold tracking-tight text-ink">
                    {formatValue(data.result.value, {}, { unit: data.kpi.unit })}
                  </p>
                  {data.result.change_pct != null && (
                    <span
                      className={cn(
                        "pb-1 text-[0.8125rem] font-medium",
                        data.result.change_pct >= 0 ? "text-good" : "text-bad",
                      )}
                    >
                      {data.result.change_pct >= 0 ? "▲" : "▼"}{" "}
                      {Math.abs(data.result.change_pct * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <Badge tone={statusTone(data.kpi.validation_status)}>
                    {data.kpi.validation_status.replace(/_/g, " ")}
                  </Badge>
                  {data.kpi.unit && <Badge tone="neutral">{data.kpi.unit}</Badge>}
                  {provenance.additivity && (
                    <Badge tone={provenance.additivity === "additive" ? "neutral" : "warn"}>
                      {provenance.additivity.replace(/_/g, "-")}
                    </Badge>
                  )}
                  <span className="text-[0.6875rem] text-ink-faint">
                    confidence {(data.kpi.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </section>

              {/* Trend */}
              {series.length > 1 && (
                <section>
                  <Eyebrow>Historical values</Eyebrow>
                  <div className="mt-2 h-36">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={series} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                        <XAxis
                          dataKey="period"
                          tickFormatter={shortPeriod}
                          tick={{ fill: CHROME.tick, fontSize: 10 }}
                          axisLine={{ stroke: CHROME.axis }}
                          tickLine={false}
                          minTickGap={30}
                        />
                        <YAxis
                          tick={{ fill: CHROME.tick, fontSize: 10 }}
                          axisLine={false}
                          tickLine={false}
                          width={48}
                          tickFormatter={(value: number) =>
                            formatValue(value, {}, { unit: data.kpi.unit, compact: true })
                          }
                        />
                        <RechartsTooltip
                          cursor={{ stroke: CHROME.axis }}
                          contentStyle={{
                            background: "var(--color-raised)",
                            border: "1px solid var(--color-line)",
                            borderRadius: 8,
                            fontSize: 12,
                          }}
                          labelFormatter={(label) => shortPeriod(String(label))}
                          formatter={(value) => [
                            formatValue(typeof value === "number" ? value : null, {}, {
                              unit: data.kpi.unit,
                            }),
                            data.kpi.name,
                          ]}
                        />
                        <Line
                          type="monotone"
                          dataKey="value"
                          stroke={SERIES[0]}
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              )}

              {/* Definition */}
              <section className="space-y-3">
                <Eyebrow>Definition</Eyebrow>
                <p className="text-[0.8125rem] leading-relaxed text-ink-soft">
                  {data.kpi.business_meaning}
                </p>
                <div>
                  <p className="mb-1.5 text-[0.625rem] tracking-[0.1em] text-ink-faint uppercase">
                    Formula
                  </p>
                  <Code>{data.lineage.formula}</Code>
                </div>
                <div>
                  <p className="mb-1.5 text-[0.625rem] tracking-[0.1em] text-ink-faint uppercase">
                    Compiled SQL
                  </p>
                  <Code>{data.result.query_sql ?? "—"}</Code>
                </div>
              </section>

              {/* Provenance */}
              <section>
                <Eyebrow>Provenance</Eyebrow>
                <dl className="mt-2 grid gap-3 sm:grid-cols-2">
                  <Field label="Source tables">
                    {data.lineage.tables.length ? data.lineage.tables.join(", ") : "—"}
                  </Field>
                  {provenance.revenue_basis && (
                    <Field label="Revenue basis">{provenance.revenue_basis}</Field>
                  )}
                  {provenance.filters?.length && (
                    <Field label="Row filter">{provenance.filters.join("; ")}</Field>
                  )}
                  {provenance.roles && Object.keys(provenance.roles).length > 0 && (
                    <Field label="Business roles">
                      {Object.entries(provenance.roles)
                        .map(([role, column]) => `${role} = ${column}`)
                        .join(", ")}
                    </Field>
                  )}
                  {data.explanation && (
                    <Field label="Agents">
                      {data.explanation.producer_agent} → {data.explanation.validator_agent}
                    </Field>
                  )}
                </dl>
              </section>

              {/* XAI */}
              {data.explanation && (
                <section>
                  <Eyebrow>Audit record</Eyebrow>
                  <dl className="mt-2 space-y-3">
                    <Field label="What happened">{data.explanation.what_happened}</Field>
                    <Field label="Assumptions">{data.explanation.assumptions}</Field>
                    <Field label="Quality limitations">
                      {data.explanation.quality_limitations}
                    </Field>
                  </dl>
                </section>
              )}

              {/* Breakdown */}
              {data.result.breakdown?.length > 0 && (
                <section>
                  <Eyebrow>Top segments</Eyebrow>
                  <ul className="mt-2 space-y-1.5">
                    {data.result.breakdown.slice(0, 6).map((row) => (
                      <li
                        key={row.dimension}
                        className="flex items-center justify-between gap-3 text-[0.75rem]"
                      >
                        <span className="truncate text-ink-soft">{row.dimension}</span>
                        <span className="tnum shrink-0 font-medium text-ink">
                          {formatValue(row.value, {}, { unit: data.kpi.unit, compact: true })}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}

          {detail.isError && (
            <p className="text-[0.8125rem] text-bad">{(detail.error as Error).message}</p>
          )}
        </div>
      </aside>
    </div>
  );
}

export { Panel };

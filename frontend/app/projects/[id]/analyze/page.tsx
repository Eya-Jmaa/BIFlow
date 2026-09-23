"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Lightbulb,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import {
  Badge,
  Code,
  EmptyState,
  Eyebrow,
  Field,
  Panel,
  PanelHeader,
  Segment,
  SegmentGroup,
  Skeleton,
  statusTone,
} from "@/components/ui/primitives";
import { api, type Insight } from "@/lib/api";
import { formatValue } from "@/lib/viz";
import { cn } from "@/lib/utils";

/**
 * Analyst workspace.
 *
 * Left: what the analyst agent concluded. Right: the evidence behind whatever
 * is selected. Every claim carries a "Why?" that opens the computed values and
 * the SQL it was derived from — an insight that cannot be traced is not
 * published, so there is always something to show.
 */

const CATEGORIES = [
  { key: "risk", title: "Risks", icon: ShieldAlert, tone: "bg-bad-soft text-bad" },
  { key: "anomaly", title: "Anomalies", icon: AlertTriangle, tone: "bg-warn-soft text-warn" },
  { key: "opportunity", title: "Opportunities", icon: Lightbulb, tone: "bg-good-soft text-good" },
  { key: "trend", title: "Trends", icon: TrendingUp, tone: "bg-brand-soft text-brand" },
  { key: "finding", title: "Findings", icon: Search, tone: "bg-inset text-ink-soft" },
  {
    key: "quality_caveat",
    title: "Caveats",
    icon: AlertTriangle,
    tone: "bg-warn-soft text-warn",
  },
] as const;

export default function AnalyzePage() {
  const { id } = useParams<{ id: string }>();
  const [filter, setFilter] = useState<string>("all");
  const [selected, setSelected] = useState<string | null>(null);

  const insights = useQuery({
    queryKey: ["insights", id],
    queryFn: () => api.insights(id),
    retry: false,
  });
  const analysis = useQuery({
    queryKey: ["analysis", id],
    queryFn: () =>
      api.analysis(id) as Promise<
        { id: string; analysis_type: string; metric: string; details: Record<string, unknown> }[]
      >,
    retry: false,
  });

  const items = useMemo(() => insights.data ?? [], [insights.data]);
  const active = items.find((item) => item.id === selected) ?? items[0] ?? null;

  if (insights.isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Skeleton className="h-[30rem]" />
        <Skeleton className="h-[30rem]" />
      </div>
    );
  }

  if (insights.isError || items.length === 0) {
    return (
      <EmptyState
        title="No findings yet"
        message="Run the pipeline. The analyst agent runs trend, anomaly, seasonality, Pareto and correlation tests over the computed KPI series, then ranks what is worth reporting."
        icon={<Sparkles className="size-5" />}
      />
    );
  }

  const counts = Object.fromEntries(
    CATEGORIES.map((category) => [
      category.key,
      items.filter((item) => item.category === category.key).length,
    ]),
  );
  const shown = filter === "all" ? items : items.filter((item) => item.category === filter);
  const grounded = items.filter((item) => item.grounded).length;
  const actionable = items.filter((item) => item.recommendation).length;

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1.15fr_0.85fr]">
      {/* Findings */}
      <div className="min-w-0 space-y-3">
        <Panel>
          <PanelHeader
            title="AI findings"
            subtitle={`${items.length} reported · ${grounded} grounded in computed values · ${actionable} with a recommendation`}
            icon={<Sparkles className="size-4" />}
          />
          <div className="flex flex-wrap gap-1">
            <SegmentGroup className="flex-wrap">
              <Segment active={filter === "all"} onClick={() => setFilter("all")}>
                All {items.length}
              </Segment>
              {CATEGORIES.filter((category) => counts[category.key] > 0).map((category) => (
                <Segment
                  key={category.key}
                  active={filter === category.key}
                  onClick={() => setFilter(category.key)}
                >
                  {category.title} {counts[category.key]}
                </Segment>
              ))}
            </SegmentGroup>
          </div>
        </Panel>

        <ul className="space-y-2.5">
          {shown.map((item) => {
            const category =
              CATEGORIES.find((entry) => entry.key === item.category) ?? CATEGORIES[4];
            const Icon = category.icon;
            const isActive = active?.id === item.id;
            return (
              <li key={item.id}>
                <button
                  onClick={() => setSelected(item.id)}
                  className={cn(
                    "w-full rounded-card border bg-raised p-4 text-left",
                    "transition-[box-shadow,border-color,transform] duration-[--duration-fast] ease-[--ease-out-soft]",
                    "hover:-translate-y-px hover:shadow-lift",
                    isActive ? "border-brand ring-2 ring-brand/15" : "border-line",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "grid size-8 shrink-0 place-items-center rounded-lg",
                        category.tone,
                      )}
                    >
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-[0.875rem] font-medium text-ink">{item.title}</p>
                        <Badge tone={statusTone(item.severity)}>{item.severity}</Badge>
                      </div>
                      <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-muted">
                        {item.description}
                      </p>
                      {item.recommendation && (
                        <p className="mt-2.5 flex gap-2 rounded-lg bg-brand-soft/60 px-2.5 py-2 text-[0.75rem] leading-relaxed text-ink-soft">
                          <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden />
                          <span className="line-clamp-2">{item.recommendation}</span>
                        </p>
                      )}
                      <div className="mt-2.5 flex items-center gap-3 text-[0.6875rem] text-ink-faint">
                        {item.metric && <span className="truncate">{item.metric}</span>}
                        <span className="tnum">
                          confidence {(item.confidence * 100).toFixed(0)}%
                        </span>
                        <span className="ml-auto font-medium text-brand">
                          {isActive ? "Showing evidence" : "Why?"}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Evidence */}
      <div className="lg:sticky lg:top-24">
        <Panel>
          <PanelHeader
            title="Evidence"
            subtitle={active ? active.title : "Select a finding"}
          />
          {!active ? (
            <p className="text-[0.8125rem] text-ink-muted">
              Every finding carries the values it was derived from.
            </p>
          ) : (
            <div className="space-y-5">
              <dl className="grid grid-cols-2 gap-3">
                <Field label="Metric">{active.metric ?? "—"}</Field>
                <Field label="Value">{formatValue(active.value, {}, {})}</Field>
                <Field label="Comparison">{active.comparison ?? "—"}</Field>
                <Field label="Period">{active.period ?? "—"}</Field>
              </dl>

              {active.recommendation && (
                <div className="rounded-card border border-brand-line bg-brand-soft/50 p-3.5">
                  <div className="flex items-center gap-2">
                    <Lightbulb className="size-3.5 text-brand" aria-hidden />
                    <Eyebrow>Recommendation</Eyebrow>
                  </div>
                  <p className="mt-2 text-[0.8125rem] leading-relaxed text-ink-soft">
                    {active.recommendation}
                  </p>
                  {active.recommendation_basis && (
                    <p className="mt-2 border-t border-brand-line/60 pt-2 text-[0.625rem] text-ink-faint">
                      {/* The advice is auditable too: this names the rule that fired. */}
                      Rule: {active.recommendation_basis}
                    </p>
                  )}
                </div>
              )}

              <div>
                <Eyebrow>Grounding</Eyebrow>
                <p className="mt-1.5 flex items-center gap-2 text-[0.8125rem] text-ink-soft">
                  <Badge tone={active.grounded ? "good" : "bad"} dot>
                    {active.grounded ? "grounded" : "rejected"}
                  </Badge>
                  <span className="text-ink-muted">
                    {active.grounded
                      ? "metric and value match a computed result"
                      : "no matching computed value"}
                  </span>
                </p>
              </div>

              {active.evidence && Object.keys(active.evidence).length > 0 && (
                <div>
                  <Eyebrow>Computed evidence</Eyebrow>
                  <Code className="mt-1.5 max-h-56">
                    {JSON.stringify(active.evidence, null, 2)}
                  </Code>
                </div>
              )}

              {active.query_sql && (
                <div>
                  <Eyebrow>Source query</Eyebrow>
                  <Code className="mt-1.5 max-h-48">{active.query_sql}</Code>
                </div>
              )}
            </div>
          )}
        </Panel>

        {/* Statistical tests actually run */}
        {analysis.data && analysis.data.length > 0 && (
          <Panel className="mt-3">
            <PanelHeader
              title="Statistical tests"
              subtitle={`${analysis.data.length} analyses recorded`}
            />
            <ul className="space-y-1.5">
              {Object.entries(
                analysis.data.reduce<Record<string, number>>((counts, row) => {
                  counts[row.analysis_type] = (counts[row.analysis_type] ?? 0) + 1;
                  return counts;
                }, {}),
              ).map(([type, count]) => (
                <li
                  key={type}
                  className="flex items-center justify-between text-[0.75rem] text-ink-soft"
                >
                  <span className="capitalize">{type.replace(/_/g, " ")}</span>
                  <span className="tnum text-ink-faint">{count}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

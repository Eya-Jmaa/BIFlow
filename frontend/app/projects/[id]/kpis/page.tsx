"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { BarChart3 } from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Code, EmptyState, Field, Skeleton } from "@/components/ui/data";
import { api, type KPI } from "@/lib/api";
import { deltaOf, formatValue } from "@/lib/viz";
import { cn } from "@/lib/utils";

type Detail = {
  result: { value: number | null; query_sql: string | null; status: string };
  lineage: { tables: string[]; formula: string; sql: string | null };
  explanation: Record<string, string> | null;
};

export default function KpiPage() {
  const { id } = useParams<{ id: string }>();
  const kpis = useQuery({ queryKey: ["kpis", id], queryFn: () => api.kpis(id), retry: false });
  const [selected, setSelected] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: ["kpi", id, selected],
    queryFn: () => api.kpi(id, selected!) as Promise<Detail>,
    enabled: Boolean(selected),
  });

  if (kpis.isError) {
    return (
      <EmptyState
        title="No KPI catalog yet"
        message="Run the pipeline. The semantic agent binds business roles to columns, then instantiates only the KPIs those roles can support."
        icon={<BarChart3 className="size-5" />}
      />
    );
  }

  const list = kpis.data ?? [];
  const active = list.find((kpi) => kpi.id === selected) ?? null;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="min-w-0 space-y-2.5">
        {kpis.isLoading &&
          [0, 1, 2, 3].map((index) => <Skeleton key={index} className="h-28 w-full" />)}

        {list.map((kpi: KPI) => {
          const delta = deltaOf(kpi.change_pct, true);
          const isActive = kpi.id === selected;
          return (
            <button
              key={kpi.id}
              className="block w-full text-left"
              onClick={() => setSelected(kpi.id)}
            >
              <Card
                interactive
                className={cn(isActive && "ring-2 ring-brand/30 ring-offset-1 ring-offset-canvas")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{kpi.name}</p>
                    <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-ink-muted">
                      {kpi.business_meaning}
                    </p>
                  </div>
                  <Badge tone={statusTone(kpi.validation_status)}>
                    {kpi.validation_status.replace(/_/g, " ")}
                  </Badge>
                </div>

                <div className="mt-3 flex items-baseline gap-3">
                  <p className="text-2xl font-semibold tracking-tight text-ink">
                    {formatValue(kpi.value, {}, { unit: kpi.unit, compact: true })}
                  </p>
                  {delta && (
                    <span
                      className={cn(
                        "text-xs font-medium",
                        delta.favourable === null
                          ? "text-ink-muted"
                          : delta.favourable
                            ? "text-good"
                            : "text-bad",
                      )}
                    >
                      {delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "—"}{" "}
                      {delta.value} {delta.direction}
                    </span>
                  )}
                </div>

                <p className="mt-2.5 truncate font-mono text-[0.625rem] text-ink-faint">
                  {kpi.formula}
                </p>
              </Card>
            </button>
          );
        })}
      </div>

      <Card className="min-w-0 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-auto">
        <CardHeader
          title={active ? active.name : "KPI explanation"}
          subtitle={active ? active.description : "Select a KPI to inspect its formula, SQL and XAI record."}
        />

        {!selected && (
          <EmptyState
            title="Nothing selected"
            message="Every KPI carries the formula it was built from, the SQL it compiled to, and the reasoning behind each business role it used."
            icon={<BarChart3 className="size-5" />}
          />
        )}

        {detail.isLoading && selected && <Skeleton className="h-64 w-full" />}

        {detail.data && active && (
          <div className="space-y-5">
            <div>
              <p className="text-[2rem] leading-none font-semibold tracking-tight text-ink">
                {formatValue(detail.data.result.value, {}, { unit: active.unit })}
              </p>
              <p className="mt-1.5 text-xs text-ink-faint">
                {active.unit ?? "value"} · confidence {(active.confidence * 100).toFixed(0)}%
              </p>
            </div>

            <div>
              <p className="mb-1.5 text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase">
                Formula
              </p>
              <Code>{detail.data.lineage.formula}</Code>
            </div>

            <div>
              <p className="mb-1.5 text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase">
                Compiled SQL
              </p>
              <Code>{detail.data.result.query_sql ?? "—"}</Code>
            </div>

            {detail.data.explanation && (
              <dl className="grid gap-4">
                <Field label="What happened">{detail.data.explanation.what_happened}</Field>
                <Field label="How it was calculated">
                  {detail.data.explanation.how_calculated}
                </Field>
                <Field label="Data used">{detail.data.explanation.data_used}</Field>
                <Field label="Assumptions">{detail.data.explanation.assumptions}</Field>
                <Field label="Quality limitations">
                  {detail.data.explanation.quality_limitations}
                </Field>
                <Field label="Agents">
                  {detail.data.explanation.producer_agent} → {detail.data.explanation.validator_agent}
                </Field>
              </dl>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

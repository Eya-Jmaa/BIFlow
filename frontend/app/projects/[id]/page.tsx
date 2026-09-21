"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Database,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState, Field, StatTile } from "@/components/ui/data";
import { api } from "@/lib/api";
import { formatValue } from "@/lib/viz";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const datasets = useQuery({ queryKey: ["datasets", id], queryFn: () => api.datasets(id) });
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id) });
  const kpis = useQuery({ queryKey: ["kpis", id], queryFn: () => api.kpis(id), retry: false });
  const insights = useQuery({
    queryKey: ["insights", id],
    queryFn: () => api.insights(id),
    retry: false,
  });

  const latest = runs.data?.[0];
  const headline = (kpis.data ?? []).filter((kpi) => kpi.validation_status === "computed");
  const risks = (insights.data ?? []).filter(
    (insight) => insight.severity === "warning" || insight.category === "risk",
  );

  if (!latest && datasets.data?.length === 0) {
    return (
      <EmptyState
        title="Start by uploading a dataset"
        message="BIFlow reads CSV, Parquet and Excel. Nothing is modified — the original file is kept in the RAW layer."
        icon={<Database className="size-5" />}
        action={
          <Link href={`/projects/${id}/datasets`}>
            <Button>
              Upload data <ArrowRight aria-hidden />
            </Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Datasets"
          value={datasets.data?.length ?? 0}
          hint="in the RAW layer"
          icon={<Database className="size-4" />}
          tone="brand"
        />
        <StatTile
          label="Pipeline runs"
          value={runs.data?.length ?? 0}
          hint={latest ? `last: ${latest.status}` : "not run yet"}
          icon={<Workflow className="size-4" />}
          tone="accent"
        />
        <StatTile
          label="Computed KPIs"
          value={headline.length}
          hint={
            kpis.data && kpis.data.length > headline.length
              ? `${kpis.data.length - headline.length} did not compute`
              : "all formulas valid"
          }
          icon={<BarChart3 className="size-4" />}
          tone="good"
        />
        <StatTile
          label="Insights"
          value={insights.data?.length ?? 0}
          hint={risks.length ? `${risks.length} need attention` : "none flagged"}
          icon={<Sparkles className="size-4" />}
          tone={risks.length ? "warn" : "brand"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader
            title="KPI snapshot"
            subtitle={
              headline.length
                ? "Computed deterministically from the cleaned layer"
                : "Run the pipeline to populate the catalog"
            }
            action={
              headline.length > 0 && (
                <Link href={`/projects/${id}/kpis`}>
                  <Button variant="secondary" size="sm">
                    All KPIs
                  </Button>
                </Link>
              )
            }
          />
          {headline.length === 0 ? (
            <p className="text-[0.8125rem] text-ink-muted">No KPIs computed yet.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {headline.slice(0, 6).map((kpi) => (
                <div
                  key={kpi.id}
                  className="rounded-xl border border-line bg-surface-muted/60 p-3.5"
                >
                  <p className="truncate text-[0.8125rem] font-medium text-ink-muted">{kpi.name}</p>
                  <p className="mt-1.5 text-xl font-semibold tracking-tight text-ink">
                    {formatValue(kpi.value, {}, { unit: kpi.unit, compact: true })}
                  </p>
                  <p className="mt-2 truncate font-mono text-[0.625rem] text-ink-faint">
                    {kpi.formula}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Latest run"
              action={latest && <Badge tone={statusTone(latest.status)} dot>{latest.status}</Badge>}
            />
            {!latest ? (
              <p className="text-[0.8125rem] text-ink-muted">
                No pipeline has been executed yet.
              </p>
            ) : (
              <>
                <dl className="grid gap-3 sm:grid-cols-2">
                  <Field label="Current step">{latest.current_step || "—"}</Field>
                  <Field label="Engine">
                    {latest.llm_model || "deterministic only"}
                  </Field>
                  <Field label="Started">
                    {latest.started_at
                      ? new Date(latest.started_at).toLocaleString("en-GB")
                      : "—"}
                  </Field>
                  <Field label="Run ID">
                    <span className="font-mono text-[0.6875rem]">{latest.id.slice(0, 8)}</span>
                  </Field>
                </dl>
                {latest.error && (
                  <p className="mt-3 rounded-lg bg-bad-soft px-3 py-2 text-[0.8125rem] text-bad">
                    {latest.error}
                  </p>
                )}
                <Link
                  href={`/projects/${id}/pipeline`}
                  className="mt-4 inline-flex items-center gap-1 text-[0.8125rem] font-medium text-brand hover:text-brand-strong"
                >
                  Open pipeline <ArrowRight className="size-3.5" aria-hidden />
                </Link>
              </>
            )}
          </Card>

          {risks.length > 0 && (
            <Card>
              <CardHeader
                title="Needs attention"
                subtitle={`${risks.length} flagged`}
                action={
                  <span className="grid size-8 place-items-center rounded-xl bg-warn-soft text-warn">
                    <AlertTriangle className="size-4" aria-hidden />
                  </span>
                }
              />
              <ul className="space-y-2.5">
                {risks.slice(0, 4).map((insight) => (
                  <li key={insight.id} className="text-[0.8125rem] leading-snug text-ink-soft">
                    {insight.title}
                  </li>
                ))}
              </ul>
              <Link
                href={`/projects/${id}/insights`}
                className="mt-4 inline-flex items-center gap-1 text-[0.8125rem] font-medium text-brand hover:text-brand-strong"
              >
                All insights <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </Card>
          )}

          {latest?.status === "completed" && risks.length === 0 && (
            <Card>
              <div className="flex items-start gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-good-soft text-good">
                  <ShieldCheck className="size-4" aria-hidden />
                </span>
                <div>
                  <p className="text-[0.9375rem] font-semibold text-ink">Run audited</p>
                  <p className="mt-0.5 text-[0.8125rem] text-ink-muted">
                    Every KPI traced to its formula and SQL, with no unresolved warnings.
                  </p>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

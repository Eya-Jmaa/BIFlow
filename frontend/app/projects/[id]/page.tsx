"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Database, ShieldCheck } from "lucide-react";

import { PipelineGraph } from "@/components/pipeline-graph";
import { KpiInspector } from "@/components/kpi-inspector";
import { Sparkline } from "@/components/ui/charts";
import {
  Badge,
  Button,
  EmptyState,
  Eyebrow,
  Field,
  Panel,
  PanelHeader,
  Skeleton,
  statusTone,
} from "@/components/ui/primitives";
import { api, type KPI } from "@/lib/api";
import { stageStatesFromRuns, relativeTime, runtimeMs, type AgentRun } from "@/lib/run-state";
import { deltaOf, formatValue } from "@/lib/viz";
import { cn } from "@/lib/utils";

/**
 * Project overview.
 *
 * The headline KPIs come first because that is what a business reader is here
 * for; the pipeline and its operational facts sit below. Every tile opens the
 * full inspector, which is the product's differentiator — a number you can
 * follow all the way down.
 */
export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const [inspect, setInspect] = useState<string | null>(null);

  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id), retry: false });
  const latest = runs.data?.[0];

  const agents = useQuery({
    queryKey: ["agents", id],
    queryFn: () => api.agentRuns(id) as Promise<AgentRun[]>,
    enabled: Boolean(latest),
    retry: false,
  });
  const kpis = useQuery({
    queryKey: ["kpis", id],
    queryFn: () => api.kpis(id),
    enabled: Boolean(latest),
    retry: false,
  });
  const insights = useQuery({
    queryKey: ["insights", id],
    queryFn: () => api.insights(id),
    enabled: Boolean(latest),
    retry: false,
  });
  const datasets = useQuery({
    queryKey: ["datasets", id],
    queryFn: () => api.datasets(id),
    retry: false,
  });

  const states = stageStatesFromRuns(agents.data);
  const computed = (kpis.data ?? []).filter((kpi) => kpi.validation_status === "computed");
  const attention = (insights.data ?? []).filter(
    (insight) => insight.severity === "warning" || insight.category === "risk",
  );

  if (!latest && datasets.data?.length === 0) {
    return (
      <EmptyState
        title="Start with a dataset"
        message="BIFlow reads CSV, Parquet and Excel. The original file is never modified — it is kept in the RAW layer and everything downstream is derived from it."
        icon={<Database className="size-5" />}
        action={
          <Link href={`/projects/${id}/datasets`}>
            <Button>
              Upload data
              <ArrowRight aria-hidden />
            </Button>
          </Link>
        }
      />
    );
  }

  if (!latest) {
    return (
      <EmptyState
        title="Ready to run"
        message="Your dataset is attached. Run the pipeline and seven agents will profile, clean, model, measure, analyse, visualise and audit it."
        icon={<ShieldCheck className="size-5" />}
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Headline metrics */}
      {kpis.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-32" />
          ))}
        </div>
      ) : computed.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {computed.slice(0, 4).map((kpi) => (
            <HeadlineKpi
              key={kpi.id}
              projectId={id}
              kpi={kpi}
              onOpen={() => setInspect(kpi.id)}
            />
          ))}
        </div>
      ) : null}

      {/* Pipeline */}
      <Panel>
        <PanelHeader
          title="Pipeline"
          subtitle="Hover a stage for what its agent produced on this run"
          action={
            <Link href={`/projects/${id}/pipeline`}>
              <Button variant="secondary" size="sm">
                Run history
              </Button>
            </Link>
          }
        />
        <PipelineGraph states={states} projectId={id} />
      </Panel>

      <div className="grid items-start gap-4 lg:grid-cols-[1fr_20rem]">
        {/* Attention */}
        <Panel>
          <PanelHeader
            title="Needs attention"
            subtitle={
              attention.length
                ? `${attention.length} findings ranked by severity and effect size`
                : "Nothing flagged on this run"
            }
            icon={<AlertTriangle className="size-4" />}
            action={
              <Link href={`/projects/${id}/analyze`}>
                <Button variant="secondary" size="sm">
                  All findings
                </Button>
              </Link>
            }
          />
          {attention.length === 0 ? (
            <p className="text-[0.8125rem] text-ink-muted">
              No risks or warnings were raised by the analyst agent.
            </p>
          ) : (
            <ul className="space-y-2.5">
              {attention.slice(0, 5).map((insight) => (
                <li key={insight.id} className="flex gap-2.5">
                  <span
                    className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warn"
                    aria-hidden
                  />
                  <span className="min-w-0">
                    <span className="block text-[0.8125rem] font-medium text-ink">
                      {insight.title}
                    </span>
                    <span className="mt-0.5 block line-clamp-2 text-[0.75rem] leading-relaxed text-ink-muted">
                      {insight.description}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Run facts — all real */}
        <Panel>
          <PanelHeader title="This run" />
          <dl className="space-y-3.5">
            <Field label="Status">
              <Badge tone={statusTone(latest.status)} dot>
                {latest.status}
              </Badge>
            </Field>
            <Field label="Runtime">
              {(() => {
                const total = runtimeMs(agents.data);
                return total ? `${(total / 1000).toFixed(1)} s across ${agents.data?.length ?? 0} agents` : "—";
              })()}
            </Field>
            <Field label="Engine">{latest.llm_model ?? "deterministic only"}</Field>
            <Field label="Completed">
              {relativeTime(latest.completed_at ?? latest.started_at) ?? "—"}
            </Field>
            {datasets.data?.[0]?.row_count != null && (
              <Field label="Rows processed">
                {datasets.data[0].row_count.toLocaleString("en-GB")}
              </Field>
            )}
            <Field label="KPIs computed">
              {computed.length} of {kpis.data?.length ?? 0}
            </Field>
            <Field label="Run ID">
              <span className="font-mono text-[0.6875rem]">{latest.id.slice(0, 8)}</span>
            </Field>
          </dl>
          {latest.error && (
            <p className="mt-4 rounded-lg bg-bad-soft px-3 py-2 text-[0.75rem] leading-snug text-bad">
              {latest.error}
            </p>
          )}
        </Panel>
      </div>

      {inspect && (
        <KpiInspector projectId={id} kpiId={inspect} onClose={() => setInspect(null)} />
      )}
    </div>
  );
}

function HeadlineKpi({
  projectId,
  kpi,
  onOpen,
}: {
  projectId: string;
  kpi: KPI;
  onOpen: () => void;
}) {
  const delta = deltaOf(kpi.change_pct, true);
  const detail = useQuery({
    queryKey: ["kpi", projectId, kpi.id],
    queryFn: () =>
      api.kpi(projectId, kpi.id) as Promise<{
        result: { time_series: { value: number | null }[] };
      }>,
    retry: false,
    staleTime: 60_000,
  });
  const series = detail.data?.result.time_series?.map((point) => point.value) ?? [];

  return (
    <button
      onClick={onOpen}
      className={cn(
        "group/tile rounded-card border border-line bg-surface p-5 text-left shadow-card",
        "transition-[box-shadow,border-color,transform] duration-[--duration-fast] ease-[--ease-out-soft]",
        "hover:-translate-y-px hover:border-line-strong hover:shadow-lift",
      )}
    >
      <p className="truncate text-[0.8125rem] font-medium text-ink-muted">{kpi.name}</p>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className="text-[1.625rem] leading-none font-semibold tracking-tight text-ink">
          {formatValue(kpi.value, {}, { unit: kpi.unit, compact: true })}
        </p>
        {series.length > 1 && (
          <span className="text-brand opacity-60 transition-opacity group-hover/tile:opacity-100">
            <Sparkline values={series} width={56} height={20} />
          </span>
        )}
      </div>
      {delta ? (
        <p className="mt-2.5 flex items-center gap-1.5 text-xs">
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
            {delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "—"} {delta.value}
          </span>
          <span className="text-ink-faint">vs previous period</span>
        </p>
      ) : (
        <p className="mt-2.5 text-xs text-ink-faint">no prior period</p>
      )}
    </button>
  );
}

"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Database } from "lucide-react";

import { Badge, Panel, StatusDot, statusTone } from "@/components/ui/primitives";
import { PipelineDots } from "@/components/pipeline-graph";
import { api, type Project } from "@/lib/api";
import { STAGES, stageStatuses, completedCount } from "@/lib/pipeline";
import { relativeTime } from "@/lib/run-state";
import { cn } from "@/lib/utils";

/**
 * A project card that says what state the project is actually in.
 *
 * Everything shown is fetched per-card from the project's own endpoints:
 * dataset size from `/datasets`, stage states from the latest run's
 * `/steps`, quality from `/quality`. A field with no backing data is omitted
 * rather than shown as zero.
 */
export function ProjectCard({ project }: { project: Project }) {
  const runs = useQuery({
    queryKey: ["runs", project.id],
    queryFn: () => api.runs(project.id),
    retry: false,
  });
  const latest = runs.data?.[0];

  const steps = useQuery({
    queryKey: ["steps", latest?.id],
    queryFn: () => api.steps(latest!.id),
    enabled: Boolean(latest),
    retry: false,
  });
  const datasets = useQuery({
    queryKey: ["datasets", project.id],
    queryFn: () => api.datasets(project.id),
    retry: false,
  });
  const quality = useQuery({
    queryKey: ["quality", project.id],
    queryFn: () => api.quality(project.id) as Promise<{ overall_score: number }[]>,
    enabled: Boolean(latest),
    retry: false,
  });

  const statuses = stageStatuses(steps.data);
  const done = completedCount(statuses);
  const dataset = datasets.data?.[0];
  const score = quality.data?.[0]?.overall_score;
  const updated = relativeTime(project.updated_at);
  const running = latest?.status === "running" || latest?.status === "queued";

  return (
    <Link href={`/projects/${project.id}`} className="block">
      <Panel interactive className="group/card">
        {/* Identity */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-[0.9375rem] font-semibold tracking-tight text-ink">
              {project.name}
            </h3>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.6875rem] text-ink-faint">
              <span className="font-medium text-ink-muted">{project.domain}</span>
              {updated && (
                <>
                  <span aria-hidden>·</span>
                  <span>Updated {updated}</span>
                </>
              )}
            </p>
          </div>
          <Badge tone={statusTone(running ? "running" : project.status)} dot pulse={running}>
            {running ? "running" : project.status.replace(/_/g, " ")}
          </Badge>
        </div>

        <p className="mt-3 line-clamp-2 text-[0.8125rem] leading-relaxed text-ink-muted">
          {project.business_objective}
        </p>

        {/* Dataset facts — only what exists */}
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[0.75rem]">
          {dataset ? (
            <span className="flex items-center gap-1.5 text-ink-soft">
              <Database className="size-3.5 text-ink-faint" aria-hidden />
              <span className="font-mono text-[0.6875rem]">{dataset.table_name}</span>
            </span>
          ) : (
            <span className="text-ink-faint">No dataset yet</span>
          )}
          {dataset?.row_count != null && (
            <span className="tnum text-ink-muted">
              {dataset.row_count.toLocaleString("en-GB")} rows
            </span>
          )}
          {dataset?.column_count != null && (
            <span className="tnum text-ink-muted">{dataset.column_count} columns</span>
          )}
        </div>

        {/* Pipeline — each segment links into its stage */}
        <div className="mt-4">
          <div className="mb-1.5 flex items-baseline justify-between">
            <span className="text-[0.625rem] tracking-[0.1em] text-ink-faint uppercase">
              Pipeline
            </span>
            <span className="tnum text-[0.625rem] text-ink-faint">
              {done}/{STAGES.length} stages
            </span>
          </div>
          <PipelineDots statuses={statuses} projectId={project.id} />
        </div>

        {/* Footer */}
        <div className="mt-4 flex items-center justify-between gap-3 border-t border-line pt-3">
          {score != null ? (
            <span className="flex items-center gap-1.5 text-[0.75rem]">
              <StatusDot tone={score >= 85 ? "good" : score >= 60 ? "warn" : "bad"} />
              <span className="text-ink-muted">Data quality</span>
              <span className="tnum font-semibold text-ink">{score.toFixed(1)}%</span>
            </span>
          ) : (
            <span className="text-[0.75rem] text-ink-faint">Quality not scored yet</span>
          )}
          <span className="flex items-center gap-1 text-[0.75rem] font-medium text-brand">
            Open
            <ArrowRight
              className={cn(
                "size-3.5 transition-transform duration-[--duration-fast] ease-[--ease-out-soft]",
                "group-hover/card:translate-x-0.5",
              )}
              aria-hidden
            />
          </span>
        </div>
      </Panel>
    </Link>
  );
}

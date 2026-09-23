"use client";

import { useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { STAGES, type Stage, type StageId, type StageStatus } from "@/lib/pipeline";
import { Badge, StatusDot } from "@/components/ui/primitives";

/**
 * The pipeline, as an interactive graph.
 *
 * Used as the marketing hero and as the in-app stepper — one component, so the
 * thing a visitor sees on the homepage is literally the thing they operate
 * later. Metrics shown on hover come from each agent's real `output_summary`;
 * when a stage has not run, it says so rather than showing a placeholder
 * number.
 */

export type StageMetric = { label: string; value: string };

export type StageState = {
  status: StageStatus;
  /** Milliseconds, from the backend's agent run. */
  latencyMs?: number | null;
  metrics?: StageMetric[];
};

const STATUS_LABEL: Record<StageStatus, string> = {
  completed: "Complete",
  running: "Running",
  failed: "Failed",
  pending: "Waiting",
};

const STATUS_TONE = {
  completed: "good",
  running: "brand",
  failed: "bad",
  pending: "neutral",
} as const;

function NodeMark({ stage, status }: { stage: Stage; status: StageStatus }) {
  return (
    <span
      className={cn(
        "relative grid size-9 shrink-0 place-items-center rounded-xl text-[0.6875rem] font-semibold tabular-nums",
        "transition-[background-color,color,box-shadow] duration-[--duration-base] ease-[--ease-out-soft]",
        status === "completed" && "bg-brand text-white shadow-sm",
        status === "running" && "bg-brand text-white shadow-sm ring-4 ring-brand/20",
        status === "failed" && "bg-bad-soft text-bad ring-1 ring-bad/30 ring-inset",
        status === "pending" && "bg-inset text-ink-faint ring-1 ring-line ring-inset",
      )}
    >
      {stage.index}
    </span>
  );
}

export function PipelineGraph({
  states,
  projectId,
  orientation = "horizontal",
  className,
  emptyHint,
}: {
  /** Real per-stage state. Omit a stage to leave it pending. */
  states?: Partial<Record<StageId, StageState>>;
  /** When set, each node links to that stage's page. */
  projectId?: string;
  orientation?: "horizontal" | "vertical";
  className?: string;
  /** Shown in the detail panel when nothing has run yet. */
  emptyHint?: string;
}) {
  const [active, setActive] = useState<StageId>(STAGES[0].id);
  const stage = STAGES.find((item) => item.id === active) ?? STAGES[0];
  const state = states?.[stage.id];
  const status = state?.status ?? "pending";
  const anyRun = Object.values(states ?? {}).some((item) => item?.status !== "pending");

  return (
    <div className={cn("w-full", className)}>
      {/* ── Node rail ───────────────────────────────────────────── */}
      <ol
        className={cn(
          "flex",
          orientation === "horizontal"
            ? "flex-col gap-1 sm:flex-row sm:items-start sm:gap-0"
            : "flex-col gap-1",
        )}
      >
        {STAGES.map((item, index) => {
          const itemState = states?.[item.id];
          const itemStatus = itemState?.status ?? "pending";
          const isActive = item.id === active;
          const isLast = index === STAGES.length - 1;
          const reached = itemStatus === "completed" || itemStatus === "running";

          const body = (
            <span className="flex w-full items-center gap-3 sm:flex-col sm:items-center sm:gap-2">
              <NodeMark stage={item} status={itemStatus} />
              <span className="flex min-w-0 flex-col sm:items-center">
                <span
                  className={cn(
                    "truncate text-[0.8125rem] font-medium transition-colors duration-[--duration-fast]",
                    isActive ? "text-ink" : "text-ink-muted",
                  )}
                >
                  {item.label}
                </span>
                <span className="mt-0.5 flex items-center gap-1 text-[0.625rem] text-ink-faint">
                  <StatusDot tone={STATUS_TONE[itemStatus]} pulse={itemStatus === "running"} />
                  {STATUS_LABEL[itemStatus]}
                </span>
              </span>
            </span>
          );

          return (
            <li
              key={item.id}
              className={cn("relative flex", orientation === "horizontal" ? "sm:flex-1" : "")}
              onMouseEnter={() => setActive(item.id)}
              onFocus={() => setActive(item.id)}
            >
              {/* Connector. The dashed overlay is the data travelling the edge;
                  it only animates for edges that have actually carried data. */}
              {!isLast && orientation === "horizontal" && (
                <span
                  className="pointer-events-none absolute top-[1.0625rem] left-[calc(50%+1.5rem)] hidden h-px sm:block"
                  style={{ width: "calc(100% - 3rem)" }}
                  aria-hidden
                >
                  <span className="absolute inset-0 bg-line" />
                  {reached && (
                    <span
                      className="absolute inset-0 bg-[linear-gradient(90deg,transparent,var(--color-brand),transparent)] bg-[length:36px_100%] bg-repeat-x opacity-70"
                      style={{
                        animation: "bf-flow 2.4s linear infinite",
                        maskImage: "linear-gradient(90deg,transparent,#000 20%,#000 80%,transparent)",
                      }}
                    />
                  )}
                </span>
              )}

              <button
                type="button"
                onClick={() => setActive(item.id)}
                aria-pressed={isActive}
                className={cn(
                  "relative z-10 w-full rounded-xl px-2 py-2.5 text-left transition-[background-color,transform] duration-[--duration-fast] ease-[--ease-out-soft]",
                  "hover:bg-sunken/70 sm:text-center",
                  isActive && "bg-sunken",
                )}
              >
                {body}
              </button>
            </li>
          );
        })}
      </ol>

      {/* ── Detail panel ────────────────────────────────────────── */}
      <div
        key={stage.id}
        className="bf-fade-up mt-4 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[0.625rem] font-semibold tracking-[0.14em] text-ink-faint tabular-nums">
                {stage.index}
              </span>
              <h3 className="text-sm font-semibold tracking-tight text-ink">{stage.label}</h3>
              <Badge tone={STATUS_TONE[status]} dot pulse={status === "running"}>
                {STATUS_LABEL[status]}
              </Badge>
            </div>
            <p className="mt-0.5 text-[0.6875rem] font-medium text-brand">{stage.role}</p>
          </div>
          {typeof state?.latencyMs === "number" && (
            <span className="tnum text-[0.6875rem] text-ink-faint">
              {state.latencyMs < 1000
                ? `${state.latencyMs} ms`
                : `${(state.latencyMs / 1000).toFixed(1)} s`}
            </span>
          )}
        </div>

        <p className="mt-2.5 max-w-2xl text-[0.8125rem] leading-relaxed text-ink-muted">
          {stage.blurb}
        </p>

        {state?.metrics?.length ? (
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2.5 border-t border-line pt-4 sm:grid-cols-3 lg:grid-cols-5">
            {state.metrics.map((metric) => (
              <div key={metric.label} className="min-w-0">
                <dt className="truncate text-[0.625rem] tracking-[0.08em] text-ink-faint uppercase">
                  {metric.label}
                </dt>
                <dd className="tnum mt-0.5 text-sm font-semibold text-ink">{metric.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="mt-4 border-t border-line pt-4 text-[0.75rem] text-ink-faint">
            {anyRun
              ? "This stage has not run in the latest pipeline execution."
              : (emptyHint ?? "Metrics appear here once a pipeline run has produced them.")}
          </p>
        )}

        {projectId && (
          <Link
            href={`/projects/${projectId}${stage.href}`}
            className="mt-4 inline-flex items-center gap-1 text-[0.8125rem] font-medium text-brand transition-colors hover:text-brand-strong"
          >
            Open {stage.label}
            <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden>
              <path d="M6 3.5 10.5 8 6 12.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        )}
      </div>
    </div>
  );
}

/**
 * Compact seven-dot progress indicator for project cards.
 *
 * Each dot is a link into that stage, so a card is a shortcut into any part of
 * the pipeline rather than just a status readout.
 */
export function PipelineDots({
  statuses,
  projectId,
  className,
}: {
  statuses: Record<StageId, StageStatus>;
  projectId: string;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-1", className)}>
      {STAGES.map((stage) => {
        const status = statuses[stage.id];
        return (
          <Link
            key={stage.id}
            href={`/projects/${projectId}${stage.href}`}
            onClick={(event) => event.stopPropagation()}
            title={`${stage.index} ${stage.label} — ${STATUS_LABEL[status]}`}
            className="group/dot relative grid h-5 flex-1 place-items-center"
          >
            <span
              className={cn(
                "h-1.5 w-full rounded-full transition-[background-color,transform] duration-[--duration-fast] ease-[--ease-out-soft]",
                "group-hover/dot:scale-y-150",
                status === "completed" && "bg-brand",
                status === "running" && "bg-brand/60",
                status === "failed" && "bg-bad",
                status === "pending" && "bg-inset",
              )}
            />
          </Link>
        );
      })}
    </div>
  );
}

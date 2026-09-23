"use client";

import Link from "next/link";
import { Check, Loader2, Minus, X } from "lucide-react";

import { Badge, Meter, StatusDot } from "@/components/ui/primitives";
import { STAGES, type StageId, type StageStatus } from "@/lib/pipeline";
import { formatDuration, relativeTime } from "@/lib/run-state";
import { cn } from "@/lib/utils";

/**
 * The BI engine readout.
 *
 * A live view of one pipeline run: which agents have finished, which is
 * working, and how far through the run is. Every value comes from the backend
 * — dataset name and row count from the profiled dataset, stage states from
 * `pipeline_steps`, runtime from the agents' recorded latency. When a project
 * has never run, the panel says so instead of showing a staged demo.
 */

const ICON: Record<StageStatus, typeof Check> = {
  completed: Check,
  running: Loader2,
  failed: X,
  pending: Minus,
};

const TONE = {
  completed: "good",
  running: "brand",
  failed: "bad",
  pending: "neutral",
} as const;

const LABEL: Record<StageStatus, string> = {
  completed: "COMPLETE",
  running: "RUNNING",
  failed: "FAILED",
  pending: "",
};

export function BIEngine({
  projectId,
  projectName,
  dataset,
  statuses,
  runStatus,
  runtimeMs,
  lastRunAt,
  className,
}: {
  projectId?: string;
  projectName?: string;
  dataset?: { name: string; rows: number | null; columns: number | null } | null;
  statuses?: Record<StageId, StageStatus>;
  runStatus?: string | null;
  runtimeMs?: number | null;
  lastRunAt?: string | null;
  className?: string;
}) {
  const done = statuses ? STAGES.filter((stage) => statuses[stage.id] === "completed").length : 0;
  const progress = (done / STAGES.length) * 100;
  const running = runStatus === "running" || runStatus === "queued";
  const relative = relativeTime(lastRunAt);

  return (
    <div
      className={cn(
        "rounded-panel border border-line bg-surface/80 shadow-lift backdrop-blur-xl",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="grid size-6 place-items-center rounded-md bg-brand/10 text-brand">
            <svg viewBox="0 0 16 16" className="size-3.5" fill="currentColor" aria-hidden>
              <path d="M2 11.5h3v3H2v-3Zm4.5-4h3v7h-3v-7ZM11 2h3v12.5h-3V2Z" />
            </svg>
          </span>
          <p className="text-[0.625rem] font-semibold tracking-[0.14em] text-ink-soft uppercase">
            BI Engine
          </p>
        </div>
        {runStatus ? (
          <Badge tone={running ? "brand" : runStatus === "completed" ? "good" : "warn"} dot pulse={running}>
            {running ? "running" : runStatus}
          </Badge>
        ) : (
          <Badge tone="neutral">idle</Badge>
        )}
      </div>

      {/* Dataset facts */}
      <dl className="grid grid-cols-3 gap-px border-b border-line bg-line">
        <Fact label="Dataset" value={dataset?.name ?? "—"} mono />
        <Fact
          label="Rows"
          value={dataset?.rows != null ? dataset.rows.toLocaleString("en-GB") : "—"}
        />
        <Fact label="Columns" value={dataset?.columns != null ? String(dataset.columns) : "—"} />
      </dl>

      {/* Stage list */}
      <ol className="space-y-0.5 p-3">
        {STAGES.map((stage) => {
          const status = statuses?.[stage.id] ?? "pending";
          const Icon = ICON[status];
          return (
            <li key={stage.id}>
              <Link
                href={projectId ? `/projects/${projectId}${stage.href}` : "#"}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors duration-[--duration-fast]",
                  projectId ? "hover:bg-sunken" : "pointer-events-none",
                )}
              >
                <span
                  className={cn(
                    "grid size-5 shrink-0 place-items-center rounded-full",
                    status === "completed" && "bg-good-soft text-good",
                    status === "running" && "bg-brand-soft text-brand",
                    status === "failed" && "bg-bad-soft text-bad",
                    status === "pending" && "bg-inset text-ink-faint",
                  )}
                >
                  <Icon className={cn("size-3", status === "running" && "animate-spin")} aria-hidden />
                </span>
                <span
                  className={cn(
                    "flex-1 truncate text-[0.8125rem]",
                    status === "pending" ? "text-ink-faint" : "text-ink-soft",
                  )}
                >
                  {stage.role}
                </span>
                {LABEL[status] && (
                  <span
                    className={cn(
                      "text-[0.5625rem] font-semibold tracking-[0.1em]",
                      status === "completed" && "text-good",
                      status === "running" && "text-brand",
                      status === "failed" && "text-bad",
                    )}
                  >
                    {LABEL[status]}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ol>

      {/* Progress */}
      <div className="border-t border-line px-4 py-3">
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-[0.625rem] tracking-[0.1em] text-ink-faint uppercase">
            {done} of {STAGES.length} agents
          </span>
          <span className="tnum text-[0.8125rem] font-semibold text-ink">
            {progress.toFixed(0)}%
          </span>
        </div>
        <Meter value={progress} tone={running ? "brand" : done === STAGES.length ? "good" : "neutral"} />
        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-[0.625rem] text-ink-faint">
          <span>{runtimeMs != null ? `Runtime ${formatDuration(runtimeMs)}` : "No run recorded"}</span>
          {relative && <span>Last run {relative}</span>}
        </div>
      </div>

      {!statuses && (
        <p className="border-t border-line px-4 py-3 text-[0.75rem] text-ink-muted">
          {projectName
            ? "This project has no pipeline run yet."
            : "Create a project and upload a dataset to see the engine work."}
        </p>
      )}
    </div>
  );
}

function Fact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-surface px-3 py-2.5">
      <dt className="text-[0.5625rem] tracking-[0.1em] text-ink-faint uppercase">{label}</dt>
      <dd
        className={cn(
          "mt-0.5 truncate text-[0.8125rem] font-medium text-ink",
          mono ? "font-mono text-[0.6875rem]" : "tnum",
        )}
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

/** Seven-dot agent roster used in the activity drawer and compact headers. */
export function AgentRoster({
  statuses,
  className,
}: {
  statuses: Record<StageId, StageStatus>;
  className?: string;
}) {
  return (
    <ul className={cn("space-y-1", className)}>
      {STAGES.map((stage) => {
        const status = statuses[stage.id];
        return (
          <li key={stage.id} className="flex items-center gap-2 text-[0.8125rem]">
            <StatusDot tone={TONE[status]} pulse={status === "running"} />
            <span className={status === "pending" ? "text-ink-faint" : "text-ink-soft"}>
              {stage.role}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

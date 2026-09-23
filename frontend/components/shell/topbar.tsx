"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Check, ChevronDown, Menu, Play, RotateCw } from "lucide-react";

import { CommandHint } from "@/components/shell/command-palette";
import { ThemeToggle } from "@/components/theme";
import { Badge, Button, StatusDot, statusTone } from "@/components/ui/primitives";
import { api, type PipelineRun, type Project } from "@/lib/api";
import { STAGES, type StageId, type StageStatus } from "@/lib/pipeline";
import { relativeTime } from "@/lib/run-state";
import { cn } from "@/lib/utils";

/**
 * Application header.
 *
 * Left: which project you are in, switchable. Centre: whether the pipeline is
 * healthy, derived from the auditor's verdict and the stage states rather than
 * asserted. Right: run controls, agent activity, theme.
 */
export function Topbar({
  project,
  statuses,
  onOpenNav,
  onOpenActivity,
  onRunPipeline,
  running,
  runPending,
  latest,
}: {
  project: Project;
  statuses: Record<StageId, StageStatus>;
  onOpenNav: () => void;
  onOpenActivity: () => void;
  onRunPipeline: () => void;
  running: boolean;
  runPending: boolean;
  latest?: PipelineRun;
}) {
  const [switcher, setSwitcher] = useState(false);
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects, enabled: switcher });

  const done = STAGES.filter((stage) => statuses[stage.id] === "completed").length;
  const failed = STAGES.some((stage) => statuses[stage.id] === "failed");
  const health = failed
    ? { tone: "bad" as const, label: "Pipeline has failures" }
    : running
      ? { tone: "brand" as const, label: "Pipeline running" }
      : done === STAGES.length
        ? { tone: "good" as const, label: "Pipeline healthy" }
        : done > 0
          ? { tone: "warn" as const, label: `${done}/${STAGES.length} stages complete` }
          : { tone: "neutral" as const, label: "Not run yet" };

  const lastRun = relativeTime(latest?.completed_at ?? latest?.started_at);

  return (
    <header className="sticky top-0 z-30 -mx-3 mb-4 border-b border-line bg-canvas/80 px-3 py-2.5 backdrop-blur-xl lg:-mx-4 lg:px-4">
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenNav}
          className="grid size-9 shrink-0 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-sunken hover:text-ink lg:hidden"
          aria-label="Open navigation"
        >
          <Menu className="size-4" aria-hidden />
        </button>

        {/* Project switcher */}
        <div className="relative min-w-0">
          <button
            onClick={() => setSwitcher((value) => !value)}
            aria-expanded={switcher}
            className="flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors duration-[--duration-fast] hover:bg-sunken"
          >
            <span className="min-w-0">
              <span className="block truncate text-[0.875rem] font-semibold tracking-tight text-ink">
                {project.name}
              </span>
              <span className="block truncate text-[0.625rem] text-ink-faint">
                {project.domain}
              </span>
            </span>
            <ChevronDown
              className={cn(
                "size-3.5 shrink-0 text-ink-faint transition-transform duration-[--duration-fast]",
                switcher && "rotate-180",
              )}
              aria-hidden
            />
          </button>

          {switcher && (
            <>
              <button
                className="fixed inset-0 z-10 cursor-default"
                onClick={() => setSwitcher(false)}
                aria-hidden
              />
              <div className="bf-scale-in absolute top-full left-0 z-20 mt-1 w-64 overflow-hidden rounded-card border border-line bg-raised p-1.5 shadow-float">
                {(projects.data ?? []).map((item) => (
                  <Link
                    key={item.id}
                    href={`/projects/${item.id}`}
                    onClick={() => setSwitcher(false)}
                    className="flex items-center gap-2 rounded-lg px-2 py-2 transition-colors hover:bg-sunken"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[0.8125rem] text-ink">{item.name}</span>
                      <span className="block truncate text-[0.625rem] text-ink-faint">
                        {item.domain}
                      </span>
                    </span>
                    {item.id === project.id && (
                      <Check className="size-3.5 shrink-0 text-brand" aria-hidden />
                    )}
                  </Link>
                ))}
                <Link
                  href="/"
                  onClick={() => setSwitcher(false)}
                  className="mt-1 block border-t border-line px-2 pt-2 pb-1 text-[0.75rem] text-brand hover:text-brand-strong"
                >
                  All projects
                </Link>
              </div>
            </>
          )}
        </div>

        {/* Health — centre on wide screens */}
        <div className="mx-auto hidden items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 xl:flex">
          <StatusDot tone={health.tone} pulse={running} />
          <span className="text-[0.75rem] font-medium text-ink-soft">{health.label}</span>
          {lastRun && (
            <>
              <span className="text-ink-faint" aria-hidden>
                ·
              </span>
              <span className="text-[0.75rem] text-ink-faint">Last run {lastRun}</span>
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <CommandHint />
          <button
            onClick={onOpenActivity}
            className="grid size-9 place-items-center rounded-lg text-ink-muted transition-colors duration-[--duration-fast] hover:bg-sunken hover:text-ink"
            aria-label="Agent activity"
            title="Agent activity"
          >
            <Activity className="size-4" aria-hidden />
          </button>
          <ThemeToggle className="hidden sm:inline-flex" />
          <Button onClick={onRunPipeline} disabled={runPending || running} size="sm">
            {runPending || running ? (
              <RotateCw className="animate-spin" aria-hidden />
            ) : (
              <Play aria-hidden />
            )}
            <span className="hidden sm:inline">
              {running ? "Running…" : latest ? "Re-run" : "Run pipeline"}
            </span>
          </Button>
        </div>
      </div>

      {/* Narrow-screen health line */}
      <div className="mt-2 flex items-center gap-2 xl:hidden">
        <StatusDot tone={health.tone} pulse={running} />
        <span className="text-[0.6875rem] text-ink-muted">{health.label}</span>
        {lastRun && <span className="text-[0.6875rem] text-ink-faint">· {lastRun}</span>}
      </div>
    </header>
  );
}

export { Badge, statusTone };

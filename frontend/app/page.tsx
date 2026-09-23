"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FolderPlus, ShieldCheck } from "lucide-react";

import { DataField } from "@/components/data-field";
import { PipelineGraph } from "@/components/pipeline-graph";
import { BIEngine } from "@/components/bi-engine";
import { ProjectCard } from "@/components/project-card";
import { NewProject } from "@/components/new-project";
import { ThemeToggle } from "@/components/theme";
import { Badge, Button, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { stageStatuses } from "@/lib/pipeline";
import { stageStatesFromRuns, runtimeMs, type AgentRun } from "@/lib/run-state";

/**
 * Homepage.
 *
 * The hero is the product, not a picture of it: the pipeline graph and the BI
 * engine readout both bind to the most recent real project. With no project
 * yet, they render an honest idle state rather than a staged demo.
 */
export default function HomePage() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects, retry: 1 });
  const featured = projects.data?.[0];

  const runs = useQuery({
    queryKey: ["runs", featured?.id],
    queryFn: () => api.runs(featured!.id),
    enabled: Boolean(featured),
    retry: false,
  });
  const latest = runs.data?.[0];

  const agents = useQuery({
    queryKey: ["agents", featured?.id],
    queryFn: () => api.agentRuns(featured!.id) as Promise<AgentRun[]>,
    enabled: Boolean(latest),
    retry: false,
  });
  const steps = useQuery({
    queryKey: ["steps", latest?.id],
    queryFn: () => api.steps(latest!.id),
    enabled: Boolean(latest),
    retry: false,
  });
  const datasets = useQuery({
    queryKey: ["datasets", featured?.id],
    queryFn: () => api.datasets(featured!.id),
    enabled: Boolean(featured),
    retry: false,
  });

  const states = stageStatesFromRuns(agents.data);
  const statuses = steps.data ? stageStatuses(steps.data) : undefined;
  const dataset = datasets.data?.[0];

  return (
    <div className="relative">
      {/* Ambient field, confined to the hero band. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[38rem] overflow-hidden">
        <DataField />
      </div>

      <div className="relative mx-auto max-w-[80rem] px-5 py-6 lg:px-8">
        {/* ── Masthead ──────────────────────────────────────────── */}
        <header className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-xl bg-shell text-[0.8125rem] font-bold text-white">
              B
            </span>
            <span className="text-sm font-semibold tracking-tight text-ink">BIFlow</span>
          </span>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {featured && (
              <Link href={`/projects/${featured.id}`}>
                <Button variant="secondary" size="sm">
                  Open workspace
                  <ArrowRight aria-hidden />
                </Button>
              </Link>
            )}
          </div>
        </header>

        {/* ── Hero ──────────────────────────────────────────────── */}
        <section className="grid items-start gap-10 pt-14 pb-4 lg:grid-cols-[1.15fr_0.85fr] lg:gap-12 lg:pt-20">
          <div className="bf-fade-up">
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1 text-[0.625rem] font-semibold tracking-[0.14em] text-ink-muted uppercase backdrop-blur">
              <span className="size-1.5 rounded-full bg-brand" aria-hidden />
              AI-orchestrated business intelligence
            </span>

            <h1 className="mt-5 text-[2.5rem] leading-[1.05] font-semibold tracking-[-0.02em] text-balance text-ink lg:text-[3.5rem]">
              From raw data
              <br />
              <span className="bg-gradient-to-r from-brand to-accent bg-clip-text text-transparent">
                to trusted decisions.
              </span>
            </h1>

            <p className="mt-5 max-w-xl text-[0.9375rem] leading-relaxed text-ink-soft lg:text-base">
              BIFlow automatically profiles, cleans, models, analyses and visualises your data —
              with every insight traceable back to the SQL that produced it.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link href="#start">
                <Button size="lg">
                  Start a project
                  <ArrowRight aria-hidden />
                </Button>
              </Link>
              {featured && (
                <Link href={`/projects/${featured.id}/audit`}>
                  <Button variant="secondary" size="lg">
                    <ShieldCheck aria-hidden />
                    See an audit trail
                  </Button>
                </Link>
              )}
            </div>

            <p className="mt-6 flex items-center gap-2 text-[0.75rem] text-ink-faint">
              <ShieldCheck className="size-3.5" aria-hidden />
              No number in this product is written by a language model.
            </p>
          </div>

          {/* Live engine readout */}
          <div className="bf-fade-up lg:pt-4" style={{ animationDelay: "80ms" }}>
            {projects.isLoading ? (
              <Skeleton className="h-[26rem] w-full" />
            ) : (
              <BIEngine
                projectId={featured?.id}
                projectName={featured?.name}
                dataset={
                  dataset
                    ? {
                        name: dataset.name,
                        rows: dataset.row_count,
                        columns: dataset.column_count,
                      }
                    : null
                }
                statuses={statuses}
                runStatus={latest?.status ?? null}
                runtimeMs={runtimeMs(agents.data)}
                lastRunAt={latest?.completed_at ?? latest?.started_at ?? null}
              />
            )}
          </div>
        </section>

        {/* ── Interactive pipeline ──────────────────────────────── */}
        <section className="bf-fade-up pt-10 lg:pt-14" style={{ animationDelay: "140ms" }}>
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-ink">
                Seven agents, one traceable pipeline
              </h2>
              <p className="mt-1 max-w-2xl text-[0.8125rem] text-ink-muted">
                Hover a stage to see what its agent does and what it produced on the latest run.
              </p>
            </div>
            {featured && latest && (
              <Badge tone="neutral">
                Live from {featured.name}
              </Badge>
            )}
          </div>

          <PipelineGraph
            states={states}
            projectId={featured?.id}
            emptyHint="Run a pipeline and each stage reports its real output here."
          />
        </section>

        {/* ── Projects ──────────────────────────────────────────── */}
        <section id="start" className="scroll-mt-8 pt-14 lg:pt-20">
          <div className="grid items-start gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="min-w-0">
              <div className="mb-4 flex items-baseline justify-between gap-3">
                <h2 className="text-lg font-semibold tracking-tight text-ink">Projects</h2>
                {projects.data && projects.data.length > 0 && (
                  <span className="text-[0.75rem] text-ink-faint">
                    {projects.data.length} total
                  </span>
                )}
              </div>

              {projects.isLoading && (
                <div className="space-y-3">
                  {[0, 1].map((index) => (
                    <Skeleton key={index} className="h-56 w-full" />
                  ))}
                </div>
              )}

              {projects.isError && (
                <ErrorState
                  title="BIFlow can't reach its API."
                  reason={(projects.error as Error).message}
                  action={
                    <Button variant="secondary" size="sm" onClick={() => projects.refetch()}>
                      Retry
                    </Button>
                  }
                />
              )}

              {projects.data?.length === 0 && (
                <EmptyState
                  title="No project yet"
                  message="Start with a dataset and a business question. BIFlow does the rest of the pipeline."
                  icon={<FolderPlus className="size-5" />}
                />
              )}

              <div className="space-y-3">
                {projects.data?.map((project) => (
                  <ProjectCard key={project.id} project={project} />
                ))}
              </div>
            </div>

            <div className="lg:sticky lg:top-6">
              <NewProject />
            </div>
          </div>
        </section>

        <footer className="mt-20 border-t border-line py-6 text-[0.75rem] text-ink-faint">
          BIFlow — multi-agent business intelligence. Deterministic engines compute every value;
          the audit trail proves it.
        </footer>
      </div>
    </div>
  );
}

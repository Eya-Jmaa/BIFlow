"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, FolderPlus, Plus, Sparkles } from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/data";
import { api, type Project } from "@/lib/api";

const DOMAINS = [
  "ecommerce",
  "retail",
  "finance",
  "banking",
  "telecommunications",
  "transport",
  "health",
  "marketing",
  "general",
];

const PIPELINE = [
  "Profile",
  "Clean",
  "Model",
  "Measure",
  "Analyse",
  "Visualise",
  "Audit",
];

export default function HomePage() {
  const queryClient = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [name, setName] = useState("E-Commerce BI Analysis");
  const [objective, setObjective] = useState(
    "Analyse e-commerce sales performance, customer behaviour, product mix and revenue evolution across countries.",
  );
  const [domain, setDomain] = useState("ecommerce");

  const create = useMutation({
    mutationFn: () => api.createProject({ name, business_objective: objective, domain }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });

  return (
    <div className="mx-auto max-w-6xl px-5 py-10 lg:px-8 lg:py-14">
      <header className="mb-10">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1 text-[0.6875rem] font-medium text-brand-strong ring-1 ring-brand/15 ring-inset">
          <Sparkles className="size-3" aria-hidden />
          Multi-agent business intelligence
        </span>
        <h1 className="mt-4 max-w-2xl text-[2rem] leading-tight font-semibold tracking-tight text-ink lg:text-[2.5rem]">
          From a raw file to an audited dashboard.
        </h1>
        <p className="mt-3 max-w-2xl text-[0.9375rem] leading-relaxed text-ink-soft">
          Give BIFlow a dataset and a business objective. Seven agents profile the data, fix what
          they can, infer a semantic model, compute a KPI catalog, analyse the results and explain
          every number back to the SQL that produced it.
        </p>
        <ol className="mt-6 flex flex-wrap items-center gap-x-1.5 gap-y-2">
          {PIPELINE.map((step, index) => (
            <li key={step} className="flex items-center gap-1.5">
              <span className="rounded-lg bg-surface px-2.5 py-1 text-xs font-medium text-ink-soft shadow-card ring-1 ring-line ring-inset">
                {step}
              </span>
              {index < PIPELINE.length - 1 && (
                <ArrowRight className="size-3 text-ink-faint" aria-hidden />
              )}
            </li>
          ))}
        </ol>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-tight text-ink">Projects</h2>
            {projects.data && projects.data.length > 0 && (
              <span className="text-xs text-ink-faint">{projects.data.length} total</span>
            )}
          </div>

          {projects.isLoading && (
            <div className="space-y-2.5">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-24 w-full" />
              ))}
            </div>
          )}

          {projects.error && (
            <EmptyState
              title="Cannot reach the API"
              message={(projects.error as Error).message}
              icon={<FolderPlus className="size-5" />}
            />
          )}

          {projects.data?.length === 0 && (
            <EmptyState
              title="No projects yet"
              message="Create one on the right, upload a dataset, then run the pipeline."
              icon={<FolderPlus className="size-5" />}
            />
          )}

          <div className="space-y-2.5">
            {projects.data?.map((project: Project) => (
              <Link key={project.id} href={`/projects/${project.id}`} className="block">
                <Card interactive className="group">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{project.name}</p>
                      <p className="mt-1 line-clamp-2 text-[0.8125rem] leading-relaxed text-ink-muted">
                        {project.business_objective}
                      </p>
                      <div className="mt-3 flex items-center gap-2">
                        <Badge tone="neutral">{project.domain}</Badge>
                        <span className="text-[0.6875rem] text-ink-faint">
                          {new Date(project.created_at).toLocaleDateString("en-GB", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })}
                        </span>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Badge tone={statusTone(project.status)} dot>
                        {project.status.replace(/_/g, " ")}
                      </Badge>
                      <ArrowRight
                        className="size-4 text-ink-faint transition-transform group-hover:translate-x-0.5"
                        aria-hidden
                      />
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </section>

        <Card className="lg:sticky lg:top-8">
          <CardHeader title="New project" subtitle="The objective steers domain inference." />

          <div className="space-y-4">
            <label className="block">
              <span className="text-[0.8125rem] font-medium text-ink-soft">Name</span>
              <input
                className="mt-1.5 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink transition-colors placeholder:text-ink-faint focus:border-brand"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Q4 revenue review"
              />
            </label>

            <label className="block">
              <span className="text-[0.8125rem] font-medium text-ink-soft">Domain</span>
              <select
                className="mt-1.5 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink focus:border-brand"
                value={domain}
                onChange={(event) => setDomain(event.target.value)}
              >
                {DOMAINS.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-[0.8125rem] font-medium text-ink-soft">Business objective</span>
              <textarea
                className="mt-1.5 min-h-28 w-full resize-y rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm leading-relaxed text-ink transition-colors placeholder:text-ink-faint focus:border-brand"
                value={objective}
                onChange={(event) => setObjective(event.target.value)}
                placeholder="What should this analysis answer?"
              />
            </label>
          </div>

          <Button
            className="mt-5 w-full"
            onClick={() => create.mutate()}
            disabled={create.isPending || !name.trim() || !objective.trim()}
          >
            <Plus aria-hidden />
            {create.isPending ? "Creating…" : "Create project"}
          </Button>

          {create.error && (
            <p className="mt-2.5 text-[0.8125rem] text-bad">{(create.error as Error).message}</p>
          )}
        </Card>
      </div>
    </div>
  );
}

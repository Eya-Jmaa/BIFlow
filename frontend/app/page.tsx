"use client";

import { api, type Project } from "@/lib/api";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

export default function HomePage() {
  const queryClient = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [name, setName] = useState("E-Commerce BI Analysis");
  const [objective, setObjective] = useState(
    "Analyze e-commerce sales performance, customer behavior, delivery performance and revenue evolution.",
  );
  const [domain, setDomain] = useState("ecommerce");
  const create = useMutation({
    mutationFn: () => api.createProject({ name, business_objective: objective, domain }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">BIFlow</p>
        <h1 className="mt-1 text-xl font-semibold">Autonomous multi-agent business intelligence</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Give BIFlow your real data and business objective. The platform profiles, cleans, models, analyzes and explains it.
        </p>
      </header>
      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-200">Projects</h2>
          {projects.isLoading && <p className="text-sm text-slate-500">Loading projects…</p>}
          {projects.error && <p className="text-sm text-red-400">{(projects.error as Error).message}</p>}
          {projects.data?.length === 0 && <p className="text-sm text-slate-500">No projects yet. Create one to start.</p>}
          <div className="space-y-2">
            {projects.data?.map((project: Project) => (
              <Link key={project.id} href={`/projects/${project.id}`}>
                <Card className="transition hover:border-slate-600">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{project.name}</p>
                      <p className="mt-1 line-clamp-2 text-sm text-slate-400">{project.business_objective}</p>
                    </div>
                    <Badge tone={statusTone(project.status)}>{project.status}</Badge>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </section>
        <Card>
          <h2 className="text-sm font-semibold">New project</h2>
          <label className="mt-4 block text-xs text-slate-400">
            Name
            <input
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="mt-3 block text-xs text-slate-400">
            Domain
            <select
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            >
              {["ecommerce", "retail", "finance", "telecommunications", "health", "general"].map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <label className="mt-3 block text-xs text-slate-400">
            Business objective
            <textarea
              className="mt-1 min-h-28 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
            />
          </label>
          <Button className="mt-4" onClick={() => create.mutate()} disabled={create.isPending || !name || !objective}>
            Create project
          </Button>
          {create.error && <p className="mt-2 text-sm text-red-400">{(create.error as Error).message}</p>}
        </Card>
      </main>
    </div>
  );
}

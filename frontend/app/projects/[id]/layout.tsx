"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ActivityDrawer } from "@/components/shell/activity-drawer";
import { CommandPalette } from "@/components/shell/command-palette";
import { Sidebar, SidebarDrawer } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { Button, EmptyState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { stageStatuses } from "@/lib/pipeline";

/**
 * Application shell.
 *
 * Owns the state every screen shares — which project, how far the pipeline
 * got, whether a run is in flight — so individual pages fetch only their own
 * artefacts and never re-derive navigation state.
 */
export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [navOpen, setNavOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);

  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () => api.project(id),
    retry: false,
  });

  const runs = useQuery({
    queryKey: ["runs", id],
    queryFn: () => api.runs(id),
    retry: false,
    // Poll only while something is in flight.
    refetchInterval: (query) => {
      const latest = query.state.data?.[0];
      return latest?.status === "running" || latest?.status === "queued" ? 2000 : false;
    },
  });
  const latest = runs.data?.[0];
  const running = latest?.status === "running" || latest?.status === "queued";

  const steps = useQuery({
    queryKey: ["steps", latest?.id],
    queryFn: () => api.steps(latest!.id),
    enabled: Boolean(latest),
    retry: false,
    refetchInterval: running ? 1500 : false,
  });
  const statuses = stageStatuses(steps.data);

  const runPipeline = useMutation({
    mutationFn: () => api.runPipeline(id),
    // A new run replaces every artefact on every screen.
    onSuccess: () => queryClient.invalidateQueries(),
  });

  if (project.isError) {
    return (
      <div className="mx-auto max-w-lg px-6 py-24">
        <EmptyState
          title="Project not found"
          message={(project.error as Error).message}
          action={
            <Link href="/">
              <Button variant="secondary">Back to projects</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar projectId={id} statuses={statuses} />
      <SidebarDrawer
        projectId={id}
        statuses={statuses}
        open={navOpen}
        onClose={() => setNavOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col px-3 pb-4 lg:px-4">
        {project.data ? (
          <Topbar
            project={project.data}
            statuses={statuses}
            latest={latest}
            running={running}
            runPending={runPipeline.isPending}
            onOpenNav={() => setNavOpen(true)}
            onOpenActivity={() => setActivityOpen(true)}
            onRunPipeline={() => runPipeline.mutate()}
          />
        ) : (
          <div className="mb-4 space-y-2 py-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-72" />
          </div>
        )}

        <main className="min-w-0 flex-1">{children}</main>
      </div>

      <ActivityDrawer
        projectId={id}
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
      />
      <CommandPalette projectId={id} onRunPipeline={() => runPipeline.mutate()} />
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";

import { MobileNav, Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/data";
import { api } from "@/lib/api";

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id: string }>();
  const project = useQuery({
    queryKey: ["project", params.id],
    queryFn: () => api.project(params.id),
    retry: false,
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
      <Sidebar projectId={params.id} />
      <div className="flex min-w-0 flex-1 flex-col gap-4 p-3 lg:p-4">
        <MobileNav projectId={params.id} />
        {project.data ? (
          <Topbar project={project.data} />
        ) : (
          <div className="space-y-2 pb-1">
            <Skeleton className="h-6 w-56" />
            <Skeleton className="h-4 w-96" />
          </div>
        )}
        <main className="min-w-0 flex-1 pb-2">{children}</main>
      </div>
    </div>
  );
}

"use client";

import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id: string }>();
  const project = useQuery({ queryKey: ["project", params.id], queryFn: () => api.project(params.id) });
  if (project.isLoading) {
    return <div className="p-8 text-sm text-slate-400">Loading project…</div>;
  }
  if (!project.data) {
    return <div className="p-8 text-sm text-red-400">Project not found.</div>;
  }
  return (
    <div className="flex min-h-screen">
      <Sidebar projectId={params.id} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar project={project.data} />
        <main className="flex-1 overflow-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}

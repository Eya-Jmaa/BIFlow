"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";

export default function SettingsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.project(id) });
  const remove = useMutation({
    mutationFn: () => api.deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push("/");
    },
  });

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="text-sm font-semibold">Exports</h2>
        <p className="mt-1 text-sm text-slate-400">Download computed KPIs, insights and methodology. Values come from the latest pipeline run.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(["json", "csv", "xlsx", "pdf"] as const).map((format) => (
            <a key={format} href={api.exportUrl(id, format)}>
              <Button variant="secondary">Export {format.toUpperCase()}</Button>
            </a>
          ))}
        </div>
      </Card>
      <Card>
        <h2 className="text-sm font-semibold">Project</h2>
        <p className="mt-2 text-sm text-slate-400">ID: {project.data?.id}</p>
        <p className="text-sm text-slate-400">Domain: {project.data?.domain}</p>
        <Button className="mt-4" variant="destructive" onClick={() => remove.mutate()}>
          Delete project
        </Button>
      </Card>
    </div>
  );
}

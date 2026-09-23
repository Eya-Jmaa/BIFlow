"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { Download, FileJson, FileSpreadsheet, FileText, Table2, Trash2 } from "lucide-react";

import {
  Badge,
  Button,
  Field,
  Panel,
  PanelHeader,
} from "@/components/ui/primitives";
import { ThemeToggle } from "@/components/theme";
import { api } from "@/lib/api";

const FORMATS = [
  { key: "json", label: "JSON", hint: "Full run artefacts", icon: FileJson },
  { key: "csv", label: "CSV", hint: "KPI values", icon: Table2 },
  { key: "xlsx", label: "Excel", hint: "Multi-sheet workbook", icon: FileSpreadsheet },
  { key: "pdf", label: "PDF", hint: "Report with methodology", icon: FileText },
] as const;

export default function SettingsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.project(id) });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () =>
      api.health() as Promise<{
        status: string;
        service: string;
        llm: { active: boolean; provider: string; model?: string; reason: string | null };
      }>,
    retry: false,
  });

  const remove = useMutation({
    mutationFn: () => api.deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push("/");
    },
  });

  return (
    <div className="max-w-3xl space-y-4">
      <Panel>
        <PanelHeader
          title="Export"
          subtitle="Values come from the latest run, with the formula and SQL behind each one."
        />
        <div className="grid gap-3 sm:grid-cols-2">
          {FORMATS.map((format) => {
            const Icon = format.icon;
            return (
              <a
                key={format.key}
                href={api.exportUrl(id, format.key)}
                className="flex items-center gap-3 rounded-card border border-line bg-sunken/50 p-3.5 transition-[border-color,background-color] duration-[--duration-fast] hover:border-brand/30 hover:bg-brand-soft/40"
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-surface text-brand shadow-card">
                  <Icon className="size-4" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[0.8125rem] font-medium text-ink">
                    {format.label}
                  </span>
                  <span className="block text-[0.6875rem] text-ink-muted">{format.hint}</span>
                </span>
                <Download className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
              </a>
            );
          })}
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Appearance" subtitle="Dark mode is a selected theme, not an inversion." />
        <ThemeToggle />
      </Panel>

      <Panel>
        <PanelHeader title="Project" />
        <dl className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">{project.data?.name ?? "—"}</Field>
          <Field label="Domain">{project.data?.domain ?? "—"}</Field>
          <Field label="Status">{project.data?.status.replace(/_/g, " ") ?? "—"}</Field>
          <Field label="Project ID">
            <span className="font-mono text-[0.6875rem]">{project.data?.id}</span>
          </Field>
        </dl>
      </Panel>

      {/* Real engine state, not a claim. */}
      {health.data && (
        <Panel>
          <PanelHeader title="Engine" subtitle="How this instance is configured" />
          <dl className="grid gap-4 sm:grid-cols-2">
            <Field label="API">
              <Badge tone={health.data.status === "ok" ? "good" : "bad"} dot>
                {health.data.status}
              </Badge>
            </Field>
            <Field label="LLM interpretation">
              <Badge tone={health.data.llm.active ? "good" : "neutral"} dot>
                {health.data.llm.active ? `${health.data.llm.provider} · ${health.data.llm.model}` : "off"}
              </Badge>
            </Field>
          </dl>
          {health.data.llm.reason && (
            <p className="mt-3 rounded-lg bg-sunken px-3 py-2 text-[0.75rem] leading-relaxed text-ink-muted">
              {health.data.llm.reason} Numbers are unaffected — every value is computed
              deterministically either way.
            </p>
          )}
        </Panel>
      )}

      <Panel className="border-bad/20">
        <PanelHeader
          title="Delete project"
          subtitle="Removes the project, its datasets and every artefact from all its runs. This cannot be undone."
        />
        {confirming ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending}>
              <Trash2 aria-hidden />
              {remove.isPending ? "Deleting…" : "Yes, delete permanently"}
            </Button>
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button variant="danger" onClick={() => setConfirming(true)}>
            <Trash2 aria-hidden />
            Delete project
          </Button>
        )}
        {remove.error && (
          <p className="mt-2.5 text-[0.8125rem] text-bad">{(remove.error as Error).message}</p>
        )}
      </Panel>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { CornerDownLeft, Play, Search } from "lucide-react";

import { api } from "@/lib/api";
import { STAGES } from "@/lib/pipeline";
import { cn } from "@/lib/utils";

/**
 * Command palette (⌘K / Ctrl-K).
 *
 * Entries are built from real state: the projects that exist, the stages of
 * the current project, and the KPIs the latest run actually computed. There
 * are no placeholder commands for features that do not exist.
 */

type Command = {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void;
};

export function CommandPalette({
  projectId,
  onRunPipeline,
}: {
  projectId?: string;
  onRunPipeline?: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects, enabled: open });
  const kpis = useQuery({
    queryKey: ["kpis", projectId],
    queryFn: () => api.kpis(projectId!),
    enabled: open && Boolean(projectId),
    retry: false,
  });

  // Global shortcut.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      // Focus after the panel has mounted so the caret lands correctly.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const list: Command[] = [];
    const go = (href: string) => () => {
      router.push(href);
      setOpen(false);
    };

    if (projectId) {
      list.push({
        id: "overview",
        label: "Overview",
        group: "Navigate",
        run: go(`/projects/${projectId}`),
      });
      for (const stage of STAGES) {
        list.push({
          id: `stage-${stage.id}`,
          label: `${stage.index} ${stage.label}`,
          hint: stage.role,
          group: "Navigate",
          run: go(`/projects/${projectId}${stage.href}`),
        });
      }
      list.push(
        {
          id: "datasets",
          label: "Datasets",
          group: "Navigate",
          run: go(`/projects/${projectId}/datasets`),
        },
        {
          id: "pipeline",
          label: "Pipeline runs",
          group: "Navigate",
          run: go(`/projects/${projectId}/pipeline`),
        },
        {
          id: "settings",
          label: "Settings",
          group: "Navigate",
          run: go(`/projects/${projectId}/settings`),
        },
      );

      if (onRunPipeline) {
        list.push({
          id: "run",
          label: "Run pipeline",
          hint: "Execute all seven agents",
          group: "Actions",
          run: () => {
            onRunPipeline();
            setOpen(false);
          },
        });
      }

      for (const kpi of kpis.data ?? []) {
        list.push({
          id: `kpi-${kpi.id}`,
          label: kpi.name,
          hint: kpi.formula,
          group: "KPIs",
          run: go(`/projects/${projectId}/measures?kpi=${kpi.id}`),
        });
      }
    }

    for (const project of projects.data ?? []) {
      if (project.id === projectId) continue;
      list.push({
        id: `project-${project.id}`,
        label: project.name,
        hint: project.domain,
        group: "Projects",
        run: go(`/projects/${project.id}`),
      });
    }

    return list;
  }, [projectId, projects.data, kpis.data, router, onRunPipeline]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands.slice(0, 24);
    return commands
      .filter(
        (command) =>
          command.label.toLowerCase().includes(needle) ||
          command.hint?.toLowerCase().includes(needle),
      )
      .slice(0, 24);
  }, [commands, query]);

  useEffect(() => setCursor(0), [query]);

  const grouped = useMemo(() => {
    const map = new Map<string, Command[]>();
    for (const command of filtered) {
      const list = map.get(command.group) ?? [];
      list.push(command);
      map.set(command.group, list);
    }
    return [...map.entries()];
  }, [filtered]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((value) => Math.min(value + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      filtered[cursor]?.run();
    }
  };

  if (!open) return null;

  let flatIndex = -1;

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[12vh]">
      <button
        className="bf-fade absolute inset-0 bg-shell/50 backdrop-blur-sm"
        onClick={() => setOpen(false)}
        aria-label="Close command palette"
      />
      <div
        role="dialog"
        aria-modal
        aria-label="Command palette"
        className="bf-scale-in relative w-full max-w-lg overflow-hidden rounded-panel border border-line bg-raised shadow-float"
      >
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <Search className="size-4 shrink-0 text-ink-faint" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search stages, KPIs, projects…"
            className="w-full bg-transparent py-3.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none"
          />
          <kbd className="shrink-0 rounded border border-line bg-inset px-1.5 py-0.5 text-[0.625rem] text-ink-faint">
            ESC
          </kbd>
        </div>

        <div className="max-h-[22rem] overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <p className="px-2 py-6 text-center text-[0.8125rem] text-ink-faint">
              Nothing matches “{query}”.
            </p>
          ) : (
            grouped.map(([group, items]) => (
              <div key={group} className="mb-1">
                <p className="px-2 py-1.5 text-[0.5625rem] font-semibold tracking-[0.14em] text-ink-faint uppercase">
                  {group}
                </p>
                {items.map((command) => {
                  flatIndex += 1;
                  const selected = flatIndex === cursor;
                  const position = flatIndex;
                  return (
                    <button
                      key={command.id}
                      onMouseEnter={() => setCursor(position)}
                      onClick={command.run}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors duration-[--duration-fast]",
                        selected ? "bg-brand-soft text-ink" : "text-ink-soft hover:bg-sunken",
                      )}
                    >
                      {command.group === "Actions" && (
                        <Play className="size-3.5 shrink-0 text-brand" aria-hidden />
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[0.8125rem] font-medium">
                          {command.label}
                        </span>
                        {command.hint && (
                          <span className="block truncate font-mono text-[0.625rem] text-ink-faint">
                            {command.hint}
                          </span>
                        )}
                      </span>
                      {selected && (
                        <CornerDownLeft className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

/** The affordance in the topbar that tells people the palette exists. */
export function CommandHint({ className }: { className?: string }) {
  const [mac, setMac] = useState(false);
  useEffect(() => setMac(/Mac|iPhone|iPad/.test(navigator.platform)), []);
  return (
    <button
      onClick={() =>
        window.dispatchEvent(
          new KeyboardEvent("keydown", { key: "k", ctrlKey: !mac, metaKey: mac, bubbles: true }),
        )
      }
      className={cn(
        "hidden items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.75rem] text-ink-faint md:flex",
        "transition-colors duration-[--duration-fast] hover:border-line-strong hover:text-ink-muted",
        className,
      )}
    >
      <Search className="size-3.5" aria-hidden />
      <span>Search</span>
      <kbd className="rounded border border-line bg-inset px-1 py-0.5 text-[0.625rem]">
        {mac ? "⌘" : "Ctrl"} K
      </kbd>
    </button>
  );
}

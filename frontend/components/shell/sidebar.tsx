"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Database,
  Gauge,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  Plug,
  Settings,
  ShieldCheck,
  Sparkles,
  Table2,
  Workflow,
  X,
} from "lucide-react";

import { StatusDot } from "@/components/ui/primitives";
import { STAGES, type StageId, type StageStatus } from "@/lib/pipeline";
import { cn } from "@/lib/utils";

/**
 * Workspace navigation.
 *
 * The middle group is the pipeline in execution order, numbered, with each
 * item carrying that stage's live status — so the sidebar doubles as a map of
 * how far the run got. Sections below it are cross-cutting views.
 */

const STAGE_ICON: Record<StageId, typeof Gauge> = {
  profile: Gauge,
  clean: ListChecks,
  model: GitBranch,
  measure: BarChart3,
  analyze: Sparkles,
  visualize: Activity,
  audit: ShieldCheck,
};

const TONE = {
  completed: "good",
  running: "brand",
  failed: "bad",
  pending: "neutral",
} as const;

export function SidebarContent({
  projectId,
  statuses,
  onNavigate,
}: {
  projectId: string;
  statuses: Record<StageId, StageStatus>;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;

  const isActive = (href: string) => (href === base ? pathname === base : pathname.startsWith(href));

  const Item = ({
    href,
    icon: Icon,
    label,
    index,
    status,
  }: {
    href: string;
    icon: typeof Gauge;
    label: string;
    index?: string;
    status?: StageStatus;
  }) => {
    const active = isActive(href);
    return (
      <li>
        <Link
          href={href}
          onClick={onNavigate}
          aria-current={active ? "page" : undefined}
          className={cn(
            "group/nav relative flex items-center gap-2.5 rounded-lg py-2 pr-2.5 pl-2.5 text-[0.8125rem]",
            "transition-[background-color,color] duration-[--duration-fast] ease-[--ease-out-soft]",
            active ? "bg-white/[0.07] font-medium text-white" : "text-white/55 hover:bg-white/[0.04] hover:text-white/90",
          )}
        >
          {/* Active rail, animated in rather than popped in. */}
          <span
            className={cn(
              "absolute top-1/2 left-0 h-4 w-0.5 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-brand to-accent",
              "transition-[opacity,transform] duration-[--duration-base] ease-[--ease-out-soft]",
              active ? "scale-y-100 opacity-100" : "scale-y-0 opacity-0",
            )}
            aria-hidden
          />
          {index ? (
            <span
              className={cn(
                "w-4 shrink-0 text-[0.625rem] font-semibold tabular-nums transition-colors",
                active ? "text-brand" : "text-white/30 group-hover/nav:text-white/50",
              )}
            >
              {index}
            </span>
          ) : (
            <Icon className="size-4 shrink-0" aria-hidden />
          )}
          <span className="flex-1 truncate">{label}</span>
          {status && status !== "pending" && (
            <StatusDot tone={TONE[status]} pulse={status === "running"} />
          )}
        </Link>
      </li>
    );
  };

  const Group = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div>
      <p className="px-2.5 pb-1.5 text-[0.5625rem] font-semibold tracking-[0.16em] text-white/25 uppercase">
        {label}
      </p>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );

  return (
    <nav className="flex h-full flex-col" aria-label="Workspace">
      <Link
        href="/"
        onClick={onNavigate}
        className="flex items-center gap-2.5 px-4 pt-5 pb-6 transition-opacity hover:opacity-80"
      >
        <span className="grid size-8 place-items-center rounded-xl bg-gradient-to-br from-brand to-accent text-[0.8125rem] font-bold text-white">
          B
        </span>
        <span className="min-w-0">
          <span className="block text-sm leading-tight font-semibold tracking-tight text-white/95">
            BIFlow
          </span>
          <span className="block text-[0.625rem] leading-tight text-white/40">
            Multi-agent BI
          </span>
        </span>
      </Link>

      <div className="flex-1 space-y-5 overflow-y-auto px-2.5 pb-4">
        <Group label="Workspace">
          <Item href={base} icon={LayoutDashboard} label="Overview" />
          <Item href={`${base}/datasets`} icon={Database} label="Datasets" />
          <Item href={`${base}/pipeline`} icon={Workflow} label="Pipeline runs" />
        </Group>

        <Group label="Pipeline">
          {STAGES.map((stage) => (
            <Item
              key={stage.id}
              href={`${base}${stage.href}`}
              icon={STAGE_ICON[stage.id]}
              label={stage.label}
              index={stage.index}
              status={statuses[stage.id]}
            />
          ))}
        </Group>

        <Group label="System">
          <Item href={`${base}/connections`} icon={Plug} label="Connections" />
          <Item href={`${base}/settings`} icon={Settings} label="Settings" />
        </Group>
      </div>
    </nav>
  );
}

/** Persistent rail on large screens. */
export function Sidebar({
  projectId,
  statuses,
}: {
  projectId: string;
  statuses: Record<StageId, StageStatus>;
}) {
  return (
    <aside className="hidden shrink-0 p-3 pr-0 lg:block lg:w-[15rem]">
      <div className="sticky top-3 h-[calc(100vh-1.5rem)] overflow-hidden rounded-panel bg-shell shadow-shell">
        <SidebarContent projectId={projectId} statuses={statuses} />
      </div>
    </aside>
  );
}

/** Slide-over drawer below the lg breakpoint. */
export function SidebarDrawer({
  projectId,
  statuses,
  open,
  onClose,
}: {
  projectId: string;
  statuses: Record<StageId, StageStatus>;
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button
        className="bf-fade absolute inset-0 bg-shell/60 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Close navigation"
      />
      <div className="bf-slide-left absolute inset-y-0 left-0 w-[16rem] bg-shell shadow-shell">
        <button
          onClick={onClose}
          className="absolute top-4 right-3 grid size-8 place-items-center rounded-lg text-white/50 transition-colors hover:bg-white/10 hover:text-white"
          aria-label="Close navigation"
        >
          <X className="size-4" aria-hidden />
        </button>
        <SidebarContent projectId={projectId} statuses={statuses} onNavigate={onClose} />
      </div>
    </div>
  );
}

export { Table2 };

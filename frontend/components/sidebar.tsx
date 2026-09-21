"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Database,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  Settings,
  Shield,
  Sparkles,
  Waypoints,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The pipeline in navigation order.
 *
 * The sections follow the order the agents run in, so the sidebar doubles as a
 * map of what the system did: ingest, profile, clean, model, measure, explain.
 */
const GROUPS = [
  {
    label: "Workspace",
    items: [
      { href: "", label: "Overview", icon: LayoutDashboard },
      { href: "/datasets", label: "Datasets", icon: Database },
      { href: "/pipeline", label: "Pipeline", icon: Workflow },
    ],
  },
  {
    label: "Model",
    items: [
      { href: "/quality", label: "Data Quality", icon: ListChecks },
      { href: "/semantic", label: "Semantic Model", icon: GitBranch },
      { href: "/kpis", label: "KPIs", icon: BarChart3 },
    ],
  },
  {
    label: "Analysis",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: Activity },
      { href: "/insights", label: "Insights", icon: Sparkles },
      { href: "/audit", label: "Audit / XAI", icon: Shield },
      { href: "/lineage", label: "Lineage", icon: Waypoints },
    ],
  },
];

export function Sidebar({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;

  return (
    <aside className="hidden shrink-0 p-3 pr-0 lg:block lg:w-60">
      {/* A floating panel rather than a full-height rail: it lets the canvas
          wash show through and keeps the shell visually separate from content. */}
      <div className="sticky top-3 flex h-[calc(100vh-1.5rem)] flex-col rounded-card bg-shell shadow-shell">
        <Link
          href="/"
          className="flex items-center gap-2.5 px-5 pt-5 pb-6 text-white/95 transition-opacity hover:opacity-80"
        >
          <span className="grid size-8 place-items-center rounded-xl bg-gradient-to-br from-brand to-accent text-[0.8125rem] font-bold text-white">
            B
          </span>
          <span className="min-w-0">
            <span className="block text-sm leading-tight font-semibold tracking-tight">BIFlow</span>
            <span className="block text-[0.6875rem] leading-tight text-white/45">
              Multi-agent BI
            </span>
          </span>
        </Link>

        <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-3" aria-label="Project sections">
          {GROUPS.map((group) => (
            <div key={group.label}>
              <p className="px-2.5 pb-1.5 text-[0.625rem] font-semibold tracking-[0.12em] text-white/30 uppercase">
                {group.label}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const href = `${base}${item.href}` || base;
                  const active =
                    item.href === "" ? pathname === base : pathname.startsWith(href);
                  const Icon = item.icon;
                  return (
                    <li key={href}>
                      <Link
                        href={href}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.8125rem] transition-colors duration-150",
                          active
                            ? "bg-gradient-to-r from-brand to-accent font-medium text-white shadow-sm"
                            : "text-white/55 hover:bg-white/8 hover:text-white/90",
                        )}
                      >
                        <Icon className="size-4 shrink-0" aria-hidden />
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="p-3 pt-0">
          <Link
            href={`${base}/settings`}
            aria-current={pathname.startsWith(`${base}/settings`) ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[0.8125rem] transition-colors duration-150",
              pathname.startsWith(`${base}/settings`)
                ? "bg-white/12 font-medium text-white"
                : "text-white/55 hover:bg-white/8 hover:text-white/90",
            )}
          >
            <Settings className="size-4 shrink-0" aria-hidden />
            Settings
          </Link>
        </div>
      </div>
    </aside>
  );
}

/** Horizontal nav for narrow screens, where the rail is hidden. */
export function MobileNav({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const items = [...GROUPS.flatMap((group) => group.items), { href: "/settings", label: "Settings", icon: Settings }];

  return (
    <nav
      className="flex gap-1 overflow-x-auto rounded-card bg-shell p-1.5 shadow-shell lg:hidden"
      aria-label="Project sections"
    >
      {items.map((item) => {
        const href = `${base}${item.href}` || base;
        const active = item.href === "" ? pathname === base : pathname.startsWith(href);
        const Icon = item.icon;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs whitespace-nowrap transition-colors",
              active
                ? "bg-gradient-to-r from-brand to-accent font-medium text-white"
                : "text-white/55 hover:text-white/90",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

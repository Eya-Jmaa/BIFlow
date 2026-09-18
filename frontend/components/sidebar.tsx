"use client";

import { cn } from "@/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Database,
  FileSearch,
  GitBranch,
  LayoutDashboard,
  ListChecks,
  Settings,
  Shield,
  Sparkles,
  Workflow,
} from "lucide-react";

const items = [
  { href: "", label: "Overview", icon: LayoutDashboard },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/pipeline", label: "Pipeline", icon: Workflow },
  { href: "/quality", label: "Data Quality", icon: ListChecks },
  { href: "/semantic", label: "Semantic Model", icon: GitBranch },
  { href: "/kpis", label: "KPIs", icon: BarChart3 },
  { href: "/insights", label: "Insights", icon: Sparkles },
  { href: "/dashboard", label: "Dashboard", icon: Activity },
  { href: "/audit", label: "Audit / XAI", icon: Shield },
  { href: "/lineage", label: "Lineage", icon: FileSearch },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  return (
    <aside className="hidden w-56 shrink-0 border-r border-slate-800 bg-[#0b1220] md:flex md:flex-col">
      <div className="border-b border-slate-800 px-4 py-4">
        <Link href="/" className="text-sm font-semibold tracking-tight text-slate-100">
          BIFlow
        </Link>
        <p className="mt-1 text-[11px] text-slate-500">Multi-agent BI platform</p>
      </div>
      <nav className="flex-1 space-y-0.5 p-2" aria-label="Project sections">
        {items.map((item) => {
          const href = `${base}${item.href}` || base;
          const active = item.href === "" ? pathname === base : pathname.startsWith(href);
          const Icon = item.icon;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-300 hover:bg-slate-800 hover:text-white",
                active && "bg-slate-800 text-white",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

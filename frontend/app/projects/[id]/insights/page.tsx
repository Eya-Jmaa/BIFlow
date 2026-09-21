"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  Lightbulb,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Code, EmptyState } from "@/components/ui/data";
import { Toggle } from "@/components/ui/button";
import { api, type Insight } from "@/lib/api";
import { formatValue } from "@/lib/viz";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  { key: "risk", title: "Risks", icon: ShieldAlert, tone: "text-bad bg-bad-soft" },
  { key: "anomaly", title: "Anomalies", icon: AlertTriangle, tone: "text-warn bg-warn-soft" },
  { key: "opportunity", title: "Opportunities", icon: Lightbulb, tone: "text-good bg-good-soft" },
  { key: "trend", title: "Trends", icon: TrendingUp, tone: "text-brand bg-brand-soft" },
  { key: "finding", title: "Findings", icon: Search, tone: "text-ink-soft bg-surface-sunken" },
  {
    key: "quality_caveat",
    title: "Data caveats",
    icon: AlertTriangle,
    tone: "text-warn bg-warn-soft",
  },
] as const;

export default function InsightsPage() {
  const { id } = useParams<{ id: string }>();
  const insights = useQuery({
    queryKey: ["insights", id],
    queryFn: () => api.insights(id),
    retry: false,
  });
  const [filter, setFilter] = useState<string>("all");

  if (insights.isError) {
    return (
      <EmptyState
        title="No insights yet"
        message="Run the pipeline. The analyst agent reads the computed KPI series and ranks what is worth saying."
        icon={<Sparkles className="size-5" />}
      />
    );
  }

  const items = insights.data ?? [];
  const counts = Object.fromEntries(
    CATEGORIES.map((category) => [
      category.key,
      items.filter((item) => item.category === category.key).length,
    ]),
  );
  const shown = filter === "all" ? items : items.filter((item) => item.category === filter);
  const headline = items.filter((item) => item.severity === "warning").slice(0, 3);

  return (
    <div className="space-y-4">
      {headline.length > 0 && (
        <Card className="border-warn/20 bg-gradient-to-br from-warn-soft/70 to-surface">
          <CardHeader
            title="What needs attention"
            subtitle="Ranked by severity, effect size and confidence"
            action={
              <span className="grid size-8 place-items-center rounded-xl bg-warn-soft text-warn">
                <AlertTriangle className="size-4" aria-hidden />
              </span>
            }
          />
          <ul className="space-y-2.5">
            {headline.map((item) => (
              <li key={item.id} className="flex gap-2.5 text-[0.8125rem] leading-snug text-ink-soft">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warn" aria-hidden />
                <span>
                  <span className="font-medium text-ink">{item.title}.</span>{" "}
                  {item.description}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-1 rounded-card border border-line bg-surface p-1.5 shadow-card">
        <Toggle active={filter === "all"} onClick={() => setFilter("all")}>
          All {items.length}
        </Toggle>
        {CATEGORIES.filter((category) => counts[category.key] > 0).map((category) => (
          <Toggle
            key={category.key}
            active={filter === category.key}
            onClick={() => setFilter(category.key)}
          >
            {category.title} {counts[category.key]}
          </Toggle>
        ))}
      </div>

      {shown.length === 0 ? (
        <EmptyState title="Nothing in this category" icon={<Sparkles className="size-5" />} />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {shown.map((item) => (
            <InsightCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function InsightCard({ item }: { item: Insight }) {
  const [open, setOpen] = useState(false);
  const category =
    CATEGORIES.find((entry) => entry.key === item.category) ??
    CATEGORIES[CATEGORIES.length - 2];
  const Icon = category.icon;

  return (
    <Card className="flex h-full flex-col">
      <div className="flex items-start gap-3">
        <span className={cn("grid size-8 shrink-0 place-items-center rounded-xl", category.tone)}>
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium text-ink">{item.title}</p>
            <Badge tone={statusTone(item.severity)}>{item.severity}</Badge>
          </div>
          <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-soft">
            {item.description}
          </p>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line pt-3 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-ink-faint">Metric</dt>
          <dd className="mt-0.5 truncate font-medium text-ink-soft">{item.metric || "—"}</dd>
        </div>
        <div>
          <dt className="text-ink-faint">Value</dt>
          <dd className="mt-0.5 font-medium tabular-nums text-ink-soft">
            {formatValue(item.value, {}, {})}
          </dd>
        </div>
        <div>
          <dt className="text-ink-faint">Confidence</dt>
          <dd className="mt-0.5 font-medium tabular-nums text-ink-soft">
            {(item.confidence * 100).toFixed(0)}%
          </dd>
        </div>
        <div>
          <dt className="text-ink-faint">Grounded</dt>
          <dd className="mt-0.5 font-medium text-ink-soft">{item.grounded ? "yes" : "no"}</dd>
        </div>
      </dl>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase transition-colors hover:text-ink-muted"
        >
          {open ? "Hide evidence" : "Show evidence"}
        </button>
        {open && (
          <Code className="mt-2 max-h-48">{JSON.stringify(item.evidence, null, 2)}</Code>
        )}
      </div>
    </Card>
  );
}

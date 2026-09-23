"use client";

import { cn } from "@/lib/utils";
import { formatValue } from "@/lib/viz";
import type { ValueFormat } from "@/lib/viz";

/**
 * Small analytical marks.
 *
 * These are inline SVG rather than a charting library: at 80×24 a sparkline
 * needs no axes, no tooltip layer and no responsive container, and a hundred
 * of them in a table should cost nothing. Full charts still use Recharts.
 *
 * Colour comes from `currentColor` so a mark inherits the tone of whatever it
 * sits in, and never has to be recoloured per-theme.
 */

export function Sparkline({
  values,
  className,
  width = 72,
  height = 22,
  /** Marks the final point — used where the last period is incomplete. */
  flagLast,
}: {
  values: (number | null)[];
  className?: string;
  width?: number;
  height?: number;
  flagLast?: boolean;
}) {
  const points = values.filter((value): value is number => value !== null && !Number.isNaN(value));
  if (points.length < 2) {
    return <span className={cn("text-[0.6875rem] text-ink-faint", className)}>—</span>;
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const y = (value: number) => height - 2 - ((value - min) / span) * (height - 4);
  const path = points.map((value, index) => `${index === 0 ? "M" : "L"}${index * step},${y(value)}`).join(" ");
  const last = { x: (points.length - 1) * step, y: y(points[points.length - 1]) };

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("overflow-visible", className)}
      aria-hidden
    >
      <path d={path} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      <circle
        cx={last.x}
        cy={last.y}
        r={flagLast ? 2.4 : 1.8}
        fill={flagLast ? "var(--color-surface)" : "currentColor"}
        stroke={flagLast ? "var(--color-warn)" : "none"}
        strokeWidth={flagLast ? 1.4 : 0}
      />
    </svg>
  );
}

/**
 * Horizontal frequency bars for a categorical column's top values.
 *
 * One hue for every bar: length already encodes magnitude, so colouring by
 * value would spend the only free channel restating it.
 */
export function FrequencyBars({
  items,
  total,
  className,
  max = 5,
}: {
  items: { value: string; count: number }[];
  total: number;
  className?: string;
  max?: number;
}) {
  if (!items.length) return <p className="text-[0.6875rem] text-ink-faint">No values</p>;
  const top = items.slice(0, max);
  const peak = Math.max(...top.map((item) => item.count)) || 1;

  return (
    <ul className={cn("space-y-1.5", className)}>
      {top.map((item) => {
        const share = total ? (item.count / total) * 100 : 0;
        return (
          <li key={item.value} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
            <span className="truncate text-[0.6875rem] text-ink-soft" title={item.value}>
              {item.value === "" ? "(empty)" : item.value}
            </span>
            <span className="tnum text-[0.6875rem] text-ink-faint">{share.toFixed(1)}%</span>
            <span className="col-span-2 h-1 overflow-hidden rounded-full bg-inset">
              <span
                className="block h-full rounded-full bg-series-1 transition-[width] duration-[--duration-slow] ease-[--ease-out-soft]"
                style={{ width: `${(item.count / peak) * 100}%` }}
              />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * A five-number summary drawn as a box plot.
 *
 * Quantiles are what the profiler actually computes, so this shows the real
 * distribution shape rather than a histogram the backend never produced.
 */
export function QuantileStrip({
  min,
  q25,
  median,
  q75,
  max,
  className,
}: {
  min: number;
  q25: number;
  median: number;
  q75: number;
  max: number;
  className?: string;
}) {
  const span = max - min || 1;
  const pos = (value: number) => ((value - min) / span) * 100;

  return (
    <div className={cn("relative h-5 w-full", className)} aria-hidden>
      {/* Whiskers */}
      <div className="absolute top-1/2 right-0 left-0 h-px -translate-y-1/2 bg-line-strong" />
      {/* Interquartile box */}
      <div
        className="absolute top-1/2 h-3 -translate-y-1/2 rounded-[3px] bg-series-1/25 ring-1 ring-series-1/50"
        style={{ left: `${pos(q25)}%`, width: `${Math.max(pos(q75) - pos(q25), 1)}%` }}
      />
      {/* Median */}
      <div
        className="absolute top-1/2 h-3.5 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-series-1"
        style={{ left: `${pos(median)}%` }}
      />
    </div>
  );
}

/** A compact share-of-total bar, for quality axes and coverage figures. */
export function ShareBar({
  value,
  tone = "brand",
  className,
}: {
  value: number;
  tone?: "brand" | "good" | "warn" | "bad";
  className?: string;
}) {
  const fill = { brand: "bg-brand", good: "bg-good", warn: "bg-warn", bad: "bg-bad" }[tone];
  return (
    <div className={cn("h-1 w-full overflow-hidden rounded-full bg-inset", className)}>
      <div
        className={cn("h-full rounded-full transition-[width] duration-[--duration-slow] ease-[--ease-out-soft]", fill)}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

/**
 * A metric with its label and optional delta.
 *
 * Direction is carried by an arrow and a word as well as colour, so the
 * reading does not depend on hue.
 */
export function Metric({
  label,
  value,
  unit,
  format,
  delta,
  compact = true,
  className,
}: {
  label: string;
  value: number | null | undefined;
  unit?: string | null;
  format?: ValueFormat;
  delta?: { value: string; direction: "up" | "down" | "flat"; favourable: boolean | null } | null;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="truncate text-[0.8125rem] font-medium text-ink-muted">{label}</p>
      <p className="mt-1.5 text-[1.625rem] leading-none font-semibold tracking-tight text-ink">
        {formatValue(value, format, { unit, compact })}
      </p>
      {delta && (
        <p className="mt-2 flex items-center gap-1.5 text-xs">
          <span
            className={cn(
              "font-medium",
              delta.favourable === null
                ? "text-ink-muted"
                : delta.favourable
                  ? "text-good"
                  : "text-bad",
            )}
          >
            {delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "—"} {delta.value}
          </span>
          <span className="text-ink-faint">vs previous period</span>
        </p>
      )}
    </div>
  );
}

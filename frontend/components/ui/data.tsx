"use client";

import { cn } from "@/lib/utils";

/**
 * Shared display pieces.
 *
 * Every page used to hand-roll its own table, empty state and stat block, so
 * spacing and type drifted between screens. These are the one definition.
 */

export function StatTile({
  label,
  value,
  delta,
  hint,
  icon,
  tone = "brand",
}: {
  label: string;
  value: React.ReactNode;
  delta?: { value: string; direction: "up" | "down" | "flat"; favourable?: boolean | null } | null;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  tone?: "brand" | "accent" | "good" | "warn";
}) {
  const iconTone = {
    brand: "bg-brand-soft text-brand",
    accent: "bg-[#f6ecfe] text-accent",
    good: "bg-good-soft text-good",
    warn: "bg-warn-soft text-warn",
  }[tone];

  return (
    <div className="rounded-card border border-line bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[0.8125rem] font-medium text-ink-muted">{label}</p>
          {/* Hero figure: proportional digits, same sans as everything else. */}
          <p className="mt-2 text-[1.75rem] leading-none font-semibold tracking-tight text-ink">
            {value}
          </p>
        </div>
        {icon && (
          <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl", iconTone)}>
            {icon}
          </span>
        )}
      </div>
      {delta && <Delta {...delta} />}
      {!delta && hint && <p className="mt-2.5 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}

/** Direction is carried by an arrow and a word, never by colour alone. */
export function Delta({
  value,
  direction,
  favourable,
  className,
}: {
  value: string;
  direction: "up" | "down" | "flat";
  favourable?: boolean | null;
  className?: string;
}) {
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "—";
  const colour =
    favourable === null || favourable === undefined || direction === "flat"
      ? "text-ink-muted"
      : favourable
        ? "text-good"
        : "text-bad";
  return (
    <p className={cn("mt-2.5 flex items-center gap-1.5 text-xs", className)}>
      <span className={cn("font-medium", colour)}>
        {arrow} {value}
      </span>
      <span className="text-ink-faint">{direction === "flat" ? "no change" : direction}</span>
    </p>
  );
}

export function Table({
  head,
  children,
  className,
}: {
  head: React.ReactNode[];
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("-mx-1 overflow-x-auto px-1", className)}>
      <table className="w-full min-w-full text-left text-[0.8125rem]">
        <thead>
          <tr className="border-b border-line">
            {head.map((cell, index) => (
              <th
                key={index}
                className="pb-2.5 pr-4 text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase last:pr-0"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export function Row({ children, className }: { children: React.ReactNode; className?: string }) {
  return <tr className={cn("hover:bg-surface-muted/70", className)}>{children}</tr>;
}

export function Cell({
  children,
  className,
  numeric,
}: {
  children: React.ReactNode;
  className?: string;
  numeric?: boolean;
}) {
  return (
    <td
      className={cn(
        "py-2.5 pr-4 align-top text-ink-soft",
        // Aligned columns get equal-width digits; standalone figures do not.
        numeric && "text-right tabular-nums text-ink",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function EmptyState({
  title,
  message,
  action,
  icon,
}: {
  title: string;
  message?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-line-strong bg-surface-muted/60 px-6 py-12 text-center">
      {icon && (
        <span className="mb-3 grid size-11 place-items-center rounded-2xl bg-surface text-ink-faint shadow-card">
          {icon}
        </span>
      )}
      <p className="text-sm font-medium text-ink">{title}</p>
      {message && <p className="mt-1 max-w-sm text-[0.8125rem] text-ink-muted">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-surface-sunken", className)} />;
}

/** A labelled value, used wherever a page lists metadata. */
export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase">
        {label}
      </dt>
      <dd className="mt-1 text-[0.8125rem] break-words text-ink-soft">{children}</dd>
    </div>
  );
}

export function Code({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <pre
      className={cn(
        "overflow-auto rounded-lg border border-line bg-surface-sunken p-3 font-mono text-[0.6875rem] leading-relaxed text-ink-soft",
        className,
      )}
    >
      {children}
    </pre>
  );
}

/** A thin meter, for scores that are naturally 0–100. */
export function Meter({ value, tone = "brand" }: { value: number; tone?: "brand" | "good" | "warn" | "bad" }) {
  const colour = { brand: "bg-brand", good: "bg-good", warn: "bg-warn", bad: "bg-bad" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
      <div
        className={cn("h-full rounded-full transition-[width] duration-500", colour)}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

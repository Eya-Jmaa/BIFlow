"use client";

import { cn } from "@/lib/utils";

/**
 * BIFlow design-system primitives.
 *
 * Every page composes from these. Nothing here encodes page-specific
 * behaviour, and no page should re-style a surface, badge or table locally —
 * that is how spacing and type drift apart between screens.
 */

/* ── Surfaces ──────────────────────────────────────────────────── */

export function Panel({
  className,
  interactive,
  inset,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean; inset?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-card border border-line bg-surface shadow-card",
        inset ? "p-0" : "p-5",
        interactive &&
          "transition-[box-shadow,transform,border-color] duration-[--duration-fast] ease-[--ease-out-soft] hover:-translate-y-px hover:border-line-strong hover:shadow-lift",
        className,
      )}
      {...props}
    />
  );
}

export function PanelHeader({
  title,
  subtitle,
  action,
  icon,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        {icon && (
          <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h2 className="truncate text-[0.9375rem] font-semibold tracking-tight text-ink">
            {title}
          </h2>
          {subtitle && (
            <p className="mt-0.5 text-[0.8125rem] leading-snug text-ink-muted">{subtitle}</p>
          )}
        </div>
      </div>
      {action && (
        <div className="flex shrink-0 items-center gap-2 overflow-x-auto sm:overflow-visible">
          {action}
        </div>
      )}
    </div>
  );
}

/** Small uppercase label above a group of controls or fields. */
export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p
      className={cn(
        "text-[0.625rem] font-semibold tracking-[0.14em] text-ink-faint uppercase",
        className,
      )}
    >
      {children}
    </p>
  );
}

/* ── Status ────────────────────────────────────────────────────── */

export type Tone = "neutral" | "brand" | "good" | "warn" | "bad" | "info";

const TONE_CHIP: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-soft ring-line-strong/70",
  brand: "bg-brand-soft text-brand-strong ring-brand-line",
  good: "bg-good-soft text-good ring-good/25",
  warn: "bg-warn-soft text-warn ring-warn/25",
  bad: "bg-bad-soft text-bad ring-bad/25",
  info: "bg-info-soft text-info ring-info/25",
};

const TONE_DOT: Record<Tone, string> = {
  neutral: "text-ink-faint",
  brand: "text-brand",
  good: "text-good",
  warn: "text-warn",
  bad: "text-bad",
  info: "text-info",
};

export function Badge({
  children,
  tone = "neutral",
  dot,
  pulse,
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.6875rem] font-medium whitespace-nowrap ring-1 ring-inset",
        TONE_CHIP[tone],
        className,
      )}
    >
      {dot && <StatusDot tone={tone} pulse={pulse} />}
      {children}
    </span>
  );
}

/**
 * A state indicator. `pulse` is reserved for work actually in progress — a
 * dot that always pulses stops meaning anything.
 */
export function StatusDot({
  tone = "neutral",
  pulse,
  className,
}: {
  tone?: Tone;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-block size-1.5 shrink-0 rounded-full bg-current",
        TONE_DOT[tone],
        pulse && "bf-pulse",
        className,
      )}
      aria-hidden
    />
  );
}

/** Maps a backend status string to a tone. One definition, used everywhere. */
export function statusTone(status: string | null | undefined): Tone {
  const value = (status || "").toLowerCase();
  if (["completed", "computed", "valid", "ready", "published", "ok", "low", "healthy"].includes(value))
    return "good";
  if (["running", "queued", "pending", "in_progress"].includes(value)) return "brand";
  if (["failed", "invalid", "error", "high", "critical", "rejected"].includes(value)) return "bad";
  if (["warning", "warn", "open", "medium", "audited_with_issues", "review"].includes(value))
    return "warn";
  return "neutral";
}

/* ── Controls ──────────────────────────────────────────────────── */

const BUTTON_VARIANT = {
  primary:
    "bg-brand text-white shadow-sm hover:bg-brand-strong active:translate-y-px disabled:hover:bg-brand",
  secondary:
    "bg-surface text-ink-soft ring-1 ring-inset ring-line-strong hover:bg-sunken hover:text-ink active:translate-y-px",
  ghost: "text-ink-muted hover:bg-sunken hover:text-ink",
  danger: "bg-bad-soft text-bad ring-1 ring-inset ring-bad/25 hover:bg-bad hover:text-white",
} as const;

const BUTTON_SIZE = {
  sm: "h-8 gap-1.5 px-3 text-[0.8125rem]",
  md: "h-9 gap-2 px-4 text-sm",
  lg: "h-10 gap-2 px-5 text-sm",
  icon: "size-9",
  "icon-sm": "size-8",
} as const;

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: React.ComponentProps<"button"> & {
  variant?: keyof typeof BUTTON_VARIANT;
  size?: keyof typeof BUTTON_SIZE;
}) {
  return (
    <button
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg font-medium whitespace-nowrap",
        "transition-[background-color,color,box-shadow,transform] duration-[--duration-fast] ease-[--ease-out-soft]",
        "disabled:pointer-events-none disabled:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
        BUTTON_VARIANT[variant],
        BUTTON_SIZE[size],
        className,
      )}
      {...props}
    />
  );
}

/** Segmented control option. Used for chart/table, filters, view switches. */
export function Segment({
  active,
  className,
  ...props
}: React.ComponentProps<"button"> & { active?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium",
        "transition-[background-color,color,box-shadow] duration-[--duration-fast] ease-[--ease-out-soft]",
        active ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-ink-muted hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}

export function SegmentGroup({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("inline-flex max-w-full shrink-0 overflow-x-auto rounded-lg bg-inset p-0.5", className)}>
      {children}
    </div>
  );
}

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink",
        "transition-[border-color,box-shadow] duration-[--duration-fast]",
        "placeholder:text-ink-faint focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "w-full resize-y rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm leading-relaxed text-ink",
        "transition-[border-color,box-shadow] duration-[--duration-fast]",
        "placeholder:text-ink-faint focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink-soft",
        "transition-[border-color] duration-[--duration-fast] focus:border-brand focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

/* ── Tables ────────────────────────────────────────────────────── */

export function DataTable({
  head,
  children,
  className,
  sticky,
}: {
  head: React.ReactNode[];
  children: React.ReactNode;
  className?: string;
  sticky?: boolean;
}) {
  return (
    <div className={cn("-mx-1 overflow-x-auto px-1", className)}>
      <table className="w-full text-left text-[0.8125rem]">
        <thead className={cn(sticky && "sticky top-0 z-10 bg-surface")}>
          <tr className="border-b border-line">
            {head.map((cell, index) => (
              <th
                key={index}
                className="pr-4 pb-2.5 text-[0.625rem] font-semibold tracking-[0.1em] text-ink-faint uppercase last:pr-0"
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

export function Tr({
  children,
  className,
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        "transition-colors duration-[--duration-fast]",
        onClick && "cursor-pointer",
        "hover:bg-sunken/70",
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function Td({
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
        "py-2.5 pr-4 align-middle text-ink-soft last:pr-0",
        numeric && "tnum text-right text-ink",
        className,
      )}
    >
      {children}
    </td>
  );
}

/* ── Field display ─────────────────────────────────────────────── */

export function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-[0.625rem] font-semibold tracking-[0.1em] text-ink-faint uppercase">
        {label}
      </dt>
      <dd className="mt-1 text-[0.8125rem] leading-snug break-words text-ink-soft">{children}</dd>
    </div>
  );
}

export function Code({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <pre
      className={cn(
        // Wrap rather than scroll: a long SQL statement in a narrow drawer is
        // unreadable behind a horizontal scrollbar.
        "overflow-auto rounded-lg border border-line bg-inset p-3 font-mono text-[0.6875rem] leading-relaxed break-words whitespace-pre-wrap text-ink-soft",
        className,
      )}
    >
      {children}
    </pre>
  );
}

/** Thin progress meter for anything naturally on a 0–100 scale. */
export function Meter({
  value,
  tone = "brand",
  className,
}: {
  value: number;
  tone?: Tone;
  className?: string;
}) {
  const fill = {
    neutral: "bg-ink-faint",
    brand: "bg-brand",
    good: "bg-good",
    warn: "bg-warn",
    bad: "bg-bad",
    info: "bg-info",
  }[tone];
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-inset", className)}>
      <div
        className={cn("h-full rounded-full transition-[width] duration-[--duration-slow] ease-[--ease-out-soft]", fill)}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

/* ── States ────────────────────────────────────────────────────── */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("bf-skeleton rounded-lg", className)} />;
}

export function EmptyState({
  title,
  message,
  action,
  icon,
  visual,
  className,
}: {
  title: string;
  message?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  visual?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-card border border-dashed border-line-strong bg-sunken/50 px-6 py-12 text-center",
        className,
      )}
    >
      {visual}
      {!visual && icon && (
        <span className="mb-3 grid size-11 place-items-center rounded-xl bg-surface text-ink-faint shadow-card">
          {icon}
        </span>
      )}
      <p className="text-sm font-medium text-ink">{title}</p>
      {message && <p className="mt-1.5 max-w-md text-[0.8125rem] leading-relaxed text-ink-muted">{message}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/**
 * Errors name what failed and offer the next action. "Something went wrong"
 * tells a user nothing they can act on.
 */
export function ErrorState({
  title,
  reason,
  action,
  className,
}: {
  title: string;
  reason?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-card border border-bad/20 bg-bad-soft/50 p-5", className)}>
      <div className="flex items-start gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-bad-soft text-bad">
          <svg viewBox="0 0 16 16" className="size-4" fill="currentColor" aria-hidden>
            <path d="M8 1.5 15 14H1L8 1.5Zm0 4.2a.7.7 0 0 0-.7.7v3a.7.7 0 0 0 1.4 0v-3a.7.7 0 0 0-.7-.7Zm0 5.6a.85.85 0 1 0 0 1.7.85.85 0 0 0 0-1.7Z" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[0.875rem] font-medium text-ink">{title}</p>
          {reason && (
            <p className="mt-1 text-[0.8125rem] leading-relaxed break-words text-ink-muted">
              {reason}
            </p>
          )}
          {action && <div className="mt-3 flex flex-wrap gap-2">{action}</div>}
        </div>
      </div>
    </div>
  );
}

/** A feature with no backend behind it yet. Honest, not a fake screen. */
export function ComingState({
  title,
  message,
  icon,
}: {
  title: string;
  message: string;
  icon?: React.ReactNode;
}) {
  return (
    <EmptyState
      title={title}
      message={message}
      icon={icon}
      action={<Badge tone="neutral">Not yet implemented</Badge>}
    />
  );
}

/* ── Tooltip ───────────────────────────────────────────────────── */

/** CSS-only tooltip: no portal, no layout cost until hover/focus. */
export function Tooltip({
  label,
  children,
  side = "top",
  className,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom";
  className?: string;
}) {
  return (
    <span className={cn("group/tt relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute left-1/2 z-50 w-max max-w-64 -translate-x-1/2 rounded-lg border border-line bg-raised px-2.5 py-1.5 text-[0.6875rem] leading-snug text-ink-soft opacity-0 shadow-lift",
          "transition-opacity duration-[--duration-fast] group-focus-within/tt:opacity-100 group-hover/tt:opacity-100",
          side === "top" ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]",
        )}
      >
        {label}
      </span>
    </span>
  );
}

import { cn } from "@/lib/utils";

/**
 * Status pills.
 *
 * Status colours are reserved for state and never reused as a chart series
 * colour, and each pill carries its own text — colour never has to be read on
 * its own.
 */
const tones = {
  success: "bg-good-soft text-good ring-good/20",
  warning: "bg-warn-soft text-warn ring-warn/20",
  error: "bg-bad-soft text-bad ring-bad/20",
  brand: "bg-brand-soft text-brand-strong ring-brand/20",
  neutral: "bg-surface-sunken text-ink-soft ring-line-strong/60",
} as const;

export type Tone = keyof typeof tones;

export function Badge({
  children,
  tone = "neutral",
  dot,
  className,
}: {
  children: React.ReactNode;
  tone?: Tone | string;
  dot?: boolean;
  className?: string;
}) {
  const key = (tone in tones ? tone : "neutral") as Tone;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.6875rem] font-medium ring-1 ring-inset",
        tones[key],
        className,
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}

/** Maps a backend status string onto a tone. */
export function statusTone(status: string | null | undefined): Tone {
  const value = (status || "").toLowerCase();
  if (["completed", "computed", "valid", "ready", "published", "low", "ok"].includes(value)) {
    return "success";
  }
  if (["running", "queued", "pending", "in_progress"].includes(value)) return "brand";
  if (["failed", "invalid", "error", "high", "critical", "rejected"].includes(value)) return "error";
  if (["warning", "open", "medium", "audited_with_issues"].includes(value)) return "warning";
  return "neutral";
}

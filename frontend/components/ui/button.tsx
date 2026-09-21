import { cn } from "@/lib/utils";

/**
 * Buttons.
 *
 * Replaces a generated shadcn component whose variant matrix was ~40 lines of
 * class strings for the three variants this app actually uses.
 */
const variants = {
  primary:
    "bg-brand text-white shadow-sm hover:bg-brand-strong active:translate-y-px disabled:hover:bg-brand",
  secondary:
    "bg-surface text-ink-soft ring-1 ring-inset ring-line-strong hover:bg-surface-muted hover:text-ink active:translate-y-px",
  ghost: "text-ink-muted hover:bg-surface-sunken hover:text-ink",
  danger: "bg-bad-soft text-bad ring-1 ring-inset ring-bad/20 hover:bg-bad hover:text-white",
} as const;

const sizes = {
  sm: "h-8 gap-1.5 px-3 text-[0.8125rem]",
  md: "h-9 gap-2 px-4 text-sm",
  icon: "size-9",
} as const;

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: React.ComponentProps<"button"> & {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
}) {
  return (
    <button
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg font-medium whitespace-nowrap transition-colors duration-150",
        "disabled:pointer-events-none disabled:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}

/** A small segmented control, used for chart/table and filter toggles. */
export function Toggle({
  active,
  className,
  ...props
}: React.ComponentProps<"button"> & { active?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors duration-150",
        active
          ? "bg-surface text-ink shadow-sm ring-1 ring-line-strong"
          : "text-ink-muted hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}

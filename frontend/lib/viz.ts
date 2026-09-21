/**
 * Visualization tokens and value formatting.
 *
 * The categorical slots are a validated set: assigned in fixed order, never
 * cycled and never reassigned by rank, so a series that survives a filter keeps
 * its colour. Validated against this app's dark chart surface (#0b1220) for the
 * lightness band, chroma floor, colour-vision separation and contrast.
 */

export const SURFACE = "#0b1220";

/** Categorical identity. Assign in order; fold a 9th series into "Other". */
export const SERIES = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
] as const;

/** Reserved for state. Never used as "series 5", always paired with a label. */
export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
} as const;

export const CHROME = {
  grid: "#1e293b",
  axis: "#334155",
  tick: "#94a3b8",
  tooltipBg: "#0b1220",
  tooltipBorder: "#1e293b",
};

export type ValueFormat = {
  style?: "currency" | "percent" | "integer" | "decimal";
  decimals?: number;
};

/**
 * Format a metric value for display.
 *
 * Compact notation is used on axes and tiles, where "9.7M" is read faster than
 * the full figure; the tooltip and table view always carry the exact number, so
 * no value is only ever available rounded.
 */
export function formatValue(
  value: number | null | undefined,
  format: ValueFormat = {},
  options: { compact?: boolean; unit?: string | null } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const style = format.style ?? inferStyle(options.unit);
  const compact = options.compact && Math.abs(value) >= 10_000;

  if (style === "percent") {
    return `${value.toFixed(format.decimals ?? 1)}%`;
  }
  const decimals = format.decimals ?? (style === "integer" ? 0 : 2);
  const formatted = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: compact ? 1 : decimals,
    minimumFractionDigits: compact ? 0 : Math.min(decimals, 2),
    notation: compact ? "compact" : "standard",
  }).format(value);
  return style === "currency" ? `£${formatted}` : formatted;
}

function inferStyle(unit?: string | null): ValueFormat["style"] {
  if (unit === "currency") return "currency";
  if (unit === "percent") return "percent";
  if (unit === "count" || unit === "units") return "integer";
  return "decimal";
}

/** Delta direction, carrying an icon and label so colour is never the only cue. */
export function deltaTone(
  changePct: number | null | undefined,
  higherIsBetter: boolean | null = true,
): { color: string; arrow: string; label: string } | null {
  if (changePct === null || changePct === undefined || Number.isNaN(changePct)) return null;
  const rising = changePct >= 0;
  const arrow = rising ? "▲" : "▼";
  const label = rising ? "up" : "down";
  if (higherIsBetter === null) return { color: CHROME.tick, arrow, label };
  const favourable = rising === higherIsBetter;
  return { color: favourable ? STATUS.good : STATUS.critical, arrow, label };
}

/** Shorten a period label for an axis tick without losing the year. */
export function shortPeriod(period: string): string {
  const parsed = new Date(period);
  if (Number.isNaN(parsed.getTime())) return period;
  return parsed.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

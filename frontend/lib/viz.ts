/**
 * Visualization tokens and value formatting.
 *
 * The categorical slots are a validated set for this app's light chart surface
 * (white cards): they clear the lightness band, chroma floor and
 * colour-vision separation checks. Assign them in fixed order, never cycled,
 * and never reassign by rank — a series that survives a filter keeps its
 * colour, or a reader who learned "UK is blue" is misled.
 *
 * Slots 3 and 4 fall below 3:1 contrast against white. That is permitted only
 * because every chart here also ships a table view; do not drop the table
 * toggle without re-checking the palette.
 */

export const SURFACE = "#ffffff";

export const SERIES = [
  "#2a78d6", // blue
  "#eb6834", // orange
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#e87ba4", // magenta
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
] as const;

/** Reserved for state. Never used as "series 5", always paired with a label. */
export const STATUS = {
  good: "#12a150",
  warn: "#d98500",
  bad: "#d93b4b",
} as const;

/** Chart chrome stays recessive: hairline solid grid, no dashes. */
export const CHROME = {
  grid: "#eef0f8",
  axis: "#e0e3ef",
  tick: "#7c81a0",
  surface: "#ffffff",
  border: "#e6e8f4",
};

/**
 * The dataset determines the currency; the pipeline only records that a
 * measure *is* money. Change this one constant to match your data.
 */
export const CURRENCY_SYMBOL = "£";

export type ValueFormat = {
  style?: "currency" | "percent" | "integer" | "decimal";
  decimals?: number;
};

/**
 * Format a metric for display.
 *
 * Compact notation is used on axes and tiles, where "9.7M" reads faster than
 * the full figure. Tooltips and table views always carry the exact number, so
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

  if (style === "percent") return `${value.toFixed(format.decimals ?? 1)}%`;

  const decimals = format.decimals ?? (style === "integer" ? 0 : 2);
  const formatted = new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: compact ? 1 : decimals,
    minimumFractionDigits: compact ? 0 : Math.min(decimals, 2),
    notation: compact ? "compact" : "standard",
  }).format(value);

  // en-GB renders compact suffixes lowercase ("9.7m"); finance writes "9.7M".
  const cased = compact ? formatted.replace(/[a-z]$/, (suffix) => suffix.toUpperCase()) : formatted;
  return style === "currency" ? `${CURRENCY_SYMBOL}${cased}` : cased;
}

function inferStyle(unit?: string | null): ValueFormat["style"] {
  if (unit === "currency") return "currency";
  if (unit === "percent") return "percent";
  if (unit === "count" || unit === "units") return "integer";
  return "decimal";
}

/** Direction plus a word, so a delta never rests on colour alone. */
export function deltaOf(
  changePct: number | null | undefined,
  higherIsBetter: boolean | null = true,
): { value: string; direction: "up" | "down" | "flat"; favourable: boolean | null } | null {
  if (changePct === null || changePct === undefined || Number.isNaN(changePct)) return null;
  const direction = changePct > 0.0005 ? "up" : changePct < -0.0005 ? "down" : "flat";
  return {
    value: `${Math.abs(changePct * 100).toFixed(1)}%`,
    direction,
    favourable:
      higherIsBetter === null || direction === "flat" ? null : (direction === "up") === higherIsBetter,
  };
}

/** Shorten a period label for an axis tick without losing the year. */
export function shortPeriod(period: string): string {
  const parsed = new Date(period);
  if (Number.isNaN(parsed.getTime())) return period;
  return parsed.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

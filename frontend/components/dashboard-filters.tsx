"use client";

import { useMemo, useState } from "react";
import { Calendar, Check, ChevronDown, Filter, Loader2, X } from "lucide-react";

import { Toggle } from "@/components/ui/button";
import type { DashboardFilter, FilterDimension } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * One filter row, above everything it scopes.
 *
 * Every chart and tile below re-renders against this same slice, so the
 * numbers on the page always agree with each other. Filters never live inside
 * an individual chart card.
 */

export type FilterState = {
  from: string | null;
  to: string | null;
  dimension: string | null;
  values: string[];
  grain: string;
};

export const EMPTY_FILTERS: FilterState = {
  from: null,
  to: null,
  dimension: null,
  values: [],
  grain: "month",
};

// Presets before a custom range: nobody fights a calendar grid for "last 90 days".
const PRESETS = [
  { label: "All time", months: null },
  { label: "3 months", months: 3 },
  { label: "6 months", months: 6 },
  { label: "12 months", months: 12 },
] as const;

export function buildFilters(state: FilterState, dateColumn: string | null): DashboardFilter[] {
  const filters: DashboardFilter[] = [];
  if (dateColumn && state.from && state.to) {
    filters.push({ column: dateColumn, op: "between", values: [state.from, state.to] });
  }
  if (state.dimension && state.values.length > 0) {
    filters.push({ column: state.dimension, op: "in", values: state.values });
  }
  return filters;
}

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

export function DashboardFilters({
  dimensions,
  state,
  onChange,
  busy,
}: {
  dimensions: FilterDimension[];
  state: FilterState;
  onChange: (next: FilterState) => void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);

  const dateDimension = useMemo(
    () => dimensions.find((dimension) => dimension.type === "datetime") ?? null,
    [dimensions],
  );
  const categorical = useMemo(
    () =>
      dimensions.filter(
        (dimension) => dimension.type !== "datetime" && (dimension.values?.length ?? 0) > 0,
      ),
    [dimensions],
  );
  const active = categorical.find((item) => item.name === state.dimension) ?? categorical[0] ?? null;

  const applyPreset = (months: number | null) => {
    if (!dateDimension?.max) return;
    if (months === null) {
      onChange({ ...state, from: null, to: null });
      return;
    }
    const end = new Date(dateDimension.max);
    const start = new Date(end);
    start.setMonth(start.getMonth() - months);
    onChange({ ...state, from: isoDate(start), to: isoDate(end) });
  };

  const activePreset = (() => {
    if (!state.from || !state.to) return "All time";
    if (!dateDimension?.max) return "Custom";
    const end = new Date(dateDimension.max);
    for (const preset of PRESETS) {
      if (preset.months === null) continue;
      const start = new Date(end);
      start.setMonth(start.getMonth() - preset.months);
      if (isoDate(start) === state.from) return preset.label;
    }
    return "Custom";
  })();

  const toggleValue = (value: string) => {
    const next = state.values.includes(value)
      ? state.values.filter((item) => item !== value)
      : [...state.values, value];
    onChange({ ...state, dimension: active?.name ?? null, values: next });
  };

  const hasFilters = Boolean(state.from) || state.values.length > 0;

  return (
    <div className="rounded-card border border-line bg-surface shadow-card">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 p-3">
        {dateDimension && (
          <div className="flex items-center gap-2">
            <Calendar className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
            <div className="flex rounded-lg bg-surface-sunken p-0.5">
              {PRESETS.map((preset) => (
                <Toggle
                  key={preset.label}
                  active={activePreset === preset.label}
                  onClick={() => applyPreset(preset.months)}
                >
                  {activePreset === preset.label && <Check className="size-3" aria-hidden />}
                  {preset.label}
                </Toggle>
              ))}
            </div>
          </div>
        )}

        <label className="flex items-center gap-2">
          <span className="text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase">
            Grain
          </span>
          <select
            value={state.grain}
            onChange={(event) => onChange({ ...state, grain: event.target.value })}
            className="rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink-soft focus:border-brand"
          >
            {(dateDimension?.grains ?? ["month"]).map((grain) => (
              <option key={grain} value={grain}>
                {grain}
              </option>
            ))}
          </select>
        </label>

        {active && (
          <div className="flex items-center gap-2">
            <Filter className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
            <select
              value={active.name}
              onChange={(event) => onChange({ ...state, dimension: event.target.value, values: [] })}
              className="rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink-soft focus:border-brand"
            >
              {categorical.map((dimension) => (
                <option key={dimension.name} value={dimension.name}>
                  {dimension.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors",
                state.values.length
                  ? "border-brand/25 bg-brand-soft text-brand-strong"
                  : "border-line-strong text-ink-muted hover:bg-surface-muted",
              )}
            >
              {state.values.length ? `${state.values.length} selected` : "All values"}
              <ChevronDown
                className={cn("size-3 transition-transform", open && "rotate-180")}
                aria-hidden
              />
            </button>
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {busy && (
            <span className="flex items-center gap-1.5 text-xs text-ink-muted">
              <Loader2 className="size-3 animate-spin text-brand" aria-hidden />
              Updating
            </span>
          )}
          {hasFilters && (
            <button
              type="button"
              onClick={() => onChange({ ...EMPTY_FILTERS, grain: state.grain })}
              className="inline-flex items-center gap-1 text-xs text-ink-muted transition-colors hover:text-ink"
            >
              <X className="size-3" aria-hidden />
              Clear
            </button>
          )}
        </div>
      </div>

      {open && active && (
        <div className="max-h-52 overflow-auto border-t border-line p-3">
          <div className="flex flex-wrap gap-1.5">
            {(active.values ?? []).map((value) => {
              const selected = state.values.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggleValue(value)}
                  aria-pressed={selected}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition-colors",
                    selected
                      ? "bg-brand text-white"
                      : "bg-surface-sunken text-ink-soft hover:bg-line",
                  )}
                >
                  {selected && <Check className="size-3" aria-hidden />}
                  {value}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

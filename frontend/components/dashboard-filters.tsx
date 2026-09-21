"use client";

import { useMemo, useState } from "react";
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

const PRESETS = [
  { label: "All time", months: null },
  { label: "Last 3 months", months: 3 },
  { label: "Last 6 months", months: 6 },
  { label: "Last 12 months", months: 12 },
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
    () => dimensions.find((d) => d.type === "datetime") ?? null,
    [dimensions],
  );
  const categorical = useMemo(
    () => dimensions.filter((d) => d.type !== "datetime" && (d.values?.length ?? 0) > 0),
    [dimensions],
  );
  const active = categorical.find((d) => d.name === state.dimension) ?? categorical[0] ?? null;

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
      ? state.values.filter((v) => v !== value)
      : [...state.values, value];
    onChange({ ...state, dimension: active?.name ?? null, values: next });
  };

  const hasFilters = Boolean(state.from) || state.values.length > 0;

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 p-3">
        {dateDimension && (
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] uppercase tracking-wide text-slate-500">Period</span>
            <div className="flex flex-wrap gap-1">
              {PRESETS.map((preset) => {
                const selected = activePreset === preset.label;
                return (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => applyPreset(preset.months)}
                    aria-pressed={selected}
                    className={cn(
                      "rounded border px-2 py-1 text-xs transition-colors",
                      selected
                        ? "border-blue-700 bg-blue-950 text-blue-200"
                        : "border-slate-800 text-slate-400 hover:bg-slate-900",
                    )}
                  >
                    {selected && <span className="mr-1 font-bold">✓</span>}
                    {preset.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-slate-500">Grain</span>
          <select
            value={state.grain}
            onChange={(event) => onChange({ ...state, grain: event.target.value })}
            className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300"
          >
            {(dateDimension?.grains ?? ["month"]).map((grain) => (
              <option key={grain} value={grain}>
                {grain}
              </option>
            ))}
          </select>
        </div>

        {active && (
          <div className="flex items-center gap-1.5">
            <select
              value={active.name}
              onChange={(event) =>
                onChange({ ...state, dimension: event.target.value, values: [] })
              }
              className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300"
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
              className="rounded border border-slate-800 px-2 py-1 text-xs text-slate-400 hover:bg-slate-900"
            >
              {state.values.length ? `${state.values.length} selected` : "All values"}
              <span className="ml-1 text-slate-600">{open ? "▴" : "▾"}</span>
            </button>
          </div>
        )}

        {hasFilters && (
          <button
            type="button"
            onClick={() => onChange({ ...EMPTY_FILTERS, grain: state.grain })}
            className="text-xs text-slate-500 underline-offset-2 hover:text-slate-300 hover:underline"
          >
            Clear
          </button>
        )}

        {busy && <span className="text-xs text-slate-500">Updating…</span>}
      </div>

      {open && active && (
        <div className="max-h-48 overflow-auto border-t border-slate-800 p-3">
          <div className="flex flex-wrap gap-1">
            {(active.values ?? []).map((value) => {
              const selected = state.values.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggleValue(value)}
                  aria-pressed={selected}
                  className={cn(
                    "rounded border px-2 py-1 text-xs transition-colors",
                    selected
                      ? "border-blue-700 bg-blue-950 text-blue-200"
                      : "border-slate-800 text-slate-400 hover:bg-slate-900",
                  )}
                >
                  {selected && <span className="mr-1 font-bold">✓</span>}
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

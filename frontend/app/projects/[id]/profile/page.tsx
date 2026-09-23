"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Gauge, ShieldAlert } from "lucide-react";

import {
  Badge,
  DataTable,
  EmptyState,
  Eyebrow,
  Field,
  Panel,
  PanelHeader,
  Segment,
  SegmentGroup,
  Skeleton,
  Td,
  Tooltip,
  Tr,
  statusTone,
} from "@/components/ui/primitives";
import { FrequencyBars, QuantileStrip, ShareBar } from "@/components/ui/charts";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

/**
 * Data profiling.
 *
 * Every figure comes from `/profile`, which the Data Profiler writes. The
 * per-column charts are drawn from the statistics the profiler actually
 * computed — quantiles for numerics, top values for categoricals — rather than
 * a histogram the backend never produced.
 */

type TypeInference = {
  action: string;
  target_type: string | null;
  format: string | null;
  parse_rate: number | null;
  reason: string;
  warnings: string[];
  rejected: { format: string; parse_rate: number }[];
};

type Column = {
  name: string;
  inferred_type: string;
  logical_type: string;
  null_pct: number;
  distinct_count: number;
  uniqueness_pct: number;
  is_candidate_pk: boolean;
  semantic_hint: string | null;
  warnings: string[];
  stats: {
    mean?: number | null;
    std?: number | null;
    min?: number | null;
    max?: number | null;
    median?: number | null;
    q25?: number | null;
    q75?: number | null;
    outlier_count_iqr?: number;
    top_values?: { value: string; count: number }[];
    min_date?: string;
    max_date?: string;
    granularity?: string;
    type_inference?: TypeInference;
  };
};

type Profile = {
  id: string;
  dataset: string;
  table_name: string;
  row_count: number;
  column_count: number;
  quality_score: number | null;
  duplicate_row_count: number;
  warnings: string[];
  pii_flags: { column: string; kind: string }[];
  columns: Column[];
};

const TYPE_TONE: Record<string, string> = {
  datetime: "bg-info-soft text-info",
  currency: "bg-good-soft text-good",
  quantity: "bg-good-soft text-good",
  numeric: "bg-sunken text-ink-soft",
  categorical: "bg-brand-soft text-brand-strong",
  geo: "bg-warn-soft text-warn",
  identifier: "bg-sunken text-ink-soft",
  text: "bg-sunken text-ink-soft",
  email: "bg-warn-soft text-warn",
};

export default function ProfilePage() {
  const { id } = useParams<{ id: string }>();
  const [filter, setFilter] = useState<"all" | "issues" | "measures" | "dimensions">("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  const profiles = useQuery({
    queryKey: ["profile", id],
    queryFn: () => api.profile(id) as Promise<Profile[]>,
    retry: false,
  });

  if (profiles.isLoading) return <LoadingProfile />;

  if (profiles.isError || !profiles.data?.length) {
    return (
      <EmptyState
        title="No profile yet"
        message="Upload a dataset and run the pipeline. The Data Profiler reads every column and records its types, missingness, cardinality and distribution."
        icon={<Gauge className="size-5" />}
      />
    );
  }

  return (
    <div className="space-y-4">
      {profiles.data.map((profile) => (
        <ProfileTable
          key={profile.id}
          profile={profile}
          filter={filter}
          setFilter={setFilter}
          expanded={expanded}
          setExpanded={setExpanded}
        />
      ))}
    </div>
  );
}

function ProfileTable({
  profile,
  filter,
  setFilter,
  expanded,
  setExpanded,
}: {
  profile: Profile;
  filter: "all" | "issues" | "measures" | "dimensions";
  setFilter: (value: "all" | "issues" | "measures" | "dimensions") => void;
  expanded: string | null;
  setExpanded: (value: string | null) => void;
}) {
  const nullRate = useMemo(() => {
    if (!profile.columns.length) return 0;
    return profile.columns.reduce((sum, column) => sum + column.null_pct, 0) / profile.columns.length;
  }, [profile.columns]);

  const columns = useMemo(() => {
    if (filter === "issues") {
      return profile.columns.filter(
        (column) => column.warnings.length > 0 || column.null_pct > 5 || column.stats.outlier_count_iqr,
      );
    }
    if (filter === "measures") {
      return profile.columns.filter((column) =>
        ["currency", "quantity", "numeric"].includes(column.logical_type),
      );
    }
    if (filter === "dimensions") {
      return profile.columns.filter((column) =>
        ["datetime", "categorical", "geo"].includes(column.logical_type),
      );
    }
    return profile.columns;
  }, [profile.columns, filter]);

  const duplicateRate = profile.row_count ? (profile.duplicate_row_count / profile.row_count) * 100 : 0;

  return (
    <>
      {/* Dataset overview */}
      <Panel>
        <PanelHeader
          title={profile.table_name}
          subtitle="Dataset overview, as read by the Data Profiler"
          icon={<Gauge className="size-4" />}
          action={
            profile.quality_score != null && (
              <Badge tone={statusTone(profile.quality_score >= 85 ? "valid" : "warning")}>
                profile score {profile.quality_score.toFixed(1)}
              </Badge>
            )
          }
        />

        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Rows" value={profile.row_count.toLocaleString("en-GB")} />
          <Stat label="Columns" value={String(profile.column_count)} />
          <Stat label="Mean null rate" value={`${nullRate.toFixed(2)}%`} bar={100 - nullRate} tone={nullRate < 5 ? "good" : "warn"} />
          <Stat
            label="Duplicate rows"
            value={profile.duplicate_row_count.toLocaleString("en-GB")}
            hint={`${duplicateRate.toFixed(2)}% of rows`}
          />
          <Stat label="PII flags" value={String(profile.pii_flags.length)} tone={profile.pii_flags.length ? "warn" : "good"} />
          <Stat
            label="Typed columns"
            value={`${profile.columns.filter((c) => c.stats.type_inference?.action !== "keep" || c.inferred_type !== "String").length}/${profile.column_count}`}
          />
        </dl>

        {profile.warnings.length > 0 && (
          <ul className="mt-5 space-y-1.5 border-t border-line pt-4">
            {profile.warnings.map((warning, index) => (
              <li key={index} className="flex gap-2 text-[0.75rem] leading-snug text-ink-muted">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" aria-hidden />
                {warning}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {/* Column table */}
      <Panel>
        <PanelHeader
          title="Columns"
          subtitle={`${columns.length} of ${profile.column_count} shown — select a row for its full profile`}
          action={
            <SegmentGroup>
              <Segment active={filter === "all"} onClick={() => setFilter("all")}>
                All
              </Segment>
              <Segment active={filter === "dimensions"} onClick={() => setFilter("dimensions")}>
                Dimensions
              </Segment>
              <Segment active={filter === "measures"} onClick={() => setFilter("measures")}>
                Measures
              </Segment>
              <Segment active={filter === "issues"} onClick={() => setFilter("issues")}>
                Needs review
              </Segment>
            </SegmentGroup>
          }
        />

        <DataTable
          head={[
            "Column",
            "Type",
            <span key="n" className="block text-right">Null %</span>,
            <span key="u" className="block text-right">Unique</span>,
            "Distribution",
            "Semantic role",
            "",
          ]}
        >
          {columns.map((column) => {
            const open = expanded === column.name;
            const needsReview = column.warnings.length > 0 || column.null_pct > 5;
            return (
              <>
                <Tr
                  key={column.name}
                  onClick={() => setExpanded(open ? null : column.name)}
                  className={cn(open && "bg-sunken")}
                >
                  <Td className="font-mono text-[0.75rem] font-medium text-ink">{column.name}</Td>
                  <Td>
                    <span
                      className={cn(
                        "inline-block rounded px-1.5 py-0.5 text-[0.625rem] font-medium",
                        TYPE_TONE[column.logical_type] ?? "bg-sunken text-ink-soft",
                      )}
                    >
                      {column.logical_type}
                    </span>
                  </Td>
                  <Td numeric className={column.null_pct > 20 ? "text-warn" : undefined}>
                    {column.null_pct.toFixed(2)}
                  </Td>
                  <Td numeric>{column.distinct_count.toLocaleString("en-GB")}</Td>
                  <Td className="w-40">
                    <MiniDistribution column={column} />
                  </Td>
                  <Td className="text-[0.75rem]">{column.semantic_hint ?? "—"}</Td>
                  <Td>
                    {needsReview && (
                      <Tooltip label={column.warnings[0] ?? "High missingness"}>
                        <ShieldAlert className="size-3.5 text-warn" aria-hidden />
                      </Tooltip>
                    )}
                  </Td>
                </Tr>
                {open && (
                  <tr key={`${column.name}-detail`}>
                    <td colSpan={7} className="bg-sunken/60 px-0 pb-4">
                      <ColumnDetail column={column} rows={profile.row_count} />
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </DataTable>
      </Panel>
    </>
  );
}

function Stat({
  label,
  value,
  hint,
  bar,
  tone = "brand",
}: {
  label: string;
  value: string;
  hint?: string;
  bar?: number;
  tone?: "brand" | "good" | "warn" | "bad";
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.625rem] tracking-[0.1em] text-ink-faint uppercase">{label}</dt>
      <dd className="tnum mt-1 text-lg font-semibold tracking-tight text-ink">{value}</dd>
      {bar !== undefined && <ShareBar value={bar} tone={tone} className="mt-1.5" />}
      {hint && <p className="mt-1 text-[0.625rem] text-ink-faint">{hint}</p>}
    </div>
  );
}

/** A distribution glance sized for a table cell. */
function MiniDistribution({ column }: { column: Column }) {
  const { stats } = column;
  if (stats.min != null && stats.q25 != null && stats.median != null && stats.q75 != null && stats.max != null) {
    return (
      <QuantileStrip
        min={stats.min}
        q25={stats.q25}
        median={stats.median}
        q75={stats.q75}
        max={stats.max}
      />
    );
  }
  if (stats.top_values?.length) {
    const top = stats.top_values[0];
    const total = stats.top_values.reduce((sum, item) => sum + item.count, 0);
    const share = total ? (top.count / total) * 100 : 0;
    return (
      <div className="flex items-center gap-2">
        <ShareBar value={share} tone="brand" className="w-16" />
        <span className="truncate text-[0.625rem] text-ink-faint" title={top.value}>
          {top.value}
        </span>
      </div>
    );
  }
  if (stats.min_date && stats.max_date) {
    return (
      <span className="text-[0.625rem] text-ink-faint">
        {stats.min_date.slice(0, 10)} → {stats.max_date.slice(0, 10)}
      </span>
    );
  }
  return <span className="text-[0.625rem] text-ink-faint">—</span>;
}

function ColumnDetail({ column, rows }: { column: Column; rows: number }) {
  const { stats } = column;
  const inference = stats.type_inference;

  return (
    <div className="bf-fade grid gap-5 px-4 pt-4 lg:grid-cols-3">
      <div>
        <Eyebrow>Statistics</Eyebrow>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2">
          <Field label="Storage type">{column.inferred_type}</Field>
          <Field label="Distinct">{column.distinct_count.toLocaleString("en-GB")}</Field>
          <Field label="Unique %">{column.uniqueness_pct.toFixed(2)}%</Field>
          <Field label="Nulls">
            {Math.round((column.null_pct / 100) * rows).toLocaleString("en-GB")}
          </Field>
          {stats.mean != null && <Field label="Mean">{stats.mean.toLocaleString("en-GB", { maximumFractionDigits: 2 })}</Field>}
          {stats.std != null && <Field label="Std dev">{stats.std.toLocaleString("en-GB", { maximumFractionDigits: 2 })}</Field>}
          {stats.min != null && <Field label="Min">{stats.min.toLocaleString("en-GB", { maximumFractionDigits: 2 })}</Field>}
          {stats.max != null && <Field label="Max">{stats.max.toLocaleString("en-GB", { maximumFractionDigits: 2 })}</Field>}
          {stats.outlier_count_iqr != null && (
            <Field label="IQR outliers">{stats.outlier_count_iqr.toLocaleString("en-GB")}</Field>
          )}
          {stats.granularity && <Field label="Grain">{stats.granularity}</Field>}
        </dl>
      </div>

      <div>
        <Eyebrow>{stats.top_values?.length ? "Most frequent values" : "Distribution"}</Eyebrow>
        <div className="mt-2">
          {stats.top_values?.length ? (
            <FrequencyBars
              items={stats.top_values}
              total={stats.top_values.reduce((sum, item) => sum + item.count, 0)}
              max={6}
            />
          ) : stats.min != null && stats.q25 != null && stats.median != null && stats.q75 != null && stats.max != null ? (
            <div>
              <QuantileStrip
                min={stats.min}
                q25={stats.q25}
                median={stats.median}
                q75={stats.q75}
                max={stats.max}
              />
              <div className="mt-1.5 flex justify-between text-[0.625rem] text-ink-faint tabular-nums">
                <span>{stats.min.toLocaleString("en-GB", { maximumFractionDigits: 1 })}</span>
                <span>median {stats.median.toLocaleString("en-GB", { maximumFractionDigits: 1 })}</span>
                <span>{stats.max.toLocaleString("en-GB", { maximumFractionDigits: 1 })}</span>
              </div>
            </div>
          ) : (
            <p className="text-[0.75rem] text-ink-faint">No distribution recorded for this type.</p>
          )}
        </div>
      </div>

      <div>
        <Eyebrow>Type inference</Eyebrow>
        {inference ? (
          <div className="mt-2 space-y-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone={inference.action === "keep" ? "neutral" : "good"}>
                {inference.action.replace(/_/g, " ")}
              </Badge>
              {inference.format && (
                <code className="rounded bg-inset px-1.5 py-0.5 font-mono text-[0.625rem] text-ink-soft">
                  {inference.format}
                </code>
              )}
              {inference.parse_rate != null && (
                <span className="tnum text-[0.625rem] text-ink-faint">
                  {(inference.parse_rate * 100).toFixed(2)}% parsed
                </span>
              )}
            </div>
            <p className="text-[0.75rem] leading-relaxed text-ink-muted">{inference.reason}</p>
            {inference.warnings.map((warning, index) => (
              <p key={index} className="flex gap-1.5 text-[0.75rem] leading-snug text-warn">
                <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
                {warning}
              </p>
            ))}
            {inference.rejected.length > 0 && (
              <details>
                <summary className="cursor-pointer text-[0.625rem] tracking-[0.08em] text-ink-faint uppercase">
                  Rejected candidates
                </summary>
                <ul className="mt-1.5 space-y-0.5">
                  {inference.rejected.map((item) => (
                    <li key={item.format} className="flex justify-between gap-2 font-mono text-[0.625rem] text-ink-faint">
                      <span>{item.format}</span>
                      <span className="tnum">{(item.parse_rate * 100).toFixed(1)}%</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ) : (
          <p className="mt-2 text-[0.75rem] text-ink-faint">
            No inference decision recorded for this column.
          </p>
        )}
      </div>
    </div>
  );
}

function LoadingProfile() {
  return (
    <div className="space-y-4">
      <Panel>
        <Skeleton className="mb-4 h-5 w-40" />
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index}>
              <Skeleton className="h-2.5 w-16" />
              <Skeleton className="mt-2 h-6 w-20" />
            </div>
          ))}
        </div>
      </Panel>
      <Panel>
        <Skeleton className="mb-4 h-5 w-32" />
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="mb-2 h-9 w-full" />
        ))}
      </Panel>
    </div>
  );
}

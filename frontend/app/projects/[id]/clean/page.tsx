"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ListChecks, Wand2 } from "lucide-react";

import {
  Badge,
  DataTable,
  EmptyState,
  Eyebrow,
  Meter,
  Panel,
  PanelHeader,
  Segment,
  SegmentGroup,
  Skeleton,
  Td,
  Tr,
  statusTone,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Data cleaning.
 *
 * Shows what was found, what was done about it, and what was deliberately left
 * alone. The agent only applies conservative, reversible transformations — so
 * most issues are reported with a recommendation rather than silently fixed,
 * and this page has to make that distinction obvious.
 */

type Issue = {
  id: string;
  severity: string;
  issue_type: string;
  table_name: string | null;
  column_name: string | null;
  rows_affected: number;
  detection_method: string;
  recommended_action: string;
  status: string;
  evidence: Record<string, unknown> | null;
};

type Report = {
  id: string;
  overall_score: number;
  completeness: number;
  uniqueness: number;
  consistency: number;
  validity: number;
  referential_integrity: number;
  issues: Issue[];
};

type Transformation = {
  id: string;
  operation: string;
  table_name: string;
  column_name: string | null;
  rows_affected: number;
  reason: string;
  before_example: string | null;
  after_example: string | null;
};

const AXES = [
  { key: "completeness", label: "Completeness" },
  { key: "uniqueness", label: "Uniqueness" },
  { key: "consistency", label: "Consistency" },
  { key: "validity", label: "Validity" },
  { key: "referential_integrity", label: "Referential" },
] as const;

function tone(score: number) {
  return score >= 85 ? "good" : score >= 60 ? "warn" : "bad";
}

export default function CleanPage() {
  const { id } = useParams<{ id: string }>();
  const [severity, setSeverity] = useState<"all" | "high" | "medium" | "low">("all");

  const quality = useQuery({
    queryKey: ["quality", id],
    queryFn: () => api.quality(id) as Promise<Report[]>,
    retry: false,
  });
  const transforms = useQuery({
    queryKey: ["transforms", id],
    queryFn: () => api.transformations(id) as Promise<Transformation[]>,
    retry: false,
  });

  if (quality.isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <Skeleton className="h-80" />
        <Skeleton className="h-80" />
      </div>
    );
  }

  if (quality.isError || !quality.data?.length) {
    return (
      <EmptyState
        title="Nothing cleaned yet"
        message="Run the pipeline. The Data Quality agent scores five axes, reports every issue it finds, and records each fix it applies."
        icon={<ListChecks className="size-5" />}
      />
    );
  }

  const report = quality.data[0];
  const applied = transforms.data ?? [];
  const issues = report.issues.filter((issue) => severity === "all" || issue.severity === severity);
  const counts = {
    high: report.issues.filter((issue) => issue.severity === "high").length,
    medium: report.issues.filter((issue) => issue.severity === "medium").length,
    low: report.issues.filter((issue) => issue.severity === "low").length,
  };

  // An issue type is "handled" when a transformation of the matching operation ran.
  const handledTypes = new Set(
    applied.flatMap((item) => {
      if (item.operation === "drop_duplicates") return ["duplicates"];
      if (item.operation === "trim_whitespace") return ["whitespace"];
      if (item.operation === "empty_to_null") return ["empty_string"];
      return [];
    }),
  );

  return (
    <div className="space-y-4">
      <div className="grid items-start gap-4 lg:grid-cols-[22rem_1fr]">
        {/* Scorecard */}
        <Panel>
          <PanelHeader
            title="Quality score"
            subtitle="Five measured axes"
            action={
              <Badge tone={statusTone(report.overall_score >= 85 ? "valid" : "warning")}>
                {report.overall_score >= 85 ? "healthy" : "review"}
              </Badge>
            }
          />
          <p className="tnum text-[2.75rem] leading-none font-semibold tracking-tight text-ink">
            {report.overall_score.toFixed(2)}
            <span className="ml-1.5 text-sm font-normal text-ink-faint">/ 100</span>
          </p>
          <dl className="mt-6 space-y-3.5">
            {AXES.map((axis) => {
              const value = report[axis.key];
              return (
                <div key={axis.key}>
                  <div className="mb-1 flex items-baseline justify-between">
                    <dt className="text-[0.75rem] text-ink-muted">{axis.label}</dt>
                    <dd className="tnum text-[0.75rem] font-medium text-ink-soft">
                      {value.toFixed(1)}
                    </dd>
                  </div>
                  <Meter value={value} tone={tone(value)} />
                </div>
              );
            })}
          </dl>
        </Panel>

        {/* Issues */}
        <Panel>
          <PanelHeader
            title="Issues detected"
            subtitle={`${report.issues.length} found by the quality agent`}
            action={
              <SegmentGroup>
                <Segment active={severity === "all"} onClick={() => setSeverity("all")}>
                  All {report.issues.length}
                </Segment>
                {counts.high > 0 && (
                  <Segment active={severity === "high"} onClick={() => setSeverity("high")}>
                    High {counts.high}
                  </Segment>
                )}
                {counts.medium > 0 && (
                  <Segment active={severity === "medium"} onClick={() => setSeverity("medium")}>
                    Medium {counts.medium}
                  </Segment>
                )}
                {counts.low > 0 && (
                  <Segment active={severity === "low"} onClick={() => setSeverity("low")}>
                    Low {counts.low}
                  </Segment>
                )}
              </SegmentGroup>
            }
          />

          <ul className="space-y-2.5">
            {issues.map((issue) => {
              const handled = handledTypes.has(issue.issue_type);
              return (
                <li
                  key={issue.id}
                  className="rounded-card border border-line bg-raised p-3.5 transition-shadow duration-[--duration-fast] hover:shadow-card"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <Badge tone={statusTone(issue.severity)}>{issue.severity}</Badge>
                      <span className="truncate text-[0.875rem] font-medium text-ink">
                        {issue.issue_type.replace(/_/g, " ")}
                      </span>
                      {issue.column_name && (
                        <code className="truncate rounded bg-inset px-1.5 py-0.5 font-mono text-[0.625rem] text-ink-soft">
                          {issue.column_name}
                        </code>
                      )}
                    </div>
                    <Badge tone={handled ? "good" : "neutral"}>
                      {handled ? "resolved automatically" : "reported, not changed"}
                    </Badge>
                  </div>

                  <div className="mt-2.5 grid gap-x-6 gap-y-2 sm:grid-cols-[auto_1fr]">
                    {issue.rows_affected > 0 && (
                      <div>
                        <Eyebrow>Affected</Eyebrow>
                        <p className="tnum mt-0.5 text-[0.875rem] font-semibold text-ink">
                          {issue.rows_affected.toLocaleString("en-GB")}
                          <span className="ml-1 text-[0.6875rem] font-normal text-ink-faint">rows</span>
                        </p>
                      </div>
                    )}
                    <div className="min-w-0">
                      <Eyebrow>BIFlow&rsquo;s recommendation</Eyebrow>
                      <p className="mt-0.5 text-[0.8125rem] leading-relaxed text-ink-muted">
                        {issue.recommended_action}
                      </p>
                    </div>
                  </div>

                  <p className="mt-2.5 border-t border-line pt-2 text-[0.625rem] text-ink-faint">
                    Detected by {issue.detection_method}
                  </p>
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>

      {/* Applied transformations */}
      <Panel>
        <PanelHeader
          title="Transformations applied"
          subtitle="Only conservative, reversible fixes run automatically — outliers are never dropped"
          icon={<Wand2 className="size-4" />}
          action={<Badge tone="neutral">{applied.length} applied</Badge>}
        />
        {applied.length === 0 ? (
          <p className="text-[0.8125rem] text-ink-muted">
            Nothing needed changing — every issue above was reported rather than altered.
          </p>
        ) : (
          <DataTable
            head={[
              "Operation",
              "Target",
              <span key="r" className="block text-right">Rows</span>,
              "Before → after",
              "Reason",
            ]}
          >
            {applied.map((item) => (
              <Tr key={item.id}>
                <Td className="font-medium text-ink">{item.operation.replace(/_/g, " ")}</Td>
                <Td className="font-mono text-[0.6875rem]">
                  {item.table_name}
                  {item.column_name ? `.${item.column_name}` : ""}
                </Td>
                <Td numeric>{item.rows_affected.toLocaleString("en-GB")}</Td>
                <Td className="font-mono text-[0.6875rem]">
                  {item.before_example ? (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="rounded bg-bad-soft px-1 py-0.5 text-bad">
                        {`"${item.before_example}"`}
                      </span>
                      <span className="text-ink-faint" aria-hidden>→</span>
                      <span className="rounded bg-good-soft px-1 py-0.5 text-good">
                        {`"${item.after_example ?? ""}"`}
                      </span>
                    </span>
                  ) : (
                    "—"
                  )}
                </Td>
                <Td className="max-w-sm text-[0.75rem] leading-snug text-ink-muted">{item.reason}</Td>
              </Tr>
            ))}
          </DataTable>
        )}
      </Panel>
    </div>
  );
}

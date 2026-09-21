"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { ListChecks, Wand2 } from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Cell, EmptyState, Meter, Row, Table } from "@/components/ui/data";
import { api } from "@/lib/api";

type Issue = {
  id: string;
  severity: string;
  issue_type: string;
  table_name: string | null;
  column_name: string | null;
  rows_affected: number;
  detection_method: string;
  recommended_action: string;
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

function scoreTone(score: number) {
  if (score >= 85) return "good" as const;
  if (score >= 60) return "warn" as const;
  return "bad" as const;
}

export default function QualityPage() {
  const { id } = useParams<{ id: string }>();
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

  if (quality.isError) {
    return (
      <EmptyState
        title="No quality report yet"
        message="Upload a dataset and run the pipeline. The quality agent scores five axes and records every fix it applies."
        icon={<ListChecks className="size-5" />}
      />
    );
  }

  const reports = quality.data ?? [];
  const issues = reports.flatMap((report) => report.issues);
  const bySeverity = (severity: string) =>
    issues.filter((issue) => issue.severity === severity).length;

  return (
    <div className="space-y-4">
      <div className="grid items-start gap-4 lg:grid-cols-[1fr_1.6fr]">
        {reports.map((report) => (
          <Card key={report.id}>
            <CardHeader
              title="Quality score"
              action={
                <Badge tone={statusTone(report.overall_score >= 85 ? "valid" : "warning")}>
                  {report.overall_score >= 85 ? "healthy" : "review"}
                </Badge>
              }
            />
            <p className="text-[2.5rem] leading-none font-semibold tracking-tight text-ink">
              {report.overall_score}
              <span className="ml-1 text-base font-normal text-ink-faint">/ 100</span>
            </p>
            <dl className="mt-5 space-y-3">
              {AXES.map((axis) => {
                const value = report[axis.key];
                return (
                  <div key={axis.key}>
                    <div className="mb-1 flex items-baseline justify-between">
                      <dt className="text-xs text-ink-muted">{axis.label}</dt>
                      <dd className="text-xs font-medium tabular-nums text-ink-soft">{value}</dd>
                    </div>
                    <Meter value={value} tone={scoreTone(value)} />
                  </div>
                );
              })}
            </dl>
          </Card>
        ))}

        <Card>
          <CardHeader
            title="Detected issues"
            subtitle={`${issues.length} total`}
            action={
              <div className="flex gap-1.5">
                {bySeverity("high") > 0 && <Badge tone="error">{bySeverity("high")} high</Badge>}
                {bySeverity("medium") > 0 && (
                  <Badge tone="warning">{bySeverity("medium")} medium</Badge>
                )}
                {bySeverity("low") > 0 && <Badge tone="neutral">{bySeverity("low")} low</Badge>}
              </div>
            }
          />
          {issues.length === 0 ? (
            <p className="text-[0.8125rem] text-ink-muted">No issues detected.</p>
          ) : (
            <div className="max-h-[26rem] overflow-auto">
              <Table
                head={[
                  "Severity",
                  "Issue",
                  "Column",
                  <span key="rows" className="block text-right">
                    Rows
                  </span>,
                  "Recommended action",
                ]}
              >
                {issues.map((issue) => (
                  <Row key={issue.id}>
                    <Cell>
                      <Badge tone={statusTone(issue.severity)}>{issue.severity}</Badge>
                    </Cell>
                    <Cell className="font-medium text-ink">
                      {issue.issue_type.replace(/_/g, " ")}
                    </Cell>
                    <Cell className="font-mono text-[0.6875rem]">{issue.column_name ?? "—"}</Cell>
                    <Cell numeric>
                      {issue.rows_affected ? issue.rows_affected.toLocaleString("en-GB") : "—"}
                    </Cell>
                    <Cell className="max-w-sm text-xs leading-snug text-ink-muted">
                      {issue.recommended_action}
                    </Cell>
                  </Row>
                ))}
              </Table>
            </div>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Applied transformations"
          subtitle="Only conservative, recorded fixes are applied automatically — outliers are never dropped."
          action={
            <span className="grid size-8 place-items-center rounded-xl bg-brand-soft text-brand">
              <Wand2 className="size-4" aria-hidden />
            </span>
          }
        />
        {(transforms.data?.length ?? 0) === 0 ? (
          <p className="text-[0.8125rem] text-ink-muted">Nothing needed changing.</p>
        ) : (
          <Table
            head={[
              "Operation",
              "Target",
              <span key="rows" className="block text-right">
                Rows
              </span>,
              "Before → after",
              "Reason",
            ]}
          >
            {transforms.data?.map((item) => (
              <Row key={item.id}>
                <Cell className="font-medium text-ink">{item.operation.replace(/_/g, " ")}</Cell>
                <Cell className="font-mono text-[0.6875rem]">
                  {item.table_name}
                  {item.column_name ? `.${item.column_name}` : ""}
                </Cell>
                <Cell numeric>{item.rows_affected.toLocaleString("en-GB")}</Cell>
                <Cell className="font-mono text-[0.6875rem]">
                  {item.before_example ? (
                    <>
                      <span className="text-bad">{`"${item.before_example}"`}</span>
                      <span className="mx-1 text-ink-faint">→</span>
                      <span className="text-good">{`"${item.after_example ?? ""}"`}</span>
                    </>
                  ) : (
                    "—"
                  )}
                </Cell>
                <Cell className="max-w-sm text-xs leading-snug text-ink-muted">{item.reason}</Cell>
              </Row>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

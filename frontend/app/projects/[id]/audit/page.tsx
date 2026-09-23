"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, Waypoints } from "lucide-react";

import {
  Badge,
  DataTable,
  EmptyState,
  Eyebrow,
  Field,
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
import { LineageTrace, type LineageGraph } from "@/components/lineage-trace";
import { api, type KPI } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Audit and explainability.
 *
 * Two halves of one claim: the verdict says whether the run may publish, and
 * the trace shows, for any KPI, the path from the raw file to the number. Both
 * come from records the auditor wrote — nothing here is reconstructed by the
 * frontend.
 */

type AuditEvent = {
  id: string;
  event_type: string;
  severity: string;
  message: string;
  entity_type: string;
  status: string;
  details: Record<string, unknown> | null;
};

type Explanation = {
  id: string;
  entity_type: string;
  entity_id: string;
  what_happened: string;
  how_calculated: string;
  data_used: string;
  assumptions: string;
  quality_limitations: string;
  transformations: string;
  producer_agent: string;
  validator_agent: string;
};

/** Metrics whose score is a multiplier rather than a proportion. */
function isRatio(metric: string) {
  return metric === "vs_naive_baseline";
}

type Evaluation = {
  agent_name: string;
  metric_name: string;
  score: number;
  details: Record<string, unknown>;
};

export default function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [traceKpi, setTraceKpi] = useState<string | null>(null);

  const audit = useQuery({
    queryKey: ["audit", id],
    queryFn: () =>
      api.audit(id) as Promise<{ events: AuditEvent[]; explanations: Explanation[] }>,
    retry: false,
  });
  const evaluation = useQuery({
    queryKey: ["evaluation", id],
    queryFn: () => api.evaluation(id) as Promise<Evaluation[]>,
    retry: false,
  });
  const lineage = useQuery({
    queryKey: ["lineage", id],
    queryFn: () => api.lineage(id) as Promise<{ run_id: string; kpis: LineageGraph[] }>,
    retry: false,
  });
  const kpis = useQuery({
    queryKey: ["kpis", id],
    queryFn: () => api.kpis(id),
    retry: false,
  });

  const graphs = lineage.data?.kpis ?? [];
  const kpiList = useMemo(
    () => (kpis.data ?? []).filter((kpi) => kpi.validation_status === "computed"),
    [kpis.data],
  );
  const selectedKpi: KPI | undefined =
    kpiList.find((kpi) => kpi.id === traceKpi) ?? kpiList[0];
  const selectedGraph =
    graphs.find((graph) => graph.kpi_name === selectedKpi?.name) ??
    graphs[kpiList.indexOf(selectedKpi as KPI)] ??
    graphs[0];

  if (audit.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (audit.isError || !audit.data) {
    return (
      <EmptyState
        title="No audit record yet"
        message="Run the pipeline. The auditor validates every KPI and insight, writes an explanation for each, and decides whether the dashboard may publish."
        icon={<ShieldCheck className="size-5" />}
      />
    );
  }

  const events = audit.data.events ?? [];
  const verdict = events.find((event) => event.event_type === "run_verdict");
  const checks = events.filter((event) => event.event_type !== "run_verdict");
  const failing = checks.filter((event) => event.status !== "VALID");
  const shown = onlyProblems ? failing : checks;
  const caveats = (verdict?.details?.caveats as string[] | undefined) ?? [];
  const coverage = checks.length ? ((checks.length - failing.length) / checks.length) * 100 : 0;

  return (
    <div className="space-y-4">
      {/* Verdict */}
      {verdict && (
        <Panel
          className={cn(
            verdict.status === "VALID"
              ? "border-good/25 bg-gradient-to-br from-good-soft/50 to-surface"
              : "border-warn/25 bg-gradient-to-br from-warn-soft/50 to-surface",
          )}
        >
          <div className="flex flex-wrap items-start gap-4">
            <span
              className={cn(
                "grid size-11 shrink-0 place-items-center rounded-xl",
                verdict.status === "VALID" ? "bg-good-soft text-good" : "bg-warn-soft text-warn",
              )}
            >
              <ShieldCheck className="size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-[0.9375rem] font-semibold tracking-tight text-ink">
                  Run verdict
                </h2>
                <Badge tone={statusTone(verdict.status)} dot>
                  {verdict.status}
                </Badge>
              </div>
              <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-soft">
                {verdict.message}
              </p>
              {caveats.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {caveats.map((caveat, index) => (
                    <li key={index} className="flex gap-2 text-[0.75rem] leading-snug text-ink-muted">
                      <span
                        className="mt-1.5 size-1 shrink-0 rounded-full bg-ink-faint"
                        aria-hidden
                      />
                      {caveat}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="w-40 shrink-0">
              <Eyebrow>Audit coverage</Eyebrow>
              <p className="tnum mt-1 text-lg font-semibold text-ink">{coverage.toFixed(0)}%</p>
              <Meter
                value={coverage}
                tone={coverage === 100 ? "good" : coverage > 80 ? "warn" : "bad"}
                className="mt-1.5"
              />
              <p className="mt-1.5 text-[0.625rem] text-ink-faint">
                {checks.length - failing.length} of {checks.length} entities valid
              </p>
            </div>
          </div>
        </Panel>
      )}

      {/* Insight trace */}
      <Panel>
        <PanelHeader
          title="Insight trace"
          subtitle="Follow any number back to the file it came from"
          icon={<Waypoints className="size-4" />}
          action={
            kpiList.length > 0 && (
              <select
                value={selectedKpi?.id ?? ""}
                onChange={(event) => setTraceKpi(event.target.value)}
                className="max-w-52 rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink-soft focus:border-brand focus:outline-none"
                aria-label="Choose a KPI to trace"
              >
                {kpiList.map((kpi) => (
                  <option key={kpi.id} value={kpi.id}>
                    {kpi.name}
                  </option>
                ))}
              </select>
            )
          }
        />
        {selectedGraph && selectedKpi ? (
          <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
            <LineageTrace graph={selectedGraph} />
            <div className="space-y-4">
              <div>
                <Eyebrow>Formula</Eyebrow>
                <code className="mt-1.5 block rounded-lg border border-line bg-inset p-3 font-mono text-[0.6875rem] leading-relaxed break-words text-ink-soft">
                  {selectedKpi.formula}
                </code>
              </div>
              {selectedKpi.query_sql && (
                <div>
                  <Eyebrow>Compiled SQL</Eyebrow>
                  <code className="mt-1.5 block overflow-auto rounded-lg border border-line bg-inset p-3 font-mono text-[0.6875rem] leading-relaxed break-words text-ink-soft">
                    {selectedKpi.query_sql}
                  </code>
                </div>
              )}
              {(() => {
                const explanation = audit.data.explanations.find(
                  (item) => item.entity_id === selectedKpi.id,
                );
                if (!explanation) return null;
                return (
                  <dl className="space-y-3 border-t border-line pt-4">
                    <Field label="Data used">{explanation.data_used}</Field>
                    <Field label="Transformations">{explanation.transformations}</Field>
                    <Field label="Agents">
                      {explanation.producer_agent} → {explanation.validator_agent}
                    </Field>
                  </dl>
                );
              })()}
            </div>
          </div>
        ) : (
          <p className="text-[0.8125rem] text-ink-muted">
            No lineage recorded — run the pipeline to produce KPIs to trace.
          </p>
        )}
      </Panel>

      {/* Evaluation */}
      {evaluation.data && evaluation.data.length > 0 && (
        <Panel>
          <PanelHeader
            title="Agent evaluation"
            subtitle="Each agent scored, including against a naive non-agentic baseline"
          />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {evaluation.data.map((row) => (
              <div key={`${row.agent_name}-${row.metric_name}`}>
                <div className="mb-1.5 flex items-baseline justify-between gap-2">
                  <p className="truncate text-[0.8125rem] font-medium text-ink">
                    {row.metric_name.replace(/_/g, " ")}
                  </p>
                  <p className="tnum shrink-0 text-[0.8125rem] font-semibold text-ink">
                    {/* The baseline comparison is a ratio, not a share: 4.7x as
                        many KPIs as a naive script, which "467%" obscures. */}
                    {isRatio(row.metric_name)
                      ? `${row.score.toFixed(1)}x`
                      : `${(row.score * 100).toFixed(0)}%`}
                  </p>
                </div>
                <Meter
                  value={isRatio(row.metric_name) ? Math.min(100, row.score * 20) : row.score * 100}
                  tone={row.score >= 0.8 ? "good" : row.score >= 0.5 ? "warn" : "bad"}
                />
                <p className="mt-1.5 text-[0.625rem] text-ink-faint">{row.agent_name} agent</p>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Validation checks */}
      <Panel>
        <PanelHeader
          title="Validation checks"
          subtitle={`${checks.length} entities validated, ${failing.length} rejected`}
          action={
            <SegmentGroup>
              <Segment active={!onlyProblems} onClick={() => setOnlyProblems(false)}>
                All
              </Segment>
              <Segment active={onlyProblems} onClick={() => setOnlyProblems(true)}>
                Problems {failing.length}
              </Segment>
            </SegmentGroup>
          }
        />
        {shown.length === 0 ? (
          <p className="text-[0.8125rem] text-ink-muted">
            {onlyProblems ? "Nothing was rejected." : "No checks recorded."}
          </p>
        ) : (
          <div className="max-h-96 overflow-auto">
            <DataTable head={["Status", "Entity", "Check", "Message"]} sticky>
              {shown.map((event) => (
                <Tr key={event.id}>
                  <Td>
                    <Badge tone={statusTone(event.status)}>{event.status}</Badge>
                  </Td>
                  <Td className="text-ink-faint">{event.entity_type}</Td>
                  <Td>{event.event_type.replace(/_/g, " ")}</Td>
                  <Td className="text-ink-soft">{event.message}</Td>
                </Tr>
              ))}
            </DataTable>
          </div>
        )}
      </Panel>
    </div>
  );
}

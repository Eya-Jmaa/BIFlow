"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { ShieldCheck } from "lucide-react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Cell, EmptyState, Field, Meter, Row, Table } from "@/components/ui/data";
import { Toggle } from "@/components/ui/button";
import { api } from "@/lib/api";

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
  what_happened: string;
  how_calculated: string;
  data_used: string;
  assumptions: string;
  quality_limitations: string;
  transformations: string;
  producer_agent: string;
  validator_agent: string;
};

type Evaluation = {
  agent_name: string;
  metric_name: string;
  score: number;
  details: Record<string, unknown>;
};

export default function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const audit = useQuery({
    queryKey: ["audit", id],
    queryFn: () =>
      api.audit(id) as Promise<{ events: AuditEvent[]; explanations: Explanation[]; status: string }>,
    retry: false,
  });
  const evaluation = useQuery({
    queryKey: ["evaluation", id],
    queryFn: () => api.evaluation(id) as Promise<Evaluation[]>,
    retry: false,
  });
  const [onlyProblems, setOnlyProblems] = useState(false);

  if (audit.isError) {
    return (
      <EmptyState
        title="No audit record yet"
        message="The auditor validates every KPI and insight, then decides whether the run may publish."
        icon={<ShieldCheck className="size-5" />}
      />
    );
  }

  const events = audit.data?.events ?? [];
  const verdict = events.find((event) => event.event_type === "run_verdict");
  const checks = events.filter((event) => event.event_type !== "run_verdict");
  const failing = checks.filter((event) => event.status !== "VALID");
  const shown = onlyProblems ? failing : checks;
  const caveats = (verdict?.details?.caveats as string[] | undefined) ?? [];

  return (
    <div className="space-y-4">
      {verdict && (
        <Card
          className={
            verdict.status === "VALID"
              ? "border-good/20 bg-gradient-to-br from-good-soft/60 to-surface"
              : "border-warn/20 bg-gradient-to-br from-warn-soft/60 to-surface"
          }
        >
          <div className="flex items-start gap-4">
            <span
              className={`grid size-11 shrink-0 place-items-center rounded-2xl ${
                verdict.status === "VALID" ? "bg-good-soft text-good" : "bg-warn-soft text-warn"
              }`}
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
                    <li key={index} className="flex gap-2 text-xs leading-snug text-ink-muted">
                      <span className="mt-1 size-1 shrink-0 rounded-full bg-ink-faint" aria-hidden />
                      {caveat}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </Card>
      )}

      {evaluation.data && evaluation.data.length > 0 && (
        <Card>
          <CardHeader
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
                  <p className="shrink-0 text-[0.8125rem] font-semibold tabular-nums text-ink">
                    {(row.score * 100).toFixed(0)}%
                  </p>
                </div>
                <Meter
                  value={row.score * 100}
                  tone={row.score >= 0.8 ? "good" : row.score >= 0.5 ? "warn" : "bad"}
                />
                <p className="mt-1.5 text-[0.6875rem] text-ink-faint">{row.agent_name} agent</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Validation checks"
          subtitle={`${checks.length} entities validated, ${failing.length} rejected`}
          action={
            <div className="flex rounded-lg bg-surface-sunken p-0.5">
              <Toggle active={!onlyProblems} onClick={() => setOnlyProblems(false)}>
                All
              </Toggle>
              <Toggle active={onlyProblems} onClick={() => setOnlyProblems(true)}>
                Problems
              </Toggle>
            </div>
          }
        />
        {shown.length === 0 ? (
          <p className="text-[0.8125rem] text-ink-muted">
            {onlyProblems ? "Nothing was rejected." : "No checks recorded."}
          </p>
        ) : (
          <div className="max-h-96 overflow-auto">
            <Table head={["Status", "Entity", "Check", "Message"]}>
              {shown.map((event) => (
                <Row key={event.id}>
                  <Cell>
                    <Badge tone={statusTone(event.status)}>{event.status}</Badge>
                  </Cell>
                  <Cell className="text-ink-faint">{event.entity_type}</Cell>
                  <Cell>{event.event_type.replace(/_/g, " ")}</Cell>
                  <Cell className="text-ink-soft">{event.message}</Cell>
                </Row>
              ))}
            </Table>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader
          title="XAI explanations"
          subtitle="Why each number is what it is, in the agent's own record"
        />
        <div className="space-y-3">
          {(audit.data?.explanations ?? []).map((explanation) => (
            <details
              key={explanation.id}
              className="rounded-xl border border-line bg-surface-muted/50 px-4 py-3"
            >
              <summary className="cursor-pointer text-[0.8125rem] font-medium text-ink">
                {explanation.what_happened}
              </summary>
              <dl className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
                <Field label="How it was calculated">{explanation.how_calculated}</Field>
                <Field label="Data used">{explanation.data_used}</Field>
                <Field label="Assumptions">{explanation.assumptions}</Field>
                <Field label="Quality limitations">{explanation.quality_limitations}</Field>
                <Field label="Transformations applied">{explanation.transformations}</Field>
                <Field label="Agents">
                  {explanation.producer_agent} → {explanation.validator_agent}
                </Field>
              </dl>
            </details>
          ))}
        </div>
      </Card>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Sparkles } from "lucide-react";

import {
  Badge,
  Button,
  Eyebrow,
  Input,
  Panel,
  Textarea,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Guided project creation.
 *
 * The business objective is the most consequential field on the screen — it
 * drives the domain the orchestrator infers, which in turn decides which KPI
 * templates the catalog can instantiate — so it gets the most room and a live
 * preview of what the backend will actually conclude from it.
 *
 * That preview calls `POST /api/domains/infer`, which runs the very same
 * `infer_domain` the pipeline runs. It is a real inference, not an illustration.
 */

const EXAMPLES = [
  "Analyse e-commerce sales performance, customer behaviour, product mix and revenue evolution across countries.",
  "Understand subscriber churn, ARPU and contract mix across our telecom base.",
  "Track claim volume, resolution time and cost per encounter across departments.",
];

type Step = { n: number; title: string; hint: string };

const STEPS: Step[] = [
  { n: 1, title: "Name your project", hint: "Anything you will recognise later." },
  { n: 2, title: "Describe what you want to understand", hint: "This drives everything downstream." },
  { n: 3, title: "Review what BIFlow infers", hint: "The domain decides which KPIs apply." },
];

export function NewProject({ className }: { className?: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [debounced, setDebounced] = useState("");

  // Debounced so typing does not fire an inference per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(objective.trim()), 400);
    return () => clearTimeout(timer);
  }, [objective]);

  const inference = useQuery({
    queryKey: ["domain-infer", debounced],
    queryFn: () => api.inferDomain(debounced),
    enabled: debounced.length > 12,
    retry: false,
    staleTime: 60_000,
  });

  const create = useMutation({
    mutationFn: () =>
      api.createProject({
        name: name.trim(),
        business_objective: objective.trim(),
        domain: inference.data?.domain ?? "general",
      }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      // Straight to Datasets — the next real action is uploading data.
      router.push(`/projects/${project.id}/datasets`);
    },
  });

  const step = useMemo(() => {
    if (!name.trim()) return 1;
    if (objective.trim().length <= 12) return 2;
    return 3;
  }, [name, objective]);

  const ready = name.trim().length > 0 && objective.trim().length > 12;

  return (
    <Panel className={cn("overflow-hidden p-0", className)}>
      {/* Step rail */}
      <div className="flex items-center gap-3 border-b border-line bg-sunken/60 px-5 py-3">
        {STEPS.map((item, index) => (
          <div key={item.n} className="flex flex-1 items-center gap-2">
            <span
              className={cn(
                "grid size-5 shrink-0 place-items-center rounded-full text-[0.625rem] font-semibold transition-colors duration-[--duration-base]",
                step > item.n
                  ? "bg-brand text-white"
                  : step === item.n
                    ? "bg-brand/15 text-brand ring-1 ring-brand/40 ring-inset"
                    : "bg-inset text-ink-faint",
              )}
            >
              {step > item.n ? <Check className="size-3" aria-hidden /> : item.n}
            </span>
            <span
              className={cn(
                "hidden truncate text-[0.6875rem] font-medium transition-colors sm:block",
                step >= item.n ? "text-ink-soft" : "text-ink-faint",
              )}
            >
              {item.title}
            </span>
            {index < STEPS.length - 1 && (
              <span className="hidden h-px flex-1 bg-line sm:block" aria-hidden />
            )}
          </div>
        ))}
      </div>

      <div className="space-y-5 p-5">
        <div>
          <Eyebrow>Step 1 — Name</Eyebrow>
          <Input
            className="mt-2"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Q4 revenue review"
            aria-label="Project name"
          />
        </div>

        <div>
          <div className="flex items-baseline justify-between gap-3">
            <Eyebrow>Step 2 — What should BIFlow help you understand?</Eyebrow>
            <span className="text-[0.625rem] text-ink-faint">drives domain inference</span>
          </div>
          <Textarea
            className="mt-2 min-h-24"
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            placeholder="Describe the business question in a sentence or two."
            aria-label="Business objective"
          />
          {!objective && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {EXAMPLES.map((example, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setObjective(example)}
                  className="rounded-full bg-inset px-2.5 py-1 text-[0.6875rem] text-ink-muted transition-colors duration-[--duration-fast] hover:bg-brand-soft hover:text-brand-strong"
                >
                  {example.split(" ").slice(0, 4).join(" ")}…
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Step 3 — live, real inference */}
        <div>
          <Eyebrow>Step 3 — BIFlow infers</Eyebrow>
          <div
            className={cn(
              "mt-2 rounded-card border p-4 transition-[border-color,background-color] duration-[--duration-base]",
              inference.data?.confident
                ? "border-brand-line bg-brand-soft/50"
                : "border-line bg-sunken/50",
            )}
          >
            {debounced.length <= 12 ? (
              <p className="text-[0.8125rem] text-ink-faint">
                Describe your objective above and BIFlow will infer the business domain.
              </p>
            ) : inference.isLoading ? (
              <p className="flex items-center gap-2 text-[0.8125rem] text-ink-muted">
                <Sparkles className="size-3.5 animate-pulse text-brand" aria-hidden />
                Inferring domain…
              </p>
            ) : inference.isError ? (
              <p className="text-[0.8125rem] text-ink-muted">
                Domain preview unavailable — the pipeline will still infer it at run time.
              </p>
            ) : inference.data ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[0.8125rem] text-ink-muted">Domain</span>
                  <Badge tone={inference.data.confident ? "brand" : "neutral"}>
                    {inference.data.domain}
                  </Badge>
                  {!inference.data.confident && (
                    <span className="text-[0.6875rem] text-ink-faint">
                      no domain keywords matched — falling back to general
                    </span>
                  )}
                </div>

                {inference.data.matched_terms.length > 0 && (
                  <InferRow label="Matched" items={inference.data.matched_terms} />
                )}
                {inference.data.common_dimensions.length > 0 && (
                  <InferRow label="Likely dimensions" items={inference.data.common_dimensions} muted />
                )}
                {inference.data.common_kpis.length > 0 && (
                  <InferRow
                    label="Candidate KPIs"
                    items={inference.data.common_kpis.map((kpi) => kpi.replace(/_/g, " "))}
                    muted
                  />
                )}
                <p className="border-t border-line/70 pt-2.5 text-[0.6875rem] leading-relaxed text-ink-faint">
                  Candidates only. Which KPIs are actually built depends on the business roles the
                  profiler can bind to real columns in your data.
                </p>
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
          <Button onClick={() => create.mutate()} disabled={!ready || create.isPending}>
            {create.isPending ? "Creating…" : "Create project"}
            <ArrowRight aria-hidden />
          </Button>
          <span className="text-[0.75rem] text-ink-faint">
            Next: upload a dataset, then run the pipeline.
          </span>
        </div>

        {create.error && (
          <p className="text-[0.8125rem] text-bad">{(create.error as Error).message}</p>
        )}
      </div>
    </Panel>
  );
}

function InferRow({
  label,
  items,
  muted,
}: {
  label: string;
  items: string[];
  muted?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1.5">
      <span className="text-[0.6875rem] text-ink-faint">{label}</span>
      {items.slice(0, 6).map((item) => (
        <span
          key={item}
          className={cn(
            "rounded-md px-1.5 py-0.5 text-[0.6875rem]",
            muted ? "bg-surface text-ink-muted ring-1 ring-line ring-inset" : "bg-brand/12 text-brand-strong",
          )}
        >
          {item}
        </span>
      ))}
    </div>
  );
}

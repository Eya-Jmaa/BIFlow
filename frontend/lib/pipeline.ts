/**
 * The BIFlow pipeline, defined once.
 *
 * The hero graph, the sidebar, the project cards and the stepper all read from
 * this list, so a stage can never be named one thing in navigation and another
 * on a card. `agent` is the backend's own step name (see STEP_SEQUENCE in
 * `app/pipeline/executor.py`) — it is how UI state binds to real run state.
 */

export type StageId =
  | "profile"
  | "clean"
  | "model"
  | "measure"
  | "analyze"
  | "visualize"
  | "audit";

export type Stage = {
  id: StageId;
  /** Backend `pipeline_steps.name` / `agent_runs.agent_name`. */
  agent: string;
  index: string;
  label: string;
  /** The agent's job, in the product's own words. */
  role: string;
  /** What this stage does, for the hero hover panel. */
  blurb: string;
  /** Route segment under /projects/[id]. */
  href: string;
};

export const STAGES: Stage[] = [
  {
    id: "profile",
    agent: "profiler",
    index: "01",
    label: "Profile",
    role: "Data Profiler",
    blurb:
      "Reads every column: types, missingness, cardinality, distributions and PII. Resolves date formats from evidence rather than guessing.",
    href: "/profile",
  },
  {
    id: "clean",
    agent: "quality",
    index: "02",
    label: "Clean",
    role: "Data Quality / ETL",
    blurb:
      "Scores quality on five axes and applies only conservative, recorded transformations. Outliers are reported, never dropped.",
    href: "/clean",
  },
  {
    id: "model",
    agent: "semantic",
    index: "03",
    label: "Model",
    role: "Semantic Modeller",
    blurb:
      "Binds business roles to physical columns, then derives dimensions, measures and statistically validated relationships.",
    href: "/model",
  },
  {
    id: "measure",
    agent: "semantic",
    index: "04",
    label: "Measure",
    role: "KPI Engine",
    blurb:
      "Instantiates the domain KPI catalog against bound roles and compiles each formula to read-only SQL before executing it.",
    href: "/measures",
  },
  {
    id: "analyze",
    agent: "analyst",
    index: "05",
    label: "Analyze",
    role: "BI Analyst",
    blurb:
      "Runs trend, anomaly, seasonality, Pareto and correlation tests over the computed series, then ranks what is worth saying.",
    href: "/analyze",
  },
  {
    id: "visualize",
    agent: "dashboard",
    index: "06",
    label: "Visualize",
    role: "Dashboard Generator",
    blurb:
      "Chooses widget types and binds each one to a computed metric. Nothing renders that is not backed by a real query.",
    href: "/visualize",
  },
  {
    id: "audit",
    agent: "auditor",
    index: "07",
    label: "Audit",
    role: "Auditor / XAI",
    blurb:
      "Validates every KPI and insight, traces each back to its SQL and source columns, and decides whether the run may publish.",
    href: "/audit",
  },
];

export const STAGE_BY_AGENT: Record<string, Stage[]> = STAGES.reduce(
  (map, stage) => {
    (map[stage.agent] ??= []).push(stage);
    return map;
  },
  {} as Record<string, Stage[]>,
);

export type StageStatus = "completed" | "running" | "failed" | "pending";

/**
 * Derive each stage's status from the backend's pipeline steps.
 *
 * Model and Measure are both produced by the `semantic` agent, so they share
 * one step's status — the mapping is explicit rather than inferred, because a
 * stage showing "complete" when nothing ran is the worst kind of lie in a
 * tool whose entire claim is traceability.
 */
export function stageStatuses(
  steps: { name: string; status: string }[] | undefined,
): Record<StageId, StageStatus> {
  const byName = new Map((steps ?? []).map((step) => [step.name, step.status]));
  const result = {} as Record<StageId, StageStatus>;
  for (const stage of STAGES) {
    const status = byName.get(stage.agent);
    result[stage.id] =
      status === "completed"
        ? "completed"
        : status === "running"
          ? "running"
          : status === "failed"
            ? "failed"
            : "pending";
  }
  return result;
}

export function completedCount(statuses: Record<StageId, StageStatus>): number {
  return STAGES.filter((stage) => statuses[stage.id] === "completed").length;
}

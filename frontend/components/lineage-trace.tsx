"use client";

import { ArrowDown, Database, FileText, FunctionSquare, Layers, Play, Table2 } from "lucide-react";

import { Code, Eyebrow } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * Insight trace.
 *
 * Reads the lineage graph the backend records per KPI and renders it as a
 * vertical chain, because that is how the question is actually asked: "where
 * did this number come from?" is answered by walking one path down, not by
 * exploring a network.
 */

export type LineageNode = {
  id: string;
  type: string;
  label: string;
  details?: Record<string, unknown> | null;
};

export type LineageEdge = { source: string; target: string; label: string };

export type LineageGraph = {
  kpi_name?: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
};

const NODE_ICON: Record<string, typeof Database> = {
  pipeline_run: Play,
  dataset: Database,
  raw: Database,
  transform: Layers,
  table: Table2,
  formula: FunctionSquare,
  sql: FileText,
  kpi: FunctionSquare,
};

const NODE_TONE: Record<string, string> = {
  pipeline_run: "bg-inset text-ink-muted",
  dataset: "bg-info-soft text-info",
  raw: "bg-info-soft text-info",
  transform: "bg-warn-soft text-warn",
  table: "bg-brand-soft text-brand",
  formula: "bg-brand-soft text-brand",
  sql: "bg-good-soft text-good",
  kpi: "bg-good-soft text-good",
};

export function LineageTrace({
  graph,
  sql,
  className,
}: {
  graph: LineageGraph;
  /** The compiled SQL, shown as the terminal step when available. */
  sql?: string | null;
  className?: string;
}) {
  // The recorded edges give the traversal order; follow them from the root.
  const ordered = orderNodes(graph);

  return (
    <div className={cn("relative", className)}>
      <ol className="space-y-0">
        {ordered.map((node, index) => {
          const Icon = NODE_ICON[node.type] ?? Layers;
          const edge = graph.edges.find((item) => item.source === node.id);
          const isLast = index === ordered.length - 1;

          return (
            <li key={node.id} className="relative">
              <div className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <span
                    className={cn(
                      "grid size-9 shrink-0 place-items-center rounded-xl",
                      NODE_TONE[node.type] ?? "bg-inset text-ink-muted",
                    )}
                  >
                    <Icon className="size-4" aria-hidden />
                  </span>
                  {!isLast && <span className="my-1 w-px flex-1 bg-line" aria-hidden />}
                </div>

                <div className={cn("min-w-0 flex-1", isLast ? "pb-0" : "pb-5")}>
                  <p className="text-[0.625rem] font-semibold tracking-[0.12em] text-ink-faint uppercase">
                    {node.type.replace(/_/g, " ")}
                  </p>
                  <p className="mt-0.5 font-mono text-[0.8125rem] break-words text-ink">
                    {node.label}
                  </p>

                  {node.details && Object.keys(node.details).length > 0 && (
                    <dl className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                      {Object.entries(node.details)
                        .slice(0, 4)
                        .map(([key, value]) => (
                          <div key={key} className="flex items-baseline gap-1.5">
                            <dt className="text-[0.625rem] text-ink-faint">
                              {key.replace(/_/g, " ")}
                            </dt>
                            <dd className="text-[0.6875rem] text-ink-soft">
                              {typeof value === "object" ? JSON.stringify(value) : String(value)}
                            </dd>
                          </div>
                        ))}
                    </dl>
                  )}

                  {edge && (
                    <p className="mt-1.5 flex items-center gap-1 text-[0.625rem] text-ink-faint">
                      <ArrowDown className="size-3" aria-hidden />
                      {edge.label}
                    </p>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {sql && (
        <div className="mt-4 border-t border-line pt-4">
          <Eyebrow>Compiled SQL</Eyebrow>
          <Code className="mt-1.5">{sql}</Code>
        </div>
      )}
    </div>
  );
}

/** Walk the edges from the node nothing points at, so the chain reads in order. */
function orderNodes(graph: LineageGraph): LineageNode[] {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const targets = new Set(graph.edges.map((edge) => edge.target));
  const root = graph.nodes.find((node) => !targets.has(node.id)) ?? graph.nodes[0];
  if (!root) return graph.nodes;

  const ordered: LineageNode[] = [];
  const seen = new Set<string>();
  let current: LineageNode | undefined = root;

  while (current && !seen.has(current.id)) {
    ordered.push(current);
    seen.add(current.id);
    const edge = graph.edges.find((item) => item.source === current!.id);
    current = edge ? byId.get(edge.target) : undefined;
  }

  // Anything the walk missed (a disconnected node) still gets shown.
  for (const node of graph.nodes) if (!seen.has(node.id)) ordered.push(node);
  return ordered;
}

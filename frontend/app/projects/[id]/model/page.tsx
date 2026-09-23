"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";

import {
  Badge,
  DataTable,
  EmptyState,
  Panel,
  PanelHeader,
  Skeleton,
  Td,
  Tr,
} from "@/components/ui/primitives";
import {
  EntityGraph,
  type Dimension,
  type Measure,
  type Relationship,
} from "@/components/entity-graph";
import { api } from "@/lib/api";

/**
 * Semantic model.
 *
 * The graph is the page: entities, what they carry, and which relationships
 * were proved rather than guessed. A join needs value overlap, type
 * compatibility and uniqueness — a matching column name is never enough.
 */

type Semantic = {
  domain: string;
  summary: string;
  version: number;
  dimensions: Dimension[];
  measures: Measure[];
  relationships: Relationship[];
};

export default function ModelPage() {
  const { id } = useParams<{ id: string }>();
  const semantic = useQuery({
    queryKey: ["semantic", id],
    queryFn: () => api.semantic(id) as Promise<Semantic>,
    retry: false,
  });

  if (semantic.isLoading) return <Skeleton className="h-[30rem] w-full" />;

  if (semantic.isError || !semantic.data) {
    return (
      <EmptyState
        title="No semantic model yet"
        message="Run the pipeline. The profiler binds business roles to columns, then the semantic agent turns them into dimensions, measures and validated relationships."
        icon={<GitBranch className="size-5" />}
      />
    );
  }

  const model = semantic.data;
  const validated = model.relationships.filter((item) => item.validated).length;

  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[0.625rem] font-semibold tracking-[0.14em] text-ink-faint uppercase">
              Inferred domain
            </p>
            <p className="mt-1 text-2xl font-semibold tracking-tight text-ink capitalize">
              {model.domain}
            </p>
            <p className="mt-1 text-[0.8125rem] text-ink-muted">{model.summary}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="brand">version {model.version}</Badge>
            <Badge tone="neutral">{model.dimensions.length} dimensions</Badge>
            <Badge tone="neutral">{model.measures.length} measures</Badge>
            <Badge tone={validated ? "good" : "neutral"}>{validated} validated joins</Badge>
          </div>
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Entity graph"
          subtitle="Drag to pan, use the controls to zoom, click an entity to inspect it"
          icon={<GitBranch className="size-4" />}
        />
        <EntityGraph
          dimensions={model.dimensions}
          measures={model.measures}
          relationships={model.relationships}
        />
      </Panel>

      <Panel>
        <PanelHeader
          title="Validated relationships"
          subtitle="Statistical evidence, not name matching"
        />
        {model.relationships.length === 0 ? (
          <p className="text-[0.8125rem] text-ink-muted">
            No relationships: this project has a single table, so there is nothing to join.
          </p>
        ) : (
          <DataTable
            head={[
              "Source",
              "Target",
              "Cardinality",
              <span key="o" className="block text-right">
                Overlap
              </span>,
              <span key="c" className="block text-right">
                Confidence
              </span>,
              "",
            ]}
          >
            {model.relationships.map((item) => (
              <Tr
                key={`${item.source_table}.${item.source_column}-${item.target_table}.${item.target_column}`}
              >
                <Td className="font-mono text-[0.6875rem]">
                  {item.source_table}.{item.source_column}
                </Td>
                <Td className="font-mono text-[0.6875rem]">
                  {item.target_table}.{item.target_column}
                </Td>
                <Td>
                  <Badge tone="neutral">{item.cardinality.replace(/_/g, "-")}</Badge>
                </Td>
                <Td numeric>
                  {item.overlap_ratio === null ? "—" : `${(item.overlap_ratio * 100).toFixed(1)}%`}
                </Td>
                <Td numeric>{(item.confidence * 100).toFixed(0)}%</Td>
                <Td>
                  <Badge tone={item.validated ? "good" : "warn"}>
                    {item.validated ? "validated" : "candidate"}
                  </Badge>
                </Td>
              </Tr>
            ))}
          </DataTable>
        )}
      </Panel>
    </div>
  );
}

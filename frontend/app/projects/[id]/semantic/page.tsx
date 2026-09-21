"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { Calendar, GitBranch, Hash, MapPin, Tag } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Cell, EmptyState, Field, Row, Table } from "@/components/ui/data";
import { api } from "@/lib/api";

type Semantic = {
  domain: string;
  summary: string;
  version: number;
  dimensions: { name: string; table_name: string; column_name: string; dim_type: string }[];
  measures: {
    name: string;
    table_name: string;
    column_name: string;
    aggregation: string;
    unit: string | null;
  }[];
  relationships: {
    source_table: string;
    source_column: string;
    target_table: string;
    target_column: string;
    cardinality: string;
    confidence: number;
    validated: boolean;
    overlap_ratio: number | null;
  }[];
};

const DIM_ICON: Record<string, typeof Tag> = {
  datetime: Calendar,
  geo: MapPin,
  categorical: Tag,
};

export default function SemanticPage() {
  const { id } = useParams<{ id: string }>();
  const semantic = useQuery({
    queryKey: ["semantic", id],
    queryFn: () => api.semantic(id) as Promise<Semantic>,
    retry: false,
  });

  if (semantic.isError) {
    return (
      <EmptyState
        title="No semantic model yet"
        message="The profiler binds business roles to columns and the semantic agent turns them into dimensions, measures and validated relationships."
        icon={<GitBranch className="size-5" />}
      />
    );
  }

  const model = semantic.data;
  if (!model) return <EmptyState title="Loading…" />;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[0.6875rem] font-semibold tracking-wider text-ink-faint uppercase">
              Inferred domain
            </p>
            <p className="mt-1 text-2xl font-semibold tracking-tight text-ink capitalize">
              {model.domain}
            </p>
            <p className="mt-1 text-[0.8125rem] text-ink-muted">{model.summary}</p>
          </div>
          <Badge tone="brand">version {model.version}</Badge>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Dimensions"
            subtitle="Columns the agent judged safe to group and chart by"
            action={<Badge tone="neutral">{model.dimensions.length}</Badge>}
          />
          {model.dimensions.length === 0 ? (
            <p className="text-[0.8125rem] text-ink-muted">None bound.</p>
          ) : (
            <ul className="space-y-1.5">
              {model.dimensions.map((dimension) => {
                const Icon = DIM_ICON[dimension.dim_type] ?? Tag;
                return (
                  <li
                    key={dimension.name}
                    className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted"
                  >
                    <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
                      <Icon className="size-3.5" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono text-[0.75rem] text-ink-soft">
                      {dimension.name}
                    </span>
                    <Badge tone="neutral">{dimension.dim_type}</Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Measures"
            subtitle="Numeric columns available to aggregate"
            action={<Badge tone="neutral">{model.measures.length}</Badge>}
          />
          {model.measures.length === 0 ? (
            <p className="text-[0.8125rem] text-ink-muted">None bound.</p>
          ) : (
            <ul className="space-y-1.5">
              {model.measures.map((measure) => (
                <li
                  key={measure.name}
                  className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted"
                >
                  <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-[#f6ecfe] text-accent">
                    <Hash className="size-3.5" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1 truncate font-mono text-[0.75rem] text-ink-soft">
                    {measure.name}
                  </span>
                  {measure.unit && <Badge tone="neutral">{measure.unit}</Badge>}
                  <Badge tone="brand">{measure.aggregation}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Validated relationships"
          subtitle="A join needs value overlap, type compatibility and uniqueness — a matching name is never enough."
        />
        {model.relationships.length === 0 ? (
          <p className="text-[0.8125rem] text-ink-muted">
            No relationships: this project has a single table, so nothing to join.
          </p>
        ) : (
          <Table
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
            ]}
          >
            {model.relationships.map((relationship) => (
              <Row
                key={`${relationship.source_table}.${relationship.source_column}-${relationship.target_table}.${relationship.target_column}`}
              >
                <Cell className="font-mono text-[0.6875rem]">
                  {relationship.source_table}.{relationship.source_column}
                </Cell>
                <Cell className="font-mono text-[0.6875rem]">
                  {relationship.target_table}.{relationship.target_column}
                </Cell>
                <Cell>
                  <Badge tone="neutral">{relationship.cardinality.replace(/_/g, "-")}</Badge>
                </Cell>
                <Cell numeric>
                  {relationship.overlap_ratio === null
                    ? "—"
                    : `${(relationship.overlap_ratio * 100).toFixed(1)}%`}
                </Cell>
                <Cell numeric>{(relationship.confidence * 100).toFixed(0)}%</Cell>
              </Row>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

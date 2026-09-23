"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Database, Plug } from "lucide-react";

import {
  Badge,
  Button,
  ComingState,
  Panel,
  PanelHeader,
  Skeleton,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";

/**
 * Connections.
 *
 * File upload is the only ingestion path the backend implements. Rather than
 * mock a database connector that does not exist, this page shows the sources
 * actually attached and states plainly what is not built yet.
 */
export default function ConnectionsPage() {
  const { id } = useParams<{ id: string }>();
  const datasets = useQuery({
    queryKey: ["datasets", id],
    queryFn: () => api.datasets(id),
    retry: false,
  });

  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader
          title="Connected sources"
          subtitle="Where this workspace reads its data from"
          icon={<Plug className="size-4" />}
          action={
            <Link href={`/projects/${id}/datasets`}>
              <Button variant="secondary" size="sm">
                Upload a file
              </Button>
            </Link>
          }
        />
        {datasets.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : datasets.data?.length ? (
          <ul className="space-y-2">
            {datasets.data.map((dataset) => (
              <li
                key={dataset.id}
                className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-raised p-3"
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
                  <Database className="size-4" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.8125rem] font-medium text-ink">
                    {dataset.name}
                  </span>
                  <span className="block truncate font-mono text-[0.625rem] text-ink-faint">
                    {dataset.table_name}
                  </span>
                </span>
                <Badge tone="neutral">{dataset.source_type}</Badge>
                {dataset.row_count != null && (
                  <span className="tnum text-[0.75rem] text-ink-muted">
                    {dataset.row_count.toLocaleString("en-GB")} rows
                  </span>
                )}
                <Badge tone="good" dot>
                  {dataset.layer}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[0.8125rem] text-ink-muted">No sources attached yet.</p>
        )}
      </Panel>

      <ComingState
        title="Live database connectors"
        message="BIFlow ingests uploaded CSV, Parquet and Excel files today. Direct Postgres and REST connectors are not implemented, so nothing here pretends to configure one."
        icon={<Plug className="size-5" />}
      />
    </div>
  );
}

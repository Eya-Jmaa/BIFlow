"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { FileSpreadsheet, Loader2, UploadCloud } from "lucide-react";

import {
  Badge,
  DataTable,
  EmptyState,
  ErrorState,
  Panel,
  PanelHeader,
  Td,
  Tr,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Data ingestion. The raw file is stored unmodified; everything derives from it. */
export default function DatasetsPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const datasets = useQuery({
    queryKey: ["datasets", id],
    queryFn: () => api.datasets(id),
    retry: false,
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDataset(id, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["datasets", id] }),
  });

  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader
          title="Upload data"
          subtitle="CSV, Parquet or Excel. The original file is kept unmodified in the RAW layer."
          icon={<UploadCloud className="size-4" />}
        />

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files?.[0];
            if (file) upload.mutate(file);
          }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-12 text-center",
            "transition-[border-color,background-color] duration-[--duration-base] ease-[--ease-out-soft]",
            dragging
              ? "border-brand bg-brand-soft"
              : "border-line-strong bg-sunken/50 hover:border-brand/40 hover:bg-brand-soft/40",
          )}
        >
          <span className="grid size-12 place-items-center rounded-2xl bg-surface text-brand shadow-card">
            {upload.isPending ? (
              <Loader2 className="size-5 animate-spin" aria-hidden />
            ) : (
              <UploadCloud className="size-5" aria-hidden />
            )}
          </span>
          <p className="mt-3.5 text-[0.875rem] font-medium text-ink">
            {upload.isPending ? "Uploading…" : "Drop a file here, or click to browse"}
          </p>
          <p className="mt-1 text-[0.75rem] text-ink-muted">.csv · .parquet · .xlsx · .xls</p>
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            accept=".csv,.parquet,.xlsx,.xls"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) upload.mutate(file);
              event.target.value = "";
            }}
          />
        </div>

        {upload.error && (
          <ErrorState
            className="mt-3"
            title="BIFlow couldn't read that file."
            reason={(upload.error as Error).message}
          />
        )}
      </Panel>

      <Panel>
        <PanelHeader
          title="Attached datasets"
          subtitle={
            datasets.data?.length
              ? `${datasets.data.length} source${datasets.data.length > 1 ? "s" : ""} — row and column counts appear after profiling`
              : undefined
          }
        />
        {datasets.data?.length === 0 ? (
          <EmptyState
            title="Nothing uploaded yet"
            message="BIFlow needs a dataset before the pipeline can run."
            icon={<FileSpreadsheet className="size-5" />}
          />
        ) : (
          <DataTable
            head={[
              "Name",
              "Table",
              "Type",
              <span key="r" className="block text-right">
                Rows
              </span>,
              <span key="c" className="block text-right">
                Columns
              </span>,
              "Layer",
            ]}
          >
            {datasets.data?.map((dataset) => (
              <Tr key={dataset.id}>
                <Td className="font-medium text-ink">{dataset.name}</Td>
                <Td className="font-mono text-[0.6875rem]">{dataset.table_name}</Td>
                <Td className="uppercase">{dataset.source_type}</Td>
                <Td numeric>
                  {dataset.row_count === null ? "—" : dataset.row_count.toLocaleString("en-GB")}
                </Td>
                <Td numeric>{dataset.column_count ?? "—"}</Td>
                <Td>
                  <Badge tone="neutral">{dataset.layer}</Badge>
                </Td>
              </Tr>
            ))}
          </DataTable>
        )}
      </Panel>
    </div>
  );
}

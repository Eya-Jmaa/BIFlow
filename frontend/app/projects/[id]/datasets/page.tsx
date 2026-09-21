"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { FileSpreadsheet, Loader2, UploadCloud } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Cell, EmptyState, Row, Table } from "@/components/ui/data";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function DatasetsPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const datasets = useQuery({ queryKey: ["datasets", id], queryFn: () => api.datasets(id) });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDataset(id, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["datasets", id] }),
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Upload data"
          subtitle="CSV, Parquet or Excel. The original file is stored unmodified in the RAW layer."
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
            "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
            dragging
              ? "border-brand bg-brand-soft"
              : "border-line-strong bg-surface-muted/60 hover:border-brand/40 hover:bg-brand-soft/40",
          )}
        >
          <span className="grid size-11 place-items-center rounded-2xl bg-surface text-brand shadow-card">
            {upload.isPending ? (
              <Loader2 className="size-5 animate-spin" aria-hidden />
            ) : (
              <UploadCloud className="size-5" aria-hidden />
            )}
          </span>
          <p className="mt-3 text-sm font-medium text-ink">
            {upload.isPending ? "Uploading…" : "Drop a file here, or click to browse"}
          </p>
          <p className="mt-1 text-xs text-ink-muted">.csv · .parquet · .xlsx · .xls</p>
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
          <p className="mt-3 rounded-lg bg-bad-soft px-3 py-2 text-[0.8125rem] text-bad">
            {(upload.error as Error).message}
          </p>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Uploaded files"
          subtitle={
            datasets.data?.length
              ? `${datasets.data.length} dataset${datasets.data.length > 1 ? "s" : ""}`
              : undefined
          }
        />
        {datasets.data?.length === 0 ? (
          <EmptyState
            title="Nothing uploaded yet"
            message="Row and column counts appear here once the profiler has run."
            icon={<FileSpreadsheet className="size-5" />}
          />
        ) : (
          <Table
            head={[
              "Name",
              "Table",
              "Type",
              <span key="rows" className="block text-right">
                Rows
              </span>,
              <span key="cols" className="block text-right">
                Columns
              </span>,
              "Layer",
            ]}
          >
            {datasets.data?.map((dataset) => (
              <Row key={dataset.id}>
                <Cell className="font-medium text-ink">{dataset.name}</Cell>
                <Cell className="font-mono text-[0.6875rem]">{dataset.table_name}</Cell>
                <Cell className="uppercase">{dataset.source_type}</Cell>
                <Cell numeric>
                  {dataset.row_count === null
                    ? "—"
                    : dataset.row_count.toLocaleString("en-GB")}
                </Cell>
                <Cell numeric>{dataset.column_count ?? "—"}</Cell>
                <Cell>
                  <Badge tone="neutral">{dataset.layer}</Badge>
                </Cell>
              </Row>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}

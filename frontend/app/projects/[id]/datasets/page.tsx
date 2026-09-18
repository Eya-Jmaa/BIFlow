"use client";

import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function DatasetsPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const datasets = useQuery({ queryKey: ["datasets", id], queryFn: () => api.datasets(id) });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDataset(id, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["datasets", id] }),
  });

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="text-sm font-semibold">Upload datasets</h2>
        <p className="mt-1 text-sm text-slate-400">CSV, Parquet or Excel. Original files are stored unmodified in the RAW layer.</p>
        <input
          className="mt-3 block text-sm"
          type="file"
          accept=".csv,.parquet,.xlsx,.xls"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file);
          }}
        />
        {upload.error && <p className="mt-2 text-sm text-red-400">{(upload.error as Error).message}</p>}
      </Card>
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Uploaded files</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="pb-2">Name</th>
                <th>Type</th>
                <th>Rows</th>
                <th>Columns</th>
                <th>Layer</th>
              </tr>
            </thead>
            <tbody>
              {datasets.data?.map((ds) => (
                <tr key={ds.id} className="border-t border-slate-800">
                  <td className="py-2">{ds.name}</td>
                  <td>{ds.source_type}</td>
                  <td>{ds.row_count ?? "—"}</td>
                  <td>{ds.column_count ?? "—"}</td>
                  <td>{ds.layer}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {datasets.data?.length === 0 && <p className="mt-3 text-sm text-slate-500">No datasets uploaded.</p>}
        </div>
      </Card>
    </div>
  );
}

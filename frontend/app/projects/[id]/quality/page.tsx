"use client";

import { Card } from "@/components/ui/card";
import { Badge, statusTone } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

type Report = {
  id: string;
  overall_score: number;
  completeness: number;
  uniqueness: number;
  consistency: number;
  validity: number;
  referential_integrity: number;
  summary: string | null;
  issues: Array<{
    id: string;
    severity: string;
    issue_type: string;
    table_name: string | null;
    column_name: string | null;
    rows_affected: number;
    detection_method: string;
    recommended_action: string;
    status: string;
  }>;
};

export default function QualityPage() {
  const { id } = useParams<{ id: string }>();
  const quality = useQuery({ queryKey: ["quality", id], queryFn: () => api.quality(id), retry: false });
  const transforms = useQuery({ queryKey: ["transforms", id], queryFn: () => api.transformations(id), retry: false });
  const reports = (quality.data || []) as Report[];

  if (quality.isError) {
    return <EmptyState message="Data quality is not available yet. Run the pipeline after uploading datasets." />;
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        {reports.map((report) => (
          <Card key={report.id}>
            <p className="text-xs uppercase text-slate-500">Overall score</p>
            <p className="text-3xl font-semibold">{report.overall_score}</p>
            <dl className="mt-3 grid grid-cols-2 gap-1 text-xs text-slate-400">
              <div>Completeness {report.completeness}</div>
              <div>Uniqueness {report.uniqueness}</div>
              <div>Consistency {report.consistency}</div>
              <div>Validity {report.validity}</div>
              <div>Referential {report.referential_integrity}</div>
            </dl>
          </Card>
        ))}
      </div>
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Issues</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="pb-2">Severity</th>
                <th>Type</th>
                <th>Table</th>
                <th>Column</th>
                <th>Rows</th>
                <th>Method</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {reports.flatMap((r) => r.issues).map((issue) => (
                <tr key={issue.id} className="border-t border-slate-800">
                  <td className="py-2">
                    <Badge tone={statusTone(issue.severity)}>{issue.severity}</Badge>
                  </td>
                  <td>{issue.issue_type}</td>
                  <td>{issue.table_name}</td>
                  <td>{issue.column_name}</td>
                  <td>{issue.rows_affected}</td>
                  <td>{issue.detection_method}</td>
                  <td className="max-w-xs text-slate-400">{issue.recommended_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Transformation lineage</h2>
        <ul className="space-y-2 text-sm">
          {((transforms.data as Array<Record<string, unknown>>) || []).map((t) => (
            <li key={String(t.id)} className="border-b border-slate-800 pb-2">
              <span className="font-medium">{String(t.operation)}</span> on {String(t.table_name)}
              {t.column_name ? `.${String(t.column_name)}` : ""} · {String(t.rows_affected)} rows
              <p className="text-xs text-slate-500">{String(t.reason)}</p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return <Card><p className="text-sm text-slate-400">{message}</p></Card>;
}

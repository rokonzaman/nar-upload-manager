"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, downloadFile } from "@/lib/api";
import type { AuditLogOut, Page } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/data-table";
import { ResultBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Download } from "lucide-react";

export default function AuditPage() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ username: "", action: "", result: "", target_server: "", q: "" });

  const params = {
    page,
    page_size: 20,
    username: filters.username || undefined,
    action: filters.action || undefined,
    result: filters.result || undefined,
    target_server: filters.target_server || undefined,
    q: filters.q || undefined,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", params],
    queryFn: () => api.get<Page<AuditLogOut>>("/audit-logs/", params),
  });

  const { data: actions } = useQuery({
    queryKey: ["audit-actions"],
    queryFn: () => api.get<string[]>("/audit-logs/actions"),
  });

  const exportCsv = async () => {
    try {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) query.set(key, String(value));
      }
      await downloadFile(`/audit-logs/export?${query.toString()}`, "audit_logs.csv");
      toast.success("Audit log exported");
    } catch (error) {
      toast.error((error as Error).message);
    }
  };

  const setFilter = (key: keyof typeof filters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit Logs"
        description="Every action performed in the system — searchable and exportable"
        actions={
          <Button variant="outline" onClick={exportCsv}>
            <Download className="h-4 w-4" /> Export CSV
          </Button>
        }
      />

      <div className="flex flex-wrap gap-3">
        <Input placeholder="Username" value={filters.username} onChange={(e) => setFilter("username", e.target.value)} className="w-40" />
        <Select value={filters.action || "all"} onValueChange={(v) => setFilter("action", v === "all" ? "" : v)}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Action" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actions</SelectItem>
            {(actions ?? []).map((action) => (
              <SelectItem key={action} value={action}>
                {action}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filters.result || "all"} onValueChange={(v) => setFilter("result", v === "all" ? "" : v)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Result" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All results</SelectItem>
            <SelectItem value="success">Success</SelectItem>
            <SelectItem value="failure">Failure</SelectItem>
          </SelectContent>
        </Select>
        <Input placeholder="Server" value={filters.target_server} onChange={(e) => setFilter("target_server", e.target.value)} className="w-36" />
        <Input placeholder="Full-text search" value={filters.q} onChange={(e) => setFilter("q", e.target.value)} className="w-52" />
      </div>

      <DataTable
        loading={isLoading}
        data={data?.items}
        page={data}
        onPageChange={setPage}
        rowKey={(a) => a.id}
        columns={[
          {
            key: "timestamp",
            header: "Timestamp",
            cell: (a) => <span className="text-sm text-muted-foreground whitespace-nowrap">{formatDate(a.timestamp)}</span>,
          },
          {
            key: "user",
            header: "User",
            cell: (a) => (
              <div>
                <p className="font-medium">{a.username}</p>
                {a.full_name && <p className="text-xs text-muted-foreground">{a.full_name}</p>}
              </div>
            ),
          },
          { key: "action", header: "Action", cell: (a) => <span className="font-mono text-sm">{a.action}</span> },
          {
            key: "target",
            header: "Target",
            cell: (a) => (
              <div className="text-sm">
                {a.bundle && (
                  <p>
                    {a.bundle}
                    {a.version ? `:${a.version}` : ""}
                  </p>
                )}
                {a.target_server && <p className="text-muted-foreground">{a.target_server}</p>}
                {a.resource_type && !a.bundle && !a.target_server && (
                  <p className="text-muted-foreground">
                    {a.resource_type}
                    {a.resource_id ? `#${a.resource_id}` : ""}
                  </p>
                )}
              </div>
            ),
          },
          { key: "result", header: "Result", cell: (a) => <ResultBadge result={a.result} /> },
          { key: "ip", header: "IP", cell: (a) => <span className="font-mono text-xs">{a.ip_address ?? "—"}</span> },
          {
            key: "details",
            header: "Details",
            cell: (a) => (
              <span className="text-xs text-muted-foreground line-clamp-2 max-w-xs block" title={a.error_message ?? a.details ?? ""}>
                {a.error_message ?? a.details ?? "—"}
              </span>
            ),
          },
        ]}
      />
    </div>
  );
}

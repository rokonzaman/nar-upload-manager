"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { RetentionPolicyOut, RetentionPreview, RetentionRunOut, Page } from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { formatBytes, formatRelative } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Pin, Play, ShieldCheck, Trash2 } from "lucide-react";

const policySchema = z.object({
  keep_latest: z.coerce.number().int().min(0),
  keep_days: z.coerce.number().int().min(0),
  is_enabled: z.boolean(),
  dry_run: z.boolean(),
  schedule: z.string().min(1),
});

type PolicyForm = z.infer<typeof policySchema>;

export default function RetentionPage() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<RetentionPreview | null>(null);
  const [executeOpen, setExecuteOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [runsPage, setRunsPage] = useState(1);

  const { data: policy, isLoading } = useQuery({
    queryKey: ["retention-policy"],
    queryFn: () => api.get<RetentionPolicyOut>("/retention/policy"),
  });

  const { data: runs } = useQuery({
    queryKey: ["retention-runs", runsPage],
    queryFn: () => api.get<Page<RetentionRunOut>>("/retention/runs", { page: runsPage, page_size: 10 }),
  });

  const form = useForm<PolicyForm>({
    resolver: zodResolver(policySchema),
    values: policy
      ? {
          keep_latest: policy.keep_latest,
          keep_days: policy.keep_days,
          is_enabled: policy.is_enabled,
          dry_run: policy.dry_run,
          schedule: policy.schedule,
        }
      : undefined,
  });

  const saveMutation = useMutation({
    mutationFn: (values: PolicyForm) => api.put("/retention/policy", values),
    onSuccess: () => {
      toast.success("Retention policy saved");
      queryClient.invalidateQueries({ queryKey: ["retention-policy"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const previewMutation = useMutation({
    mutationFn: () => api.post<RetentionPreview>("/retention/preview"),
    onSuccess: setPreview,
    onError: (error) => toast.error(error.message),
  });

  const executeMutation = useMutation({
    mutationFn: (dryRun: boolean) => api.post<RetentionRunOut>("/retention/execute", { dry_run: dryRun, confirm: !dryRun }),
    onSuccess: (run) => {
      toast.success(
        run.dry_run
          ? `Dry run: ${run.deleted_count} bundle(s) would be deleted`
          : `Deleted ${run.deleted_count} bundle(s), freed ${formatBytes(run.freed_bytes)}`,
      );
      setExecuteOpen(false);
      setConfirmText("");
      setPreview(null);
      queryClient.invalidateQueries({ queryKey: ["retention-runs"] });
      queryClient.invalidateQueries({ queryKey: ["bundles-grouped"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Retention Policy" description="Automatic cleanup of old NAR versions — pinned and deployed bundles are always protected" />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Policy</CardTitle>
            <CardDescription>
              Keep the latest N versions per artifact and anything newer than X days. Scheduled cleanup runs via cron.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading || !policy ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <form onSubmit={form.handleSubmit((v) => saveMutation.mutate(v))} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="keep_latest">Keep latest versions</Label>
                    <Input id="keep_latest" type="number" min={0} {...form.register("keep_latest")} disabled={!isAdmin} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="keep_days">Keep newer than (days)</Label>
                    <Input id="keep_days" type="number" min={0} {...form.register("keep_days")} disabled={!isAdmin} />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="schedule">Cleanup schedule (cron)</Label>
                  <Input id="schedule" {...form.register("schedule")} disabled={!isAdmin} />
                  <p className="text-xs text-muted-foreground">e.g. <code>0 0 * * 0</code> = Sundays at midnight (UTC)</p>
                </div>
                <div className="flex gap-6">
                  <label className="flex items-center gap-2 text-sm">
                    <Switch checked={form.watch("is_enabled")} onCheckedChange={(v) => form.setValue("is_enabled", v)} disabled={!isAdmin} />
                    Enabled
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <Switch checked={form.watch("dry_run")} onCheckedChange={(v) => form.setValue("dry_run", v)} disabled={!isAdmin} />
                    Scheduled runs are dry runs
                  </label>
                </div>
                <p className="text-xs text-muted-foreground">Last run: {policy.last_run_at ? formatRelative(policy.last_run_at) : "never"}</p>
                {isAdmin && (
                  <div className="flex gap-2">
                    <Button type="submit" disabled={saveMutation.isPending}>
                      Save policy
                    </Button>
                    <Button type="button" variant="outline" onClick={() => previewMutation.mutate()} disabled={previewMutation.isPending}>
                      Preview cleanup
                    </Button>
                    <Button type="button" variant="destructive" onClick={() => setExecuteOpen(true)}>
                      <Play className="h-4 w-4" /> Execute
                    </Button>
                  </div>
                )}
              </form>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Run history</CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable
              data={runs?.items}
              page={runs}
              onPageChange={setRunsPage}
              rowKey={(r) => r.id}
              columns={[
                { key: "id", header: "#", cell: (r) => r.id, className: "w-12" },
                { key: "started", header: "Started", cell: (r) => formatRelative(r.started_at) },
                { key: "by", header: "Triggered by", cell: (r) => r.triggered_by },
                {
                  key: "mode",
                  header: "Mode",
                  cell: (r) => (r.dry_run ? <Badge variant="secondary">dry run</Badge> : <Badge variant="destructive">live</Badge>),
                },
                { key: "deleted", header: "Deleted", cell: (r) => r.deleted_count },
                { key: "freed", header: "Freed", cell: (r) => formatBytes(r.freed_bytes) },
              ]}
            />
          </CardContent>
        </Card>
      </div>

      {preview && (
        <Card>
          <CardHeader>
            <CardTitle>Cleanup preview</CardTitle>
            <CardDescription>
              {preview.total_count} bundle(s) would be deleted, freeing {formatBytes(preview.total_size_bytes)}. Protected
              entries are shown for reference.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Bundle</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Uploaded</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.candidates.map((c) => (
                  <TableRow key={c.bundle_id} className={c.protected ? "opacity-60" : ""}>
                    <TableCell className="font-medium">
                      {c.artifact} <span className="font-mono text-muted-foreground">{c.version}</span>
                    </TableCell>
                    <TableCell>{formatBytes(c.file_size)}</TableCell>
                    <TableCell>{formatRelative(c.uploaded_at)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{c.reason}</TableCell>
                    <TableCell>
                      {c.protected ? (
                        <Badge variant="secondary" className="gap-1">
                          <ShieldCheck className="h-3 w-3" /> {c.reason === "Pinned version" ? <Pin className="h-3 w-3" /> : null}
                          protected
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-red-500 border-red-500/30 gap-1">
                          <Trash2 className="h-3 w-3" /> delete
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Execute dialog */}
      <Dialog open={executeOpen} onOpenChange={setExecuteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Execute retention cleanup</DialogTitle>
            <DialogDescription>
              Run a dry run first to review what would be deleted. Live deletion requires confirmation.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Button variant="outline" className="w-full" onClick={() => executeMutation.mutate(true)} disabled={executeMutation.isPending}>
              Dry run (no changes)
            </Button>
            <div className="space-y-2">
              <Label htmlFor="confirm">
                Type <span className="font-mono font-bold">DELETE</span> to enable live cleanup
              </Label>
              <Input id="confirm" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
            </div>
            <Button
              variant="destructive"
              className="w-full"
              disabled={confirmText !== "DELETE" || executeMutation.isPending}
              onClick={() => executeMutation.mutate(false)}
            >
              <Trash2 className="h-4 w-4" /> Delete now (live)
            </Button>
          </div>
          <DialogFooter />
        </DialogContent>
      </Dialog>
    </div>
  );
}

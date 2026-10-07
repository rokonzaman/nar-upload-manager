"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { BackupOut, Page } from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { formatBytes, formatRelative } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/data-table";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ArchiveRestore, Loader2, RotateCcw, Trash2 } from "lucide-react";

export default function BackupsPage() {
  const { isAdmin, isDeveloper } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [restoring, setRestoring] = useState<BackupOut | null>(null);
  const [deleting, setDeleting] = useState<BackupOut | null>(null);
  const [cleanupConfirm, setCleanupConfirm] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["backups", page, search],
    queryFn: () => api.get<Page<BackupOut>>("/backups/", { page, page_size: 15, q: search || undefined }),
  });

  const restoreMutation = useMutation({
    mutationFn: (id: number) => api.post(`/backups/${id}/restore`),
    onSuccess: () => {
      toast.success("Backup restored to server");
      setRestoring(null);
      queryClient.invalidateQueries({ queryKey: ["backups"] });
    },
    onError: (error) => {
      toast.error(error.message);
      setRestoring(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/backups/${id}`),
    onSuccess: () => {
      toast.success("Backup deleted");
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["backups"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const cleanupMutation = useMutation({
    mutationFn: () => api.post<{ deleted: number; freed_bytes: number }>("/backups/cleanup-orphans"),
    onSuccess: (result) => {
      toast.success(`Removed ${result.deleted} orphaned backup(s), freed ${formatBytes(result.freed_bytes)}`);
      setCleanupConfirm(false);
      queryClient.invalidateQueries({ queryKey: ["backups"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Backups"
        description="Files backed up before deployments replaced them — restore with one click"
        actions={
          isAdmin ? (
            <Button variant="outline" onClick={() => setCleanupConfirm(true)}>
              <Trash2 className="h-4 w-4" /> Cleanup orphans
            </Button>
          ) : undefined
        }
      />

      <Input
        placeholder="Search backups…"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
        className="sm:max-w-xs"
      />

      <DataTable
        loading={isLoading}
        data={data?.items}
        page={data}
        onPageChange={setPage}
        rowKey={(b) => b.id}
        emptyState={
          <EmptyState
            icon={ArchiveRestore}
            title="No backups yet"
            description="Backups are created automatically when a deployment replaces an existing file on a server."
          />
        }
        columns={[
          {
            key: "filename",
            header: "File",
            cell: (b) => (
              <div>
                <p className="font-medium font-mono text-sm">{b.filename}</p>
                <p className="text-xs text-muted-foreground font-mono truncate max-w-xs">{b.original_path}</p>
              </div>
            ),
          },
          { key: "server", header: "Server", cell: (b) => b.server_name ?? "—" },
          {
            key: "bundle",
            header: "Bundle",
            cell: (b) =>
              b.bundle_artifact ? (
                <span>
                  {b.bundle_artifact} <span className="font-mono text-muted-foreground">{b.bundle_version}</span>
                </span>
              ) : (
                "—"
              ),
          },
          { key: "size", header: "Size", cell: (b) => formatBytes(b.file_size) },
          { key: "created", header: "Created", cell: (b) => formatRelative(b.created_at) },
          {
            key: "restored",
            header: "Restored",
            cell: (b) =>
              b.restored_at ? <Badge variant="secondary">{formatRelative(b.restored_at)}</Badge> : <span className="text-muted-foreground">—</span>,
          },
          {
            key: "actions",
            header: "",
            className: "w-24",
            cell: (b) => (
              <div className="flex gap-1">
                {isDeveloper && (
                  <Button variant="ghost" size="icon" title="Restore" onClick={() => setRestoring(b)}>
                    <RotateCcw className="h-4 w-4 text-amber-500" />
                  </Button>
                )}
                {isAdmin && (
                  <Button variant="ghost" size="icon" title="Delete" onClick={() => setDeleting(b)}>
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                )}
              </div>
            ),
          },
        ]}
      />

      <Dialog open={!!restoring} onOpenChange={(open) => !open && !restoreMutation.isPending && setRestoring(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {restoreMutation.isPending ? "Restoring backup…" : `Restore ${restoring?.filename}?`}
            </DialogTitle>
            <DialogDescription>
              {restoreMutation.isPending
                ? `Uploading ${restoring?.filename} to ${restoring?.server_name} via SFTP…`
                : `The backup will be uploaded to ${restoring?.original_path} on ${restoring?.server_name}, replacing the current file. Checksum is verified after restore.`}
            </DialogDescription>
          </DialogHeader>
          {restoreMutation.isPending ? (
            <div className="flex flex-col items-center gap-3 py-6">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">This may take a moment for large files.</p>
            </div>
          ) : (
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setRestoring(null)}>Cancel</Button>
              <Button onClick={() => restoring && restoreMutation.mutate(restoring.id)}>Restore</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete backup ${deleting?.filename}?`}
        description="The backup file and its record will be permanently removed."
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />

      <ConfirmDialog
        open={cleanupConfirm}
        onOpenChange={setCleanupConfirm}
        title="Clean up orphaned backups?"
        description="Removes backup records whose server no longer exists or whose file is missing on disk."
        confirmLabel="Clean up"
        onConfirm={() => cleanupMutation.mutate()}
      />
    </div>
  );
}

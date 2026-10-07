"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, downloadFile } from "@/lib/api";
import type { BundleGroup, NarBundleOut, Page } from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { formatBytes, formatDate, formatRelative } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { BundleStatusBadge } from "@/components/status-badge";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  GitCompareArrows,
  Package,
  Pencil,
  Pin,
  Search,
  Trash2,
} from "lucide-react";

export default function RepositoryPage() {
  const { isDeveloper } = useAuth();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [view, setView] = useState<"grouped" | "flat">("grouped");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [detail, setDetail] = useState<NarBundleOut | null>(null);
  const [editing, setEditing] = useState<NarBundleOut | null>(null);
  const [comparing, setComparing] = useState<NarBundleOut[]>([]);
  const [deleting, setDeleting] = useState<NarBundleOut | null>(null);
  const [bulkConfirm, setBulkConfirm] = useState(false);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("uploaded_at");

  const { data: grouped, isLoading: groupedLoading } = useQuery({
    queryKey: ["bundles-grouped"],
    queryFn: () => api.get<BundleGroup[]>("/bundles/grouped"),
    enabled: view === "grouped",
  });

  const { data: flat, isLoading: flatLoading } = useQuery({
    queryKey: ["bundles-flat", page, search, statusFilter, sortBy],
    queryFn: () =>
      api.get<Page<NarBundleOut>>("/bundles/", {
        page,
        page_size: 15,
        q: search || undefined,
        status: statusFilter || undefined,
        sort_by: sortBy,
        sort_order: sortBy === "artifact" ? "asc" : "desc",
      }),
    enabled: view === "flat",
  });

  const { data: compareResult } = useQuery({
    queryKey: ["compare", comparing[0]?.id, comparing[1]?.id],
    queryFn: () =>
      api.post<{
        bundle_a: NarBundleOut;
        bundle_b: NarBundleOut;
        same_checksum: boolean;
        size_diff_bytes: number;
        manifest_diff: { added: Record<string, string>; removed: Record<string, string>; changed: Record<string, string> };
      }>("/bundles/compare", { id_a: comparing[0].id, id_b: comparing[1].id }),
    enabled: comparing.length === 2,
  });

  const filteredGroups = useMemo(() => {
    if (!grouped) return [];
    const q = search.toLowerCase();
    return grouped
      .map((group) => ({
        ...group,
        versions: group.versions.filter(
          (v) =>
            (!q || v.artifact.toLowerCase().includes(q) || v.version.includes(q) || v.bundle_group.toLowerCase().includes(q)) &&
            (!statusFilter || v.status === statusFilter),
        ),
      }))
      .filter((group) => group.versions.length > 0);
  }, [grouped, search, statusFilter]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["bundles-grouped"] });
    queryClient.invalidateQueries({ queryKey: ["bundles-flat"] });
  };

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/bundles/${id}`),
    onSuccess: () => {
      toast.success("Bundle deleted");
      setDeleting(null);
      invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: number[]) => api.post<{ succeeded: number[]; failed: Record<string, string> }>("/bundles/bulk-delete", { ids }),
    onSuccess: (result) => {
      toast.success(`Deleted ${result.succeeded.length} bundle(s)`);
      const failedCount = Object.keys(result.failed).length;
      if (failedCount > 0) toast.warning(`${failedCount} could not be deleted (pinned or deployed)`);
      setSelected(new Set());
      setBulkConfirm(false);
      invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...payload }: { id: number; tags?: string; description?: string; status?: string; is_pinned?: boolean }) =>
      api.put(`/bundles/${id}`, payload),
    onSuccess: () => {
      toast.success("Bundle updated");
      setEditing(null);
      invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleCompare = (bundle: NarBundleOut) => {
    setComparing((prev) => {
      if (prev.some((b) => b.id === bundle.id)) return prev.filter((b) => b.id !== bundle.id);
      if (prev.length >= 2) return [prev[1], bundle];
      return [...prev, bundle];
    });
  };

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const bundleRow = (bundle: NarBundleOut, showArtifact: boolean) => (
    <TableRow key={bundle.id} data-state={selected.has(bundle.id) ? "selected" : undefined}>
      {isDeveloper && (
        <TableCell className="w-8">
          <Checkbox checked={selected.has(bundle.id)} onCheckedChange={() => toggleSelect(bundle.id)} />
        </TableCell>
      )}
      {showArtifact && (
        <TableCell>
          <div className="flex items-center gap-2">
            <span className="font-medium">{bundle.artifact}</span>
            {bundle.is_pinned && <Pin className="h-3 w-3 text-amber-500" />}
          </div>
          <span className="text-xs text-muted-foreground">{bundle.bundle_group}</span>
        </TableCell>
      )}
      <TableCell className="font-mono text-sm">
        <div className="flex items-center gap-2">
          {bundle.version}
          {bundle.is_pinned && !showArtifact && <Pin className="h-3 w-3 text-amber-500" />}
        </div>
      </TableCell>
      <TableCell>{formatBytes(bundle.file_size)}</TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {bundle.tags
            .split(",")
            .filter(Boolean)
            .map((tag) => (
              <Badge key={tag} variant="secondary" className="text-xs">
                {tag.trim()}
              </Badge>
            ))}
        </div>
      </TableCell>
      <TableCell>
        <BundleStatusBadge status={bundle.status} />
      </TableCell>
      <TableCell>
        <Tooltip>
          <TooltipTrigger className="text-sm text-muted-foreground">{formatRelative(bundle.uploaded_at)}</TooltipTrigger>
          <TooltipContent>{formatDate(bundle.uploaded_at)}</TooltipContent>
        </Tooltip>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={() => downloadFile(`/bundles/${bundle.id}/download`, bundle.filename)}>
                <Download className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Download</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={() => setDetail(bundle)}>
                <Search className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Details</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => toggleCompare(bundle)}
                className={comparing.some((b) => b.id === bundle.id) ? "text-primary" : ""}
              >
                <GitCompareArrows className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Compare</TooltipContent>
          </Tooltip>
          {isDeveloper && (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" onClick={() => setEditing(bundle)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Edit</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" onClick={() => setDeleting(bundle)}>
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Delete</TooltipContent>
              </Tooltip>
            </>
          )}
        </div>
      </TableCell>
    </TableRow>
  );

  const isLoading = view === "grouped" ? groupedLoading : flatLoading;

  return (
    <div className="space-y-6">
      <PageHeader title="NAR Repository" description="Browse, search and manage uploaded NAR bundles" />

      <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
        <div className="relative sm:max-w-xs flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search bundles…" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
        <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
          <SelectTrigger className="sm:w-36">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="deprecated">Deprecated</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
        {view === "flat" && (
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="sm:w-40">
              <SelectValue placeholder="Sort by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="uploaded_at">Upload date</SelectItem>
              <SelectItem value="file_size">Size</SelectItem>
              <SelectItem value="version">Version</SelectItem>
              <SelectItem value="artifact">Artifact</SelectItem>
            </SelectContent>
          </Select>
        )}
        <div className="flex gap-1 rounded-md border p-1 sm:ml-auto">
          <Button variant={view === "grouped" ? "secondary" : "ghost"} size="sm" onClick={() => setView("grouped")}>
            Grouped
          </Button>
          <Button variant={view === "flat" ? "secondary" : "ghost"} size="sm" onClick={() => setView("flat")}>
            Flat
          </Button>
        </div>
      </div>

      {selected.size > 0 && isDeveloper && (
        <div className="flex items-center gap-3 rounded-md border bg-muted/50 p-3">
          <span className="text-sm">{selected.size} selected</span>
          <Button size="sm" variant="destructive" onClick={() => setBulkConfirm(true)}>
            <Trash2 className="h-4 w-4" /> Delete selected
          </Button>
          <Button size="sm" variant="outline" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      )}

      {comparing.length > 0 && (
        <div className="flex items-center gap-3 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
          <GitCompareArrows className="h-4 w-4 text-primary" />
          {comparing.length === 1 ? (
            <span>Select one more version to compare with {comparing[0].artifact}:{comparing[0].version}</span>
          ) : (
            <span>
              Comparing {comparing[0].version} ↔ {comparing[1].version}
            </span>
          )}
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setComparing([])}>
            Cancel
          </Button>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : view === "grouped" ? (
        filteredGroups.length === 0 ? (
          <EmptyState icon={Package} title="No bundles found" description="Upload your first NAR bundle to get started." />
        ) : (
          <div className="space-y-3">
            {filteredGroups.map((group) => {
              const key = `${group.bundle_group}:${group.artifact}`;
              const isOpen = expanded.has(key);
              return (
                <div key={key} className="rounded-md border">
                  <button
                    className="flex w-full items-center gap-3 p-4 text-left hover:bg-muted/50 transition-colors"
                    onClick={() => toggleExpand(key)}
                  >
                    {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    <Package className="h-5 w-5 text-primary" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{group.artifact}</p>
                      <p className="text-xs text-muted-foreground truncate">{group.bundle_group}</p>
                    </div>
                    <Badge variant="secondary">{group.versions.length} version{group.versions.length > 1 ? "s" : ""}</Badge>
                    <Badge variant="outline">latest {group.latest_version}</Badge>
                    <span className="text-xs text-muted-foreground">{formatBytes(group.total_size)}</span>
                  </button>
                  {isOpen && (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {isDeveloper && <TableHead className="w-8" />}
                          <TableHead>Version</TableHead>
                          <TableHead>Size</TableHead>
                          <TableHead>Tags</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Uploaded</TableHead>
                          <TableHead />
                        </TableRow>
                      </TableHeader>
                      <TableBody>{group.versions.map((v) => bundleRow(v, false))}</TableBody>
                    </Table>
                  )}
                </div>
              );
            })}
          </div>
        )
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                {isDeveloper && <TableHead className="w-8" />}
                <TableHead>Artifact</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Tags</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>{flat?.items.map((v) => bundleRow(v, true))}</TableBody>
          </Table>
          {flat && flat.pages > 1 && (
            <div className="flex items-center justify-between p-3 text-sm text-muted-foreground border-t">
              <span>
                page {flat.page} of {flat.pages} ({flat.total} bundles)
              </span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  Previous
                </Button>
                <Button variant="outline" size="sm" disabled={page >= flat.pages} onClick={() => setPage(page + 1)}>
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Detail dialog */}
      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{detail?.artifact}</DialogTitle>
            <DialogDescription>
              {detail?.bundle_group}:{detail?.version}
            </DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm">
              {[
                ["Filename", detail.filename],
                ["Size", formatBytes(detail.file_size)],
                ["Uploaded by", detail.uploaded_by],
                ["Uploaded at", formatDate(detail.uploaded_at)],
                ["Build date", formatDate(detail.build_date)],
                ["Source", detail.source],
              ].map(([label, value]) => (
                <div key={label} className="grid grid-cols-3 gap-2">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="col-span-2 break-all">{value}</span>
                </div>
              ))}
              {["sha256", "md5"].map((key) => (
                <div key={key} className="grid grid-cols-3 gap-2">
                  <span className="text-muted-foreground uppercase">{key}</span>
                  <span className="col-span-2 font-mono text-xs break-all flex items-center gap-2">
                    {detail[key as "sha256" | "md5"]}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0"
                      onClick={() => {
                        navigator.clipboard.writeText(detail[key as "sha256" | "md5"]);
                        toast.success("Checksum copied");
                      }}
                    >
                      <Copy className="h-3 w-3" />
                    </Button>
                  </span>
                </div>
              ))}
              {detail.description && <p className="text-muted-foreground border-t pt-3">{detail.description}</p>}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit {editing?.artifact}:{editing?.version}</DialogTitle>
          </DialogHeader>
          {editing && (
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                updateMutation.mutate({
                  id: editing.id,
                  tags: String(form.get("tags") ?? ""),
                  description: String(form.get("description") ?? ""),
                  status: String(form.get("status") ?? editing.status),
                  is_pinned: form.get("is_pinned") === "on",
                });
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="tags">Tags (comma separated)</Label>
                <Input id="tags" name="tags" defaultValue={editing.tags} placeholder="stable, beta, deprecated" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="status">Status</Label>
                <Select name="status" defaultValue={editing.status}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="deprecated">Deprecated</SelectItem>
                    <SelectItem value="archived">Archived</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea id="description" name="description" defaultValue={editing.description ?? ""} />
              </div>
              <div className="flex items-center gap-2">
                <Switch id="is_pinned" name="is_pinned" defaultChecked={editing.is_pinned} />
                <Label htmlFor="is_pinned">Pinned (protected from retention &amp; deletion)</Label>
              </div>
              <DialogFooter>
                <Button type="submit" disabled={updateMutation.isPending}>
                  Save changes
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Compare dialog */}
      <Dialog open={comparing.length === 2} onOpenChange={(open) => !open && setComparing([])}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Version comparison</DialogTitle>
            <DialogDescription>
              {comparing[0]?.artifact}: {comparing[0]?.version} ↔ {comparing[1]?.version}
            </DialogDescription>
          </DialogHeader>
          {compareResult ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-4">
                {[compareResult.bundle_a, compareResult.bundle_b].map((b) => (
                  <div key={b.id} className="rounded-md border p-3">
                    <p className="font-mono font-medium">{b.version}</p>
                    <p className="text-xs text-muted-foreground">{formatBytes(b.file_size)}</p>
                    <p className="text-xs text-muted-foreground font-mono break-all mt-1">{b.sha256.slice(0, 20)}…</p>
                  </div>
                ))}
              </div>
              <p>
                Size difference: <span className="font-mono">{formatBytes(Math.abs(compareResult.size_diff_bytes))}</span>
                {compareResult.size_diff_bytes !== 0 && (compareResult.size_diff_bytes > 0 ? " larger" : " smaller")}
              </p>
              {Object.keys(compareResult.manifest_diff.changed).length > 0 && (
                <div>
                  <p className="font-medium mb-1">Changed manifest keys</p>
                  {Object.entries(compareResult.manifest_diff.changed).map(([k, v]) => (
                    <p key={k} className="font-mono text-xs text-muted-foreground">
                      {k}: {v}
                    </p>
                  ))}
                </div>
              )}
              {Object.keys(compareResult.manifest_diff.changed).length === 0 && (
                <p className="text-muted-foreground">Manifests are identical (besides version-specific keys).</p>
              )}
            </div>
          ) : (
            <Skeleton className="h-32 w-full" />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.artifact}:${deleting?.version}?`}
        description="The file will be removed from the repository. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />

      <ConfirmDialog
        open={bulkConfirm}
        onOpenChange={setBulkConfirm}
        title={`Delete ${selected.size} bundle(s)?`}
        description="Pinned bundles and bundles with active deployments will be skipped."
        confirmLabel="Delete all"
        destructive
        onConfirm={() => bulkDeleteMutation.mutate(Array.from(selected))}
      />
    </div>
  );
}

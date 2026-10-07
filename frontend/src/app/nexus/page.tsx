"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { NarBundleOut, NexusArtifact, NexusRepository, NexusServerOut, ServerTestResult } from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { formatRelative } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/data-table";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { EnabledBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Database, Download, Plug, Plus, RefreshCw, Search, Trash2 } from "lucide-react";

export default function NexusPage() {
  const { isAdmin, isDeveloper } = useAuth();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<NexusServerOut | null>(null);

  // Browse state
  const [browseServerId, setBrowseServerId] = useState<string>("");
  const [repository, setRepository] = useState<string>("");
  const [searchQ, setSearchQ] = useState("");
  const [submittedQ, setSubmittedQ] = useState("");

  const { data: servers, isLoading } = useQuery({
    queryKey: ["nexus-servers"],
    queryFn: () => api.get<NexusServerOut[]>("/nexus/servers"),
  });

  const { data: repositories } = useQuery({
    queryKey: ["nexus-repos", browseServerId],
    queryFn: () => api.get<NexusRepository[]>(`/nexus/servers/${browseServerId}/repositories`),
    enabled: !!browseServerId,
  });

  const { data: artifacts, isLoading: searchLoading } = useQuery({
    queryKey: ["nexus-search", browseServerId, repository, submittedQ],
    queryFn: () =>
      api.get<NexusArtifact[]>(`/nexus/servers/${browseServerId}/search`, {
        q: submittedQ || undefined,
        repository: repository || undefined,
      }),
    enabled: !!browseServerId,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post("/nexus/servers", payload),
    onSuccess: () => {
      toast.success("Nexus server added");
      setDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["nexus-servers"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/nexus/servers/${id}`),
    onSuccess: () => {
      toast.success("Nexus server deleted");
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["nexus-servers"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => api.post<ServerTestResult>(`/nexus/servers/${id}/test`),
    onSuccess: (result) => (result.success ? toast.success(result.message) : toast.error(result.message)),
    onError: (error) => toast.error(error.message),
  });

  const syncMutation = useMutation({
    mutationFn: (id: number) => api.post<{ synced: number; skipped: number; errors: string[] }>(`/nexus/servers/${id}/sync`),
    onSuccess: (result) => {
      toast.success(`Sync complete: ${result.synced} imported, ${result.skipped} skipped, ${result.errors.length} errors`);
      queryClient.invalidateQueries({ queryKey: ["nexus-servers"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const importMutation = useMutation({
    mutationFn: (artifact: NexusArtifact) =>
      api.post<NarBundleOut>("/nexus/download", {
        server_id: Number(browseServerId),
        repository: artifact.repository,
        group: artifact.group,
        artifact: artifact.artifact,
        version: artifact.version,
        download_url: artifact.download_url,
      }),
    onSuccess: (bundle) => {
      toast.success(`Imported ${bundle.artifact}:${bundle.version}`);
      queryClient.invalidateQueries({ queryKey: ["bundles-grouped"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Nexus Integration"
        description="Browse Nexus repositories and import NAR artifacts"
        actions={
          isAdmin ? (
            <Button onClick={() => setDialogOpen(true)}>
              <Plus className="h-4 w-4" /> Add Nexus Server
            </Button>
          ) : undefined
        }
      />

      <Tabs defaultValue="browse">
        <TabsList>
          <TabsTrigger value="browse">Browse &amp; Import</TabsTrigger>
          <TabsTrigger value="servers">Servers</TabsTrigger>
        </TabsList>

        <TabsContent value="browse" className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <Select value={browseServerId} onValueChange={setBrowseServerId}>
              <SelectTrigger className="sm:w-56">
                <SelectValue placeholder="Select Nexus server" />
              </SelectTrigger>
              <SelectContent>
                {servers?.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {repositories && repositories.length > 0 && (
              <Select value={repository || "all"} onValueChange={(v) => setRepository(v === "all" ? "" : v)}>
                <SelectTrigger className="sm:w-56">
                  <SelectValue placeholder="Repository" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All repositories</SelectItem>
                  {repositories.map((r) => (
                    <SelectItem key={r.name} value={r.name}>
                      {r.name} ({r.format})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <form
              className="flex gap-2 flex-1"
              onSubmit={(e) => {
                e.preventDefault();
                setSubmittedQ(searchQ);
              }}
            >
              <Input placeholder="Search artifacts…" value={searchQ} onChange={(e) => setSearchQ(e.target.value)} />
              <Button type="submit" variant="secondary" disabled={!browseServerId}>
                <Search className="h-4 w-4" />
              </Button>
            </form>
          </div>

          {!browseServerId ? (
            <EmptyState icon={Database} title="Select a Nexus server" description="Choose a configured Nexus server to browse its repositories." />
          ) : (
            <DataTable
              loading={searchLoading}
              data={artifacts ?? []}
              rowKey={(a) => `${a.group}:${a.artifact}:${a.version}`}
              emptyState={<EmptyState icon={Search} title="No NAR artifacts found" description="Try a different search or repository." />}
              columns={[
                {
                  key: "artifact",
                  header: "Artifact",
                  cell: (a) => (
                    <div>
                      <p className="font-medium">{a.artifact}</p>
                      <p className="text-xs text-muted-foreground">{a.group}</p>
                    </div>
                  ),
                },
                { key: "version", header: "Version", cell: (a) => <span className="font-mono">{a.version}</span> },
                { key: "repo", header: "Repository", cell: (a) => a.repository },
                {
                  key: "actions",
                  header: "",
                  className: "w-28",
                  cell: (a) =>
                    isDeveloper ? (
                      <Button size="sm" variant="outline" onClick={() => importMutation.mutate(a)} disabled={importMutation.isPending}>
                        <Download className="h-4 w-4" /> Import
                      </Button>
                    ) : null,
                },
              ]}
            />
          )}
        </TabsContent>

        <TabsContent value="servers">
          <DataTable
            loading={isLoading}
            data={servers}
            rowKey={(s) => s.id}
            emptyState={
              <EmptyState
                icon={Database}
                title="No Nexus servers configured"
                description="Add a Nexus Repository Manager to import artifacts directly."
                action={isAdmin ? <Button onClick={() => setDialogOpen(true)}>Add Nexus Server</Button> : undefined}
              />
            }
            columns={[
              {
                key: "name",
                header: "Name",
                cell: (s) => (
                  <div>
                    <p className="font-medium">{s.name}</p>
                    <p className="text-xs text-muted-foreground">{s.url}</p>
                  </div>
                ),
              },
              { key: "repo", header: "Default repo", cell: (s) => s.default_repository ?? "—" },
              { key: "schedule", header: "Sync schedule", cell: (s) => <span className="font-mono text-xs">{s.sync_schedule ?? "—"}</span> },
              { key: "sync", header: "Last sync", cell: (s) => (s.last_sync_at ? formatRelative(s.last_sync_at) : "never") },
              { key: "enabled", header: "Status", cell: (s) => <EnabledBadge enabled={s.is_enabled} /> },
              {
                key: "actions",
                header: "",
                className: "w-40",
                cell: (s) =>
                  isAdmin ? (
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" title="Test connection" onClick={() => testMutation.mutate(s.id)}>
                        <Plug className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" title="Sync now" onClick={() => syncMutation.mutate(s.id)} disabled={syncMutation.isPending}>
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" title="Delete" onClick={() => setDeleting(s)}>
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  ) : null,
              },
            ]}
          />
        </TabsContent>
      </Tabs>

      {/* Create dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Nexus server</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              createMutation.mutate({
                name: form.get("name"),
                url: form.get("url"),
                username: form.get("username") || null,
                password: form.get("password") || null,
                default_repository: form.get("default_repository") || null,
                sync_schedule: form.get("sync_schedule") || null,
                is_enabled: form.get("is_enabled") === "on",
              });
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input id="name" name="name" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="url">URL *</Label>
              <Input id="url" name="url" placeholder="http://nexus.example.com:8081" required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input id="username" name="username" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" name="password" type="password" />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="default_repository">Default repository</Label>
              <Input id="default_repository" name="default_repository" placeholder="nar-releases" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sync_schedule">Sync schedule (cron, optional)</Label>
              <Input id="sync_schedule" name="sync_schedule" placeholder="0 2 * * *" />
            </div>
            <div className="flex items-center gap-2">
              <Switch id="is_enabled" name="is_enabled" defaultChecked />
              <Label htmlFor="is_enabled">Enabled</Label>
            </div>
            <DialogFooter>
              <Button type="submit" disabled={createMutation.isPending}>
                Add server
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete Nexus server "${deleting?.name}"?`}
        description="Cached artifacts already imported remain in the repository."
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />
    </div>
  );
}

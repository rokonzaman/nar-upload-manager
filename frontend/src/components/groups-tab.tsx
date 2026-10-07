"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type {
  BundleGroup,
  DeploymentOut,
  NarBundleOut,
  NiFiServerOut,
  Page,
  RestartResult,
  ServerGroupOut,
} from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { DataTable } from "@/components/data-table";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { EnvironmentBadge, EnabledBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Boxes, CheckCircle2, Loader2, Pencil, Plus, Rocket, RotateCw, Trash2, XCircle } from "lucide-react";

export function GroupsTab() {
  const { isAdmin, isDeveloper, user } = useAuth();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ServerGroupOut | null>(null);
  const [deleting, setDeleting] = useState<ServerGroupOut | null>(null);
  const [deployTarget, setDeployTarget] = useState<ServerGroupOut | null>(null);
  const [restartTarget, setRestartTarget] = useState<ServerGroupOut | null>(null);
  const [restartResults, setRestartResults] = useState<RestartResult[]>([]);
  const [restartPending, setRestartPending] = useState(false);
  const [restartCurrentIdx, setRestartCurrentIdx] = useState(-1);
  const [memberIds, setMemberIds] = useState<Set<number>>(new Set());

  // Deploy dialog state
  const [bundleSearch, setBundleSearch] = useState("");
  const [selectedBundle, setSelectedBundle] = useState<NarBundleOut | null>(null);
  const [options, setOptions] = useState({ backup: true, restart_nifi: false, dry_run: false, notes: "" });

  const { data: groups, isLoading } = useQuery({
    queryKey: ["server-groups"],
    queryFn: () => api.get<ServerGroupOut[]>("/server-groups/"),
  });

  const { data: servers } = useQuery({
    queryKey: ["servers-all"],
    queryFn: () => api.get<Page<NiFiServerOut>>("/servers/", { page_size: 100 }),
  });

  const { data: environments } = useQuery({
    queryKey: ["environments"],
    queryFn: () => api.get<string[]>("/servers/environments"),
  });

  const { data: bundleGroups } = useQuery({
    queryKey: ["bundles-grouped"],
    queryFn: () => api.get<BundleGroup[]>("/bundles/grouped"),
    enabled: !!deployTarget,
  });

  const filteredBundles = useMemo(() => {
    if (!bundleGroups) return [];
    const q = bundleSearch.toLowerCase();
    return bundleGroups
      .flatMap((g) => g.versions)
      .filter((b) => !q || b.artifact.toLowerCase().includes(q) || b.version.includes(q))
      .slice(0, 50);
  }, [bundleGroups, bundleSearch]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["server-groups"] });

  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      editing ? api.put(`/server-groups/${editing.id}`, payload) : api.post("/server-groups/", payload),
    onSuccess: () => {
      toast.success(editing ? "Group updated" : "Group created");
      setDialogOpen(false);
      setEditing(null);
      invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/server-groups/${id}`),
    onSuccess: () => {
      toast.success("Group deleted");
      setDeleting(null);
      invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  const deployMutation = useMutation({
    mutationFn: () =>
      api.post<DeploymentOut[]>(`/server-groups/${deployTarget!.id}/deploy`, {
        bundle_id: selectedBundle!.id,
        backup: options.backup,
        restart_nifi: options.restart_nifi,
        dry_run: options.dry_run,
        notes: options.notes || null,
      }),
    onSuccess: (deployments) => {
      const failed = deployments.filter((d) => d.status === "failed").length;
      const succeeded = deployments.filter((d) => d.status === "success").length;
      if (options.dry_run) {
        toast.success(`Dry run finished on ${succeeded}/${deployments.length} node(s)`);
      } else if (failed === 0) {
        toast.success(`Deployed to all ${deployments.length} node(s)`);
      } else {
        toast.warning(`${failed} of ${deployments.length} node deployment(s) failed — check the Deployments page`);
      }
      setDeployTarget(null);
      setSelectedBundle(null);
      setBundleSearch("");
      setOptions({ backup: true, restart_nifi: false, dry_run: false, notes: "" });
      queryClient.invalidateQueries({ queryKey: ["deployments"] });
    },
    onError: (error) => toast.error(error.message),
  });

  async function restartGroupNodes(group: ServerGroupOut) {
    setRestartPending(true);
    setRestartCurrentIdx(-1);
    setRestartResults([]);
    const results: RestartResult[] = [];
    for (let i = 0; i < group.servers.length; i++) {
      setRestartCurrentIdx(i);
      try {
        const result = await api.post<RestartResult>(
          `/servers/${group.servers[i].id}/restart${group.servers[i].nifi_api_url ? "?wait_for_bootstrap=true" : ""}`
        );
        results.push(result);
        setRestartResults([...results]);
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        results.push({ success: false, message: msg, command: "", exit_code: -1, stdout: "", stderr: msg });
        setRestartResults([...results]);
      }
    }
    setRestartCurrentIdx(-1);
    setRestartPending(false);
    const failed = results.filter((r) => !r.success).length;
    if (failed === 0) {
      toast.success(`All ${results.length} node(s) restarted`);
    } else {
      toast.error(`${failed} of ${results.length} node(s) failed`);
    }
  }

  const openCreate = () => {
    setEditing(null);
    setMemberIds(new Set());
    setDialogOpen(true);
  };

  const openEdit = (group: ServerGroupOut) => {
    setEditing(group);
    setMemberIds(new Set(group.servers.map((s) => s.id)));
    setDialogOpen(true);
  };

  const toggleMember = (id: number) => {
    setMemberIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">
          Groups deploy a NAR to every member node in one operation — ideal for NiFi clusters.
        </p>
        {isAdmin && (
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" /> New Group
          </Button>
        )}
      </div>

      <DataTable
        loading={isLoading}
        data={groups ?? []}
        rowKey={(g) => g.id}
        emptyState={
          <EmptyState
            icon={Boxes}
            title="No server groups"
            description="Group your cluster nodes (e.g. 3 PROD nodes) to deploy a NAR to all of them at once."
            action={isAdmin ? <Button onClick={openCreate}>New Group</Button> : undefined}
          />
        }
        columns={[
          {
            key: "name",
            header: "Group",
            cell: (g) => (
              <div>
                <p className="font-medium flex items-center gap-2">
                  <Boxes className="h-4 w-4 text-primary" /> {g.name}
                </p>
                {g.description && <p className="text-xs text-muted-foreground">{g.description}</p>}
              </div>
            ),
          },
          { key: "env", header: "Environment", cell: (g) => <EnvironmentBadge environment={g.environment} /> },
          {
            key: "members",
            header: "Nodes",
            cell: (g) => (
              <div className="flex flex-wrap gap-1">
                {g.servers.map((s) => (
                  <Badge key={s.id} variant="secondary" className="gap-1">
                    {s.name}
                    {!s.is_enabled && <span className="text-red-500">(off)</span>}
                  </Badge>
                ))}
              </div>
            ),
          },
          {
            key: "count",
            header: "Count",
            cell: (g) => <Badge variant="outline">{g.server_count} node(s)</Badge>,
          },
          {
            key: "actions",
            header: "",
            className: "w-32",
            cell: (g) => {
              const canOperate = !user?.deploy_environments || user.deploy_environments.split(",").map(e => e.trim().toUpperCase()).includes(g.environment.toUpperCase());
              return (
              <div className="flex gap-1">
                {isDeveloper && canOperate && (
                  <>
                    <Button size="sm" onClick={() => setDeployTarget(g)} disabled={g.server_count === 0}>
                      <Rocket className="h-4 w-4" /> Deploy NAR
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setRestartTarget(g); setRestartResults([]); setRestartCurrentIdx(-1); setRestartPending(false); }} disabled={g.server_count === 0}>
                      <RotateCw className="h-4 w-4" /> Restart
                    </Button>
                  </>
                )}
                {isAdmin && (
                  <>
                    <Button variant="ghost" size="icon" onClick={() => openEdit(g)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleting(g)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </>
                )}
              </div>
              );
            },
          },
        ]}
      />

      {/* Create / edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit ${editing.name}` : "Create server group"}</DialogTitle>
            <DialogDescription>Select the cluster nodes that belong to this group.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              saveMutation.mutate({
                name: form.get("name"),
                description: form.get("description") || null,
                environment: form.get("environment"),
                server_ids: Array.from(memberIds),
              });
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="name">Group name *</Label>
                <Input id="name" name="name" defaultValue={editing?.name} placeholder="nifi-prod-cluster" required />
              </div>
              <div className="space-y-2">
                <Label>Environment *</Label>
                <Select name="environment" defaultValue={editing?.environment ?? "PROD"}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(environments ?? ["DEV", "QA", "PROD"]).map((env) => (
                      <SelectItem key={env} value={env}>
                        {env}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea id="description" name="description" defaultValue={editing?.description ?? ""} />
            </div>
            <div className="space-y-2">
              <Label>Member nodes ({memberIds.size} selected)</Label>
              <div className="grid sm:grid-cols-2 gap-2 max-h-56 overflow-y-auto">
                {servers?.items.map((server) => (
                  <label
                    key={server.id}
                    className="flex items-center gap-3 rounded-md border p-3 cursor-pointer hover:bg-muted/60"
                  >
                    <Checkbox checked={memberIds.has(server.id)} onCheckedChange={() => toggleMember(server.id)} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{server.name}</p>
                      <p className="text-xs text-muted-foreground truncate">{server.hostname}</p>
                    </div>
                    <EnvironmentBadge environment={server.environment} />
                  </label>
                ))}
              </div>
            </div>
            <DialogFooter>
              <Button type="submit" disabled={saveMutation.isPending}>
                {editing ? "Save changes" : "Create group"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Group deploy dialog */}
      <Dialog open={!!deployTarget} onOpenChange={(open) => !open && setDeployTarget(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Rocket className="h-5 w-5 text-primary" /> Deploy to {deployTarget?.name}
            </DialogTitle>
            <DialogDescription>
              The NAR will be deployed to all {deployTarget?.server_count} node(s):
              <span className="block mt-1">
                {deployTarget?.servers.map((s) => (
                  <Badge key={s.id} variant="secondary" className="mr-1">
                    {s.name} <EnabledBadge enabled={s.is_enabled} />
                  </Badge>
                ))}
              </span>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Bundle</Label>
              <Input placeholder="Search bundles…" value={bundleSearch} onChange={(e) => setBundleSearch(e.target.value)} />
              <ScrollArea className="h-36 rounded-md border">
                {filteredBundles.map((bundle) => (
                  <button
                    key={bundle.id}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-muted/60 flex items-center justify-between ${selectedBundle?.id === bundle.id ? "bg-primary/10" : ""}`}
                    onClick={() => setSelectedBundle(bundle)}
                  >
                    <span>
                      <span className="font-medium">{bundle.artifact}</span>{" "}
                      <span className="font-mono text-muted-foreground">{bundle.version}</span>
                    </span>
                    {selectedBundle?.id === bundle.id && <CheckCircle2 className="h-4 w-4 text-primary" />}
                  </button>
                ))}
                {filteredBundles.length === 0 && <p className="p-3 text-sm text-muted-foreground">No bundles found.</p>}
              </ScrollArea>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={options.backup} onCheckedChange={(v) => setOptions({ ...options, backup: v })} />
                Backup
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={options.restart_nifi} onCheckedChange={(v) => setOptions({ ...options, restart_nifi: v })} />
                Restart NiFi
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={options.dry_run} onCheckedChange={(v) => setOptions({ ...options, dry_run: v })} />
                Dry run
              </label>
            </div>
            <Textarea
              placeholder="Deployment notes (optional)"
              value={options.notes}
              onChange={(e) => setOptions({ ...options, notes: e.target.value })}
            />
          </div>

          <DialogFooter>
            <Button disabled={!selectedBundle || deployMutation.isPending} onClick={() => deployMutation.mutate()}>
              {deployMutation.isPending
                ? "Deploying…"
                : `${options.dry_run ? "Dry run" : "Deploy"} to ${deployTarget?.server_count} node(s)`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Group restart dialog */}
      <Dialog open={!!restartTarget} onOpenChange={(open) => { if (!open) { setRestartTarget(null); setRestartResults([]); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <RotateCw className="h-5 w-5 text-primary" /> Restart {restartTarget?.name}
            </DialogTitle>
            <DialogDescription>
              Nodes restart sequentially — next starts only after current node finishes booting (60s timeout).
              <span className="block mt-1">
                {restartTarget?.servers.map((s) => (
                  <Badge key={s.id} variant="secondary" className="mr-1">
                    {s.name}
                  </Badge>
                ))}
              </span>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {restartTarget?.servers.map((server, idx) => {
              const result = restartResults[idx];
              const isCurrent = restartCurrentIdx === idx;
              const isPending = !result && !isCurrent && restartResults.length <= idx;
              return (
                <div key={server.id} className="rounded-md border p-3 text-sm">
                  <div className="flex items-center gap-2">
                    {isPending ? (
                      <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
                    ) : isCurrent ? (
                      <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                    ) : result?.success ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <span className="font-medium">{server.name}</span>
                    {isCurrent && <Badge variant="outline" className="text-xs">restarting...</Badge>}
                  </div>
                  {result && (
                    <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                      <p>Command: <code className="text-xs">{result.command}</code></p>
                      <p>Exit code: {result.exit_code}</p>
                      {result.message && <p>{result.message}</p>}
                      {!result.success && result.stderr && (
                        <p className="text-red-500">{result.stderr}</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setRestartTarget(null); setRestartResults([]); }} disabled={restartPending}>
              Close
            </Button>
            {!restartPending && restartTarget && restartResults.length < restartTarget.server_count && (
              <Button onClick={() => restartGroupNodes(restartTarget)}>
                <RotateCw className="h-4 w-4 mr-1" />
                Restart all {restartTarget.server_count} node(s)
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete group "${deleting?.name}"?`}
        description="Member servers are kept — only the grouping is removed."
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />
    </div>
  );
}

"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type {
  BundleGroup,
  CompatibilityReport,
  DeploymentOut,
  NarBundleOut,
  NiFiServerOut,
  Page,
  ServerGroupOut,
} from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { formatDate, formatRelative } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/data-table";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { DeploymentStatusBadge, EnvironmentBadge } from "@/components/status-badge";
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
import { AlertTriangle, CheckCircle2, FileText, Info, Plus, Rocket, Undo2 } from "lucide-react";

const DEPLOYMENT_STATUSES = ["pending", "in_progress", "success", "failed", "rolled_back", "cancelled"];

function duration(deployment: DeploymentOut): string {
  if (!deployment.started_at || !deployment.completed_at) return "—";
  const ms = new Date(deployment.completed_at).getTime() - new Date(deployment.started_at).getTime();
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function DeploymentsPage() {
  const { isDeveloper } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [serverFilter, setServerFilter] = useState("");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [logDeployment, setLogDeployment] = useState<DeploymentOut | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<DeploymentOut | null>(null);

  // Wizard state
  const [selectedBundle, setSelectedBundle] = useState<NarBundleOut | null>(null);
  const [bundleSearch, setBundleSearch] = useState("");
  const [selectedServers, setSelectedServers] = useState<Set<number>>(new Set());
  const [options, setOptions] = useState({ backup: true, restart_nifi: false, dry_run: false, notes: "", target_directory: "" });
  const [compatReports, setCompatReports] = useState<CompatibilityReport[] | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["deployments", page, statusFilter, serverFilter],
    queryFn: () =>
      api.get<Page<DeploymentOut>>("/deployments/", {
        page,
        page_size: 15,
        status: statusFilter || undefined,
        server_id: serverFilter || undefined,
      }),
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => d.status === "in_progress" || d.status === "pending") ? 2000 : false,
  });

  const { data: servers } = useQuery({
    queryKey: ["servers-all"],
    queryFn: () => api.get<Page<NiFiServerOut>>("/servers/", { page_size: 100 }),
  });

  const { data: serverGroups } = useQuery({
    queryKey: ["server-groups"],
    queryFn: () => api.get<ServerGroupOut[]>("/server-groups/"),
    enabled: wizardOpen,
  });

  const { data: bundleGroups } = useQuery({
    queryKey: ["bundles-grouped"],
    queryFn: () => api.get<BundleGroup[]>("/bundles/grouped"),
    enabled: wizardOpen,
  });

  const { data: liveLog } = useQuery({
    queryKey: ["deployment-log", logDeployment?.id],
    queryFn: () => api.get<DeploymentOut>(`/deployments/${logDeployment!.id}`),
    enabled: !!logDeployment && (logDeployment.status === "in_progress" || logDeployment.status === "pending"),
    refetchInterval: 2000,
  });

  const filteredBundles = useMemo(() => {
    if (!bundleGroups) return [];
    const q = bundleSearch.toLowerCase();
    return bundleGroups
      .flatMap((g) => g.versions)
      .filter((b) => !q || b.artifact.toLowerCase().includes(q) || b.version.includes(q))
      .slice(0, 50);
  }, [bundleGroups, bundleSearch]);

  const deployMutation = useMutation({
    mutationFn: () =>
      api.post<DeploymentOut[]>("/deployments/", {
        bundle_id: selectedBundle!.id,
        server_ids: Array.from(selectedServers),
        backup: options.backup,
        restart_nifi: options.restart_nifi,
        dry_run: options.dry_run,
        notes: options.notes || null,
        target_directory: options.target_directory || null,
      }),
    onSuccess: (deployments) => {
      toast.success(`${deployments.length} deployment(s) started`);
      setWizardOpen(false);
      resetWizard();
      queryClient.invalidateQueries({ queryKey: ["deployments"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const rollbackMutation = useMutation({
    mutationFn: (id: number) => api.post<DeploymentOut>(`/deployments/${id}/rollback`),
    onSuccess: () => {
      toast.success("Rollback completed");
      setRollbackTarget(null);
      queryClient.invalidateQueries({ queryKey: ["deployments"] });
    },
    onError: (error) => {
      toast.error(error.message);
      setRollbackTarget(null);
    },
  });

  const compatMutation = useMutation({
    mutationFn: () =>
      api.post<CompatibilityReport[]>("/deployments/compatibility", {
        bundle_id: selectedBundle!.id,
        server_ids: Array.from(selectedServers),
      }),
    onSuccess: setCompatReports,
    onError: (error) => toast.error(error.message),
  });

  const resetWizard = () => {
    setSelectedBundle(null);
    setSelectedServers(new Set());
    setOptions({ backup: true, restart_nifi: false, dry_run: false, notes: "", target_directory: "" });
    setCompatReports(null);
    setBundleSearch("");
  };

  const displayedLog = liveLog ?? logDeployment;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Deployments"
        description="Deployment history and new NAR deployments"
        actions={
          isDeveloper ? (
            <Button onClick={() => setWizardOpen(true)}>
              <Plus className="h-4 w-4" /> New Deployment
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-col sm:flex-row gap-3">
        <Select
          value={statusFilter || "all"}
          onValueChange={(v) => {
            setStatusFilter(v === "all" ? "" : v);
            setPage(1);
          }}
        >
          <SelectTrigger className="sm:w-44">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {DEPLOYMENT_STATUSES.map((s) => (
              <SelectItem key={s} value={s} className="capitalize">
                {s.replace(/_/g, " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={serverFilter || "all"}
          onValueChange={(v) => {
            setServerFilter(v === "all" ? "" : v);
            setPage(1);
          }}
        >
          <SelectTrigger className="sm:w-44">
            <SelectValue placeholder="Server" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All servers</SelectItem>
            {servers?.items.map((s) => (
              <SelectItem key={s.id} value={String(s.id)}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <DataTable
        loading={isLoading}
        data={data?.items}
        page={data}
        onPageChange={setPage}
        rowKey={(d) => d.id}
        columns={[
          { key: "id", header: "#", cell: (d) => <span className="font-mono text-muted-foreground">{d.id}</span>, className: "w-12" },
          {
            key: "bundle",
            header: "Bundle",
            cell: (d) => (
              <div>
                <p className="font-medium">{d.bundle?.artifact ?? `#${d.bundle_id}`}</p>
                <p className="text-xs text-muted-foreground font-mono">{d.bundle?.version}</p>
              </div>
            ),
          },
          {
            key: "server",
            header: "Server",
            cell: (d) => (
              <div className="flex items-center gap-2">
                <span>{d.server?.name ?? `#${d.server_id}`}</span>
                {d.server && <EnvironmentBadge environment={d.server.environment} />}
              </div>
            ),
          },
          {
            key: "status",
            header: "Status",
            cell: (d) => (
              <div className="flex items-center gap-2">
                <DeploymentStatusBadge status={d.status} />
                {d.dry_run && <Badge variant="secondary">dry run</Badge>}
                {d.checksum_verified && <CheckCircle2 className="h-3 w-3 text-emerald-500" />}
              </div>
            ),
          },
          { key: "by", header: "Deployed by", cell: (d) => d.deployed_by },
          { key: "duration", header: "Duration", cell: (d) => duration(d) },
          {
            key: "created",
            header: "Created",
            cell: (d) => <span className="text-sm text-muted-foreground">{formatRelative(d.created_at)}</span>,
          },
          {
            key: "actions",
            header: "",
            className: "w-24",
            cell: (d) => (
              <div className="flex gap-1">
                <Button variant="ghost" size="icon" title="View log" onClick={() => setLogDeployment(d)}>
                  <FileText className="h-4 w-4" />
                </Button>
                {isDeveloper && d.status === "success" && !d.dry_run && d.backup_path && (
                  <Button variant="ghost" size="icon" title="Rollback" onClick={() => setRollbackTarget(d)}>
                    <Undo2 className="h-4 w-4 text-amber-500" />
                  </Button>
                )}
              </div>
            ),
          },
        ]}
      />

      {/* New deployment wizard */}
      <Dialog open={wizardOpen} onOpenChange={(open) => { setWizardOpen(open); if (!open) resetWizard(); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Rocket className="h-5 w-5 text-primary" /> New deployment
            </DialogTitle>
            <DialogDescription>Select a bundle, target servers and deployment options.</DialogDescription>
          </DialogHeader>

          <div className="space-y-5">
            <div className="space-y-2">
              <Label>1. Bundle</Label>
              <Input placeholder="Search bundles…" value={bundleSearch} onChange={(e) => setBundleSearch(e.target.value)} />
              <ScrollArea className="h-40 rounded-md border">
                {filteredBundles.map((bundle) => (
                  <button
                    key={bundle.id}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-muted/60 flex items-center justify-between ${selectedBundle?.id === bundle.id ? "bg-primary/10" : ""}`}
                    onClick={() => { setSelectedBundle(bundle); setCompatReports(null); }}
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

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Label>2. Target servers</Label>
                {serverGroups && serverGroups.length > 0 && (
                  <Select
                    onValueChange={(groupId) => {
                      const group = serverGroups.find((g) => String(g.id) === groupId);
                      if (group) {
                        setSelectedServers(new Set(group.servers.map((s) => s.id)));
                        setCompatReports(null);
                        toast.info(`Selected ${group.server_count} node(s) from "${group.name}"`);
                      }
                    }}
                  >
                    <SelectTrigger className="w-56 h-8 text-xs">
                      <SelectValue placeholder="Quick-select a group…" />
                    </SelectTrigger>
                    <SelectContent>
                      {serverGroups.map((g) => (
                        <SelectItem key={g.id} value={String(g.id)}>
                          {g.name} ({g.server_count} nodes)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <div className="grid sm:grid-cols-2 gap-2">
                {servers?.items.map((server) => (
                  <label
                    key={server.id}
                    className={`flex items-center gap-3 rounded-md border p-3 cursor-pointer hover:bg-muted/60 ${!server.is_enabled ? "opacity-50" : ""}`}
                  >
                    <Checkbox
                      checked={selectedServers.has(server.id)}
                      onCheckedChange={(checked) => {
                        setSelectedServers((prev) => {
                          const next = new Set(prev);
                          if (checked) next.add(server.id);
                          else next.delete(server.id);
                          return next;
                        });
                        setCompatReports(null);
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{server.name}</p>
                      <p className="text-xs text-muted-foreground truncate">{server.hostname}</p>
                    </div>
                    <EnvironmentBadge environment={server.environment} />
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-3">
              <Label>3. Options</Label>
              <div className="grid sm:grid-cols-3 gap-3">
                <label className="flex items-center gap-2 text-sm">
                  <Switch checked={options.backup} onCheckedChange={(v) => setOptions({ ...options, backup: v })} />
                  Backup existing
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
              <Input
                placeholder="Target directory override (optional)"
                value={options.target_directory}
                onChange={(e) => setOptions({ ...options, target_directory: e.target.value })}
              />
              <Textarea
                placeholder="Deployment notes (optional)"
                value={options.notes}
                onChange={(e) => setOptions({ ...options, notes: e.target.value })}
              />
            </div>

            {compatReports && (
              <div className="space-y-2 rounded-md border p-3">
                <p className="text-sm font-medium">Compatibility report</p>
                {compatReports.map((report) => (
                  <div key={report.server_id} className="text-sm space-y-1">
                    <p className="font-medium">
                      {servers?.items.find((s) => s.id === report.server_id)?.name ?? `Server ${report.server_id}`}:{" "}
                      {report.compatible ? (
                        <span className="text-emerald-500">compatible</span>
                      ) : (
                        <span className="text-red-500">incompatible</span>
                      )}
                    </p>
                    {report.warnings.map((w, i) => (
                      <p key={i} className="flex items-start gap-1 text-xs text-muted-foreground">
                        {w.level === "error" ? (
                          <AlertTriangle className="h-3 w-3 text-red-500 mt-0.5 shrink-0" />
                        ) : w.level === "warning" ? (
                          <AlertTriangle className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" />
                        ) : (
                          <Info className="h-3 w-3 text-blue-500 mt-0.5 shrink-0" />
                        )}
                        {w.message}
                      </p>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              disabled={!selectedBundle || selectedServers.size === 0 || compatMutation.isPending}
              onClick={() => compatMutation.mutate()}
            >
              Check compatibility
            </Button>
            <Button
              disabled={!selectedBundle || selectedServers.size === 0 || deployMutation.isPending}
              onClick={() => deployMutation.mutate()}
            >
              {deployMutation.isPending ? "Starting…" : `Deploy to ${selectedServers.size} server(s)`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Log dialog */}
      <Dialog open={!!logDeployment} onOpenChange={(open) => !open && setLogDeployment(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Deployment #{logDeployment?.id} log</DialogTitle>
            <DialogDescription className="flex items-center gap-2">
              {logDeployment && <DeploymentStatusBadge status={displayedLog?.status ?? logDeployment.status} />}
              {displayedLog?.error_message && <span className="text-red-500">{displayedLog.error_message}</span>}
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="h-80 rounded-md border bg-muted/30 p-4">
            <pre className="text-xs font-mono whitespace-pre-wrap">{displayedLog?.log ?? "No log entries yet."}</pre>
          </ScrollArea>
          {displayedLog?.notes && <p className="text-sm text-muted-foreground">Notes: {displayedLog.notes}</p>}
          <p className="text-xs text-muted-foreground">
            Started {formatDate(displayedLog?.started_at)} — completed {formatDate(displayedLog?.completed_at)}
          </p>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!rollbackTarget}
        onOpenChange={(open) => !open && setRollbackTarget(null)}
        title={`Rollback deployment #${rollbackTarget?.id}?`}
        description={`This restores the backed-up file on ${rollbackTarget?.server?.name} to its pre-deployment state.`}
        confirmLabel="Rollback"
        onConfirm={() => rollbackTarget && rollbackMutation.mutate(rollbackTarget.id)}
      />
    </div>
  );
}

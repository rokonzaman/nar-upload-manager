"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { NiFiServerOut, Page, RemoteNarFile, RestartResult, ServerHealth, ServerTestResult } from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable } from "@/components/data-table";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { EnabledBadge, EnvironmentBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GroupsTab } from "@/components/groups-tab";
import { formatBytes, formatRelative } from "@/lib/utils";
import { Activity, Boxes, FolderOpen, MoreHorizontal, Plug, Plus, Server as ServerIcon, Trash2, Pencil, RotateCw } from "lucide-react";

const serverSchema = z.object({
  name: z.string().min(1, "Name is required"),
  hostname: z.string().min(1, "Hostname is required"),
  ssh_host: z.string().min(1, "SSH host is required"),
  ssh_port: z.coerce.number().int().min(1).max(65535),
  ssh_user: z.string().min(1, "SSH user is required"),
  ssh_key_path: z.string().optional(),
  ssh_password: z.string().optional(),
  nar_directory: z.string().min(1),
  backup_directory: z.string().min(1),
  nifi_install_directory: z.string().min(1),
  restart_command: z.string().min(1),
  nifi_api_url: z.string().optional(),
  environment: z.string().min(1),
  is_enabled: z.boolean(),
  description: z.string().optional(),
});

type ServerForm = z.infer<typeof serverSchema>;

const DEFAULT_VALUES: ServerForm = {
  name: "",
  hostname: "",
  ssh_host: "",
  ssh_port: 22,
  ssh_user: "nifi",
  ssh_key_path: "",
  ssh_password: "",
  nar_directory: "/opt/nifi/lib",
  backup_directory: "/opt/nifi/nar-backup",
  nifi_install_directory: "/opt/nifi",
  restart_command: "sudo systemctl restart nifi",
  nifi_api_url: "",
  environment: "DEV",
  is_enabled: true,
  description: "",
};

export default function ServersPage() {
  const { isAdmin, isDeveloper, user } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [envFilter, setEnvFilter] = useState<string>("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<NiFiServerOut | null>(null);
  const [deleting, setDeleting] = useState<NiFiServerOut | null>(null);
  const [healthServer, setHealthServer] = useState<NiFiServerOut | null>(null);
  const [repoServer, setRepoServer] = useState<NiFiServerOut | null>(null);
  const [selectedNars, setSelectedNars] = useState<Set<string>>(new Set());
  const [deletingNars, setDeletingNars] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["servers", page, search, envFilter],
    queryFn: () =>
      api.get<Page<NiFiServerOut>>("/servers/", {
        page,
        page_size: 10,
        q: search || undefined,
        environment: envFilter || undefined,
      }),
  });

  const { data: environments } = useQuery({
    queryKey: ["environments"],
    queryFn: () => api.get<string[]>("/servers/environments"),
  });

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["server-health", healthServer?.id],
    queryFn: () => api.get<ServerHealth>(`/servers/${healthServer!.id}/health`),
    enabled: !!healthServer,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["servers"] });

  const saveMutation = useMutation({
    mutationFn: (values: ServerForm) => {
      const payload = {
        ...values,
        ssh_key_path: values.ssh_key_path || null,
        ssh_password: values.ssh_password || null,
        nifi_api_url: values.nifi_api_url || null,
        description: values.description || null,
      };
      if (!editing) return api.post<NiFiServerOut>("/servers/", payload);
      if (!payload.ssh_password) delete (payload as Record<string, unknown>).ssh_password;
      return api.put<NiFiServerOut>(`/servers/${editing.id}`, payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Server updated" : "Server created");
      setDialogOpen(false);
      setEditing(null);
      invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/servers/${id}`),
    onSuccess: () => {
      toast.success("Server deleted");
      setDeleting(null);
      invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => api.post<ServerTestResult>(`/servers/${id}/test-connection`),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(`${result.message}${result.latency_ms ? ` (${result.latency_ms} ms)` : ""}`);
      } else {
        toast.error(result.message);
      }
    },
    onError: (error) => toast.error(error.message),
  });

  const { data: remoteNars, isLoading: narsLoading } = useQuery({
    queryKey: ["remote-nars", repoServer?.id],
    queryFn: () => api.get<RemoteNarFile[]>(`/servers/${repoServer!.id}/nar-files`),
    enabled: !!repoServer,
  });

  const deleteNarsMutation = useMutation({
    mutationFn: (filenames: string[]) =>
      api.del<{ message: string }>(`/servers/${repoServer!.id}/nar-files`, { filenames }),
    onSuccess: (res) => {
      toast.success(res.message);
      setSelectedNars(new Set());
      setDeletingNars(false);
      queryClient.invalidateQueries({ queryKey: ["remote-nars", repoServer?.id] });
    },
    onError: (error) => {
      toast.error(error.message);
      setDeletingNars(false);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (server: NiFiServerOut) => api.put(`/servers/${server.id}`, { is_enabled: !server.is_enabled }),
    onSuccess: invalidate,
    onError: (error) => toast.error(error.message),
  });

  const restartMutation = useMutation({
    mutationFn: (server: NiFiServerOut) => api.post<RestartResult>(`/servers/${server.id}/restart`),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(`NiFi restarted on ${result.command} (exit ${result.exit_code})`);
      } else {
        toast.error(`Restart failed (exit ${result.exit_code}): ${result.stderr || result.stdout}`);
      }
    },
    onError: (error) => toast.error(error.message),
  });

  const form = useForm<ServerForm>({ resolver: zodResolver(serverSchema), defaultValues: DEFAULT_VALUES });

  const openCreate = () => {
    setEditing(null);
    form.reset(DEFAULT_VALUES);
    setDialogOpen(true);
  };

  const openEdit = (server: NiFiServerOut) => {
    setEditing(server);
    form.reset({
      ...DEFAULT_VALUES,
      ...server,
      ssh_key_path: server.ssh_key_path ?? "",
      ssh_password: "",
      nifi_api_url: server.nifi_api_url ?? "",
      description: server.description ?? "",
    });
    setDialogOpen(true);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="NiFi Servers"
        description="Registered NiFi environments, clusters and their SSH deployment targets"
      />

      <Tabs defaultValue="servers" className="space-y-4">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="servers">
              <ServerIcon className="h-4 w-4 mr-1" /> Servers
            </TabsTrigger>
            <TabsTrigger value="groups">
              <Boxes className="h-4 w-4 mr-1" /> Groups (Clusters)
            </TabsTrigger>
          </TabsList>
          {isAdmin && (
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" /> Add Server
            </Button>
          )}
        </div>

        <TabsContent value="servers" className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <Input
          placeholder="Search servers…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="sm:max-w-xs"
        />
        <Select
          value={envFilter || "all"}
          onValueChange={(v) => {
            setEnvFilter(v === "all" ? "" : v);
            setPage(1);
          }}
        >
          <SelectTrigger className="sm:w-40">
            <SelectValue placeholder="Environment" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All environments</SelectItem>
            {(environments ?? []).map((env) => (
              <SelectItem key={env} value={env}>
                {env}
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
        rowKey={(s) => s.id}
        emptyState={
          <EmptyState
            icon={ServerIcon}
            title="No servers registered"
            description="Register your first NiFi server to start deploying NAR bundles."
            action={isAdmin ? <Button onClick={openCreate}>Add Server</Button> : undefined}
          />
        }
        columns={[
          {
            key: "name",
            header: "Name",
            cell: (s) => (
              <div>
                <p className="font-medium">{s.name}</p>
                <p className="text-xs text-muted-foreground">{s.hostname}</p>
              </div>
            ),
          },
          { key: "env", header: "Environment", cell: (s) => <EnvironmentBadge environment={s.environment} /> },
          {
            key: "ssh",
            header: "SSH Target",
            cell: (s) => (
              <span className="font-mono text-xs">
                {s.ssh_user}@{s.ssh_host}:{s.ssh_port}
              </span>
            ),
          },
          {
            key: "nar",
            header: "NAR Directory",
            cell: (s) => <span className="font-mono text-xs">{s.nar_directory}</span>,
          },
          {
            key: "enabled",
            header: "Enabled",
            cell: (s) =>
              isAdmin ? (
                <Switch checked={s.is_enabled} onCheckedChange={() => toggleMutation.mutate(s)} />
              ) : (
                <EnabledBadge enabled={s.is_enabled} />
              ),
          },
          {
            key: "actions",
            header: "",
            className: "w-12",
            cell: (s) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => setHealthServer(s)}>
                    <Activity className="h-4 w-4" /> Health
                  </DropdownMenuItem>
                  {isDeveloper && (!user?.deploy_environments || user.deploy_environments.split(",").map(e => e.trim().toUpperCase()).includes(s.environment.toUpperCase())) && (
                    <DropdownMenuItem onClick={() => restartMutation.mutate(s)} disabled={restartMutation.isPending}>
                      <RotateCw className="h-4 w-4" /> Restart NiFi
                    </DropdownMenuItem>
                  )}
                  {isAdmin && (
                    <>
                      <DropdownMenuItem onClick={() => { setRepoServer(s); setSelectedNars(new Set()); }}>
                    <FolderOpen className="h-4 w-4" /> NAR Repository
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => testMutation.mutate(s.id)} disabled={testMutation.isPending}>
                        <Plug className="h-4 w-4" /> Test connection
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => openEdit(s)}>
                        <Pencil className="h-4 w-4" /> Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-red-500 focus:text-red-500" onClick={() => setDeleting(s)}>
                        <Trash2 className="h-4 w-4" /> Delete
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            ),
          },
        ]}
      />
        </TabsContent>

        <TabsContent value="groups">
          <GroupsTab />
        </TabsContent>
      </Tabs>

      {/* Create / edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit ${editing.name}` : "Register NiFi server"}</DialogTitle>
            <DialogDescription>SSH credentials are stored encrypted and never displayed.</DialogDescription>
          </DialogHeader>
          <form onSubmit={form.handleSubmit((v) => saveMutation.mutate(v))} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input id="name" {...form.register("name")} />
              {form.formState.errors.name && <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="hostname">Hostname *</Label>
              <Input id="hostname" {...form.register("hostname")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ssh_host">SSH Host *</Label>
              <Input id="ssh_host" {...form.register("ssh_host")} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-2">
                <Label htmlFor="ssh_port">SSH Port *</Label>
                <Input id="ssh_port" type="number" {...form.register("ssh_port")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ssh_user">SSH User *</Label>
                <Input id="ssh_user" {...form.register("ssh_user")} />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ssh_key_path">SSH Key Path</Label>
              <Input id="ssh_key_path" placeholder="~/.ssh/id_rsa" {...form.register("ssh_key_path")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ssh_password">
                SSH Password {editing?.has_ssh_password && <Badge variant="secondary">set — leave empty to keep</Badge>}
              </Label>
              <Input id="ssh_password" type="password" autoComplete="new-password" {...form.register("ssh_password")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nar_directory">NAR Directory *</Label>
              <Input id="nar_directory" {...form.register("nar_directory")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="backup_directory">Backup Directory *</Label>
              <Input id="backup_directory" {...form.register("backup_directory")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nifi_install_directory">NiFi Install Directory *</Label>
              <Input id="nifi_install_directory" {...form.register("nifi_install_directory")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="restart_command">Restart Command *</Label>
              <Input id="restart_command" {...form.register("restart_command")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nifi_api_url">NiFi API URL</Label>
              <Input id="nifi_api_url" placeholder="https://host:8443/nifi-api" {...form.register("nifi_api_url")} />
            </div>
            <div className="space-y-2">
              <Label>Environment *</Label>
              <Select value={form.watch("environment")} onValueChange={(v) => form.setValue("environment", v)}>
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
            <div className="sm:col-span-2 space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea id="description" {...form.register("description")} />
            </div>
            <div className="sm:col-span-2 flex items-center gap-2">
              <Switch id="is_enabled" checked={form.watch("is_enabled")} onCheckedChange={(v) => form.setValue("is_enabled", v)} />
              <Label htmlFor="is_enabled">Enabled (accepts deployments)</Label>
            </div>
            <DialogFooter className="sm:col-span-2">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saveMutation.isPending}>
                {saveMutation.isPending ? "Saving…" : editing ? "Save changes" : "Create server"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Health dialog */}
      <Dialog open={!!healthServer} onOpenChange={(open) => !open && setHealthServer(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Server health — {healthServer?.name}</DialogTitle>
            <DialogDescription>Live metrics collected over SSH</DialogDescription>
          </DialogHeader>
          {healthLoading ? (
            <p className="text-sm text-muted-foreground">Collecting metrics…</p>
          ) : health ? (
            <div className="space-y-4">
              {!health.reachable && (
                <Badge variant="outline" className="bg-red-500/15 text-red-500 border-red-500/30">
                  unreachable — {health.warnings[0]}
                </Badge>
              )}
              {health.reachable && (
                <>
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span>Disk usage</span>
                      <span>
                        {health.disk_used_percent}% ({formatBytes(health.disk_free_bytes)} free)
                      </span>
                    </div>
                    <Progress value={health.disk_used_percent ?? 0} />
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span>Memory</span>
                      <span>{health.memory_percent ?? "—"}%</span>
                    </div>
                    <Progress value={health.memory_percent ?? 0} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <span className="text-muted-foreground">NiFi status</span>
                    <span>{health.nifi_status ?? "unknown"}</span>
                    <span className="text-muted-foreground">NiFi version</span>
                    <span>{health.nifi_version ?? "unknown"}</span>
                    <span className="text-muted-foreground">NAR dir size</span>
                    <span>{formatBytes(health.nar_dir_size_bytes)}</span>
                    <span className="text-muted-foreground">Checked</span>
                    <span>{formatRelative(health.checked_at)}</span>
                  </div>
                  {health.warnings.length > 0 && (
                    <div className="rounded-md bg-amber-500/10 border border-amber-500/30 p-3 text-sm text-amber-500">
                      {health.warnings.map((w) => (
                        <p key={w}>⚠ {w}</p>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* NAR Repository dialog */}
      <Dialog open={!!repoServer} onOpenChange={(open) => { if (!open) { setRepoServer(null); setSelectedNars(new Set()); } }}>
        <DialogContent className="max-w-2xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle>NAR Repository — {repoServer?.name}</DialogTitle>
            <DialogDescription>
              {repoServer?.nar_directory} — remote files on {repoServer?.ssh_host}
            </DialogDescription>
          </DialogHeader>
          {narsLoading ? (
            <p className="text-sm text-muted-foreground">Loading remote files…</p>
          ) : remoteNars && remoteNars.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm text-muted-foreground">{remoteNars.length} file(s)</p>
                {isAdmin && selectedNars.size > 0 && (
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={deletingNars}
                    onClick={() => {
                      setDeletingNars(true);
                      deleteNarsMutation.mutate(Array.from(selectedNars));
                    }}
                  >
                    <Trash2 className="h-4 w-4" /> Delete {selectedNars.size} file(s)
                  </Button>
                )}
              </div>
              <div className="rounded-md border max-h-[50vh] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 sticky top-0">
                    <tr>
                      {isAdmin && (
                        <th className="w-8 p-2">
                          <input
                            type="checkbox"
                            className="accent-primary"
                            checked={remoteNars.length > 0 && selectedNars.size === remoteNars.length}
                            onChange={(e) => {
                              if (e.target.checked) setSelectedNars(new Set(remoteNars.map((n) => n.filename)));
                              else setSelectedNars(new Set());
                            }}
                          />
                        </th>
                      )}
                      <th className="text-left p-2 font-medium">Filename</th>
                      <th className="text-right p-2 font-medium">Size</th>
                      <th className="text-right p-2 font-medium">Modified</th>
                    </tr>
                  </thead>
                  <tbody>
                    {remoteNars.map((nar) => (
                      <tr key={nar.filename} className="border-t hover:bg-muted/30">
                        {isAdmin && (
                          <td className="p-2">
                            <input
                              type="checkbox"
                              className="accent-primary"
                              checked={selectedNars.has(nar.filename)}
                              onChange={(e) => {
                                const next = new Set(selectedNars);
                                if (e.target.checked) next.add(nar.filename);
                                else next.delete(nar.filename);
                                setSelectedNars(next);
                              }}
                            />
                          </td>
                        )}
                        <td className="p-2 font-mono text-xs">{nar.filename}</td>
                        <td className="p-2 text-right text-xs text-muted-foreground">{formatBytes(nar.size_bytes)}</td>
                        <td className="p-2 text-right text-xs text-muted-foreground">{nar.modified ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <EmptyState
              icon={FolderOpen}
              title="No remote NAR files found"
              description={`The directory ${repoServer?.nar_directory} is empty or unreachable.`}
            />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete server "${deleting?.name}"?`}
        description="This removes the server registration. Existing deployment history is kept."
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />
    </div>
  );
}

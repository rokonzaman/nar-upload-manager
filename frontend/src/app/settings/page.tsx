"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type {
  ApiTokenCreated,
  ApiTokenOut,
  NotificationConfigOut,
  SettingsResponse,
  UserOut,
} from "@/lib/types";
import { NOTIFICATION_EVENTS } from "@/lib/types";
import { PageHeader } from "@/components/layout/page-header";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DeployEnvironmentsSelect } from "@/components/deploy-environments-select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatRelative } from "@/lib/utils";
import { Bell, Copy, KeyRound, Plus, Send, Trash2, Users as UsersIcon } from "lucide-react";

// ---------------------------------------------------------------------------
// General settings tab
// ---------------------------------------------------------------------------
function GeneralTab() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsResponse>("/settings/"),
  });
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    if (data) {
      setValues(Object.fromEntries(data.settings.map((s) => [s.key, s.value ?? ""])));
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: () => api.put("/settings/", { values }),
    onSuccess: () => {
      toast.success("Settings saved");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Runtime settings</CardTitle>
        <CardDescription>Changes take effect immediately and are audited. No restart or code change required.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {data?.settings.map((setting) => (
          <div key={setting.key} className="grid sm:grid-cols-2 gap-2 items-center">
            <div>
              <p className="text-sm font-medium font-mono">{setting.key}</p>
              <p className="text-xs text-muted-foreground">{setting.description}</p>
            </div>
            <Input
              value={values[setting.key] ?? ""}
              onChange={(e) => setValues((prev) => ({ ...prev, [setting.key]: e.target.value }))}
            />
          </div>
        ))}
        {data && (
          <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground space-y-1">
            <p>App: {String(data.config.app_name)} v{String(data.config.version).replace(/^v/i, "")}</p>
            <p>Environments: {(data.config.environments as string[]).join(", ")}</p>
            <p>Keycloak SSO: {String(data.config.keycloak_enabled)} — Dev mode: {String(data.config.dev_mode)}</p>
          </div>
        )}
        <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          Save settings
        </Button>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Notifications tab
// ---------------------------------------------------------------------------
function NotificationsTab() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<NotificationConfigOut | null>(null);
  const [events, setEvents] = useState<Set<string>>(new Set());

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<NotificationConfigOut[]>("/settings/notifications"),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post("/settings/notifications", payload),
    onSuccess: () => {
      toast.success("Notification config created");
      setDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/settings/notifications/${id}`),
    onSuccess: () => {
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => api.post(`/settings/notifications/${id}/test`),
    onSuccess: () => toast.success("Test notification sent"),
    onError: (error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Notification channels</CardTitle>
          <CardDescription>Email, Slack, Teams and generic webhooks for system events</CardDescription>
        </div>
        <Button onClick={() => { setEvents(new Set()); setDialogOpen(true); }}>
          <Plus className="h-4 w-4" /> Add channel
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Target</TableHead>
              <TableHead>Events</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.map((config) => (
              <TableRow key={config.id}>
                <TableCell className="font-medium">{config.name}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className="capitalize">{config.type}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs max-w-[220px] truncate">{config.target}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{config.events || "all"}</TableCell>
                <TableCell>{config.is_enabled ? "yes" : "no"}</TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" title="Send test" onClick={() => testMutation.mutate(config.id)}>
                      <Send className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" title="Delete" onClick={() => setDeleting(config)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  No notification channels configured.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add notification channel</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              createMutation.mutate({
                name: form.get("name"),
                type: form.get("type"),
                target: form.get("target"),
                events: Array.from(events),
                is_enabled: true,
              });
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="name">Name *</Label>
                <Input id="name" name="name" required />
              </div>
              <div className="space-y-2">
                <Label>Type *</Label>
                <Select name="type" defaultValue="slack">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="slack">Slack webhook</SelectItem>
                    <SelectItem value="teams">Microsoft Teams</SelectItem>
                    <SelectItem value="email">Email</SelectItem>
                    <SelectItem value="webhook">Generic webhook</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="target">Target (webhook URL or email) *</Label>
              <Input id="target" name="target" placeholder="https://hooks.slack.com/services/…" required />
            </div>
            <div className="space-y-2">
              <Label>Events (empty = all)</Label>
              <div className="grid grid-cols-2 gap-2">
                {NOTIFICATION_EVENTS.map((event) => (
                  <label key={event} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={events.has(event)}
                      onCheckedChange={(checked) => {
                        setEvents((prev) => {
                          const next = new Set(prev);
                          if (checked) next.add(event);
                          else next.delete(event);
                          return next;
                        });
                      }}
                    />
                    {event}
                  </label>
                ))}
              </div>
            </div>
            <DialogFooter>
              <Button type="submit" disabled={createMutation.isPending}>Create</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete channel "${deleting?.name}"?`}
        description="Notifications for this channel will stop immediately."
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// API tokens tab
// ---------------------------------------------------------------------------
function TokensTab() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);
  const [revoking, setRevoking] = useState<ApiTokenOut | null>(null);

  const { data } = useQuery({
    queryKey: ["api-tokens"],
    queryFn: () => api.get<ApiTokenOut[]>("/settings/api-tokens"),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post<ApiTokenCreated>("/settings/api-tokens", payload),
    onSuccess: (token) => {
      setCreated(token);
      setDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: number) => api.del(`/settings/api-tokens/${id}`),
    onSuccess: () => {
      toast.success("Token revoked");
      setRevoking(null);
      queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>API tokens</CardTitle>
          <CardDescription>For CI/CD pipelines — pass as <code className="font-mono">X-API-Key</code> header</CardDescription>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> New token
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Prefix</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>Last used</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.map((token) => (
              <TableRow key={token.id}>
                <TableCell className="font-medium">{token.name}</TableCell>
                <TableCell className="font-mono text-xs">{token.prefix}…</TableCell>
                <TableCell><Badge variant="secondary" className="capitalize">{token.role}</Badge></TableCell>
                <TableCell className="text-sm">{formatRelative(token.created_at)}</TableCell>
                <TableCell className="text-sm">{token.expires_at ? formatRelative(token.expires_at) : "never"}</TableCell>
                <TableCell className="text-sm">{token.last_used_at ? formatRelative(token.last_used_at) : "never"}</TableCell>
                <TableCell>{token.is_active ? <Badge>active</Badge> : <Badge variant="secondary">revoked</Badge>}</TableCell>
                <TableCell>
                  {token.is_active && (
                    <Button variant="ghost" size="icon" onClick={() => setRevoking(token)}>
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                  No API tokens yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API token</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              const expires = String(form.get("expires_days") ?? "");
              createMutation.mutate({
                name: form.get("name"),
                role: form.get("role"),
                expires_days: expires ? Number(expires) : null,
              });
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input id="name" name="name" placeholder="gitlab-ci" required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Role</Label>
                <Select name="role" defaultValue="developer">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Viewer</SelectItem>
                    <SelectItem value="developer">Developer</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="expires_days">Expires (days, optional)</Label>
                <Input id="expires_days" name="expires_days" type="number" min={1} placeholder="90" />
              </div>
            </div>
            <DialogFooter>
              <Button type="submit" disabled={createMutation.isPending}>Create token</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!created} onOpenChange={(open) => !open && setCreated(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Token created — copy it now</DialogTitle>
            <DialogDescription>This is the only time the token is shown.</DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2 rounded-md border bg-muted/50 p-3">
            <code className="text-xs font-mono break-all flex-1">{created?.token}</code>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                if (created) navigator.clipboard.writeText(created.token);
                toast.success("Token copied");
              }}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!revoking}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke token "${revoking?.name}"?`}
        description="Any CI/CD pipeline using this token will immediately lose access."
        confirmLabel="Revoke"
        destructive
        onConfirm={() => revoking && revokeMutation.mutate(revoking.id)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Users tab
// ---------------------------------------------------------------------------
function UsersTab() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<UserOut | null>(null);
  const [newUserEnvs, setNewUserEnvs] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserOut[]>("/auth/users"),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.post<UserOut>("/auth/users", payload),
    onSuccess: () => {
      toast.success("User created");
      setDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...payload }: { id: number; role?: string; is_active?: boolean; deploy_environments?: string | null }) =>
      api.put(`/auth/users/${id}`, payload),
    onSuccess: () => {
      toast.success("User updated");
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/auth/users/${id}`),
    onSuccess: () => {
      toast.success("User deleted");
      setDeleting(null);
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Users</CardTitle>
          <CardDescription>
            Roles are managed here — Keycloak handles sign-in only. New SSO users start as Viewer;
            usernames in ADMIN_USERNAMES always get Administrator.
          </CardDescription>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> Create user
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Deploy environments</TableHead>
              <TableHead>Last login</TableHead>
              <TableHead>Active</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.map((user) => (
              <TableRow key={user.id}>
                <TableCell>
                  <p className="font-medium">{user.full_name ?? user.username}</p>
                  <p className="text-xs text-muted-foreground">{user.username}{user.email ? ` — ${user.email}` : ""}</p>
                </TableCell>
                <TableCell>
                  <Select
                    value={user.role}
                    onValueChange={(role) => updateMutation.mutate({ id: user.id, role })}
                  >
                    <SelectTrigger className="w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">Administrator</SelectItem>
                      <SelectItem value="developer">Developer</SelectItem>
                      <SelectItem value="viewer">Viewer</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <DeployEnvironmentsSelect
                    value={user.deploy_environments}
                    onChange={(val) => updateMutation.mutate({ id: user.id, deploy_environments: val })}
                  />
                </TableCell>
                <TableCell className="text-sm">{user.last_login ? formatRelative(user.last_login) : "never"}</TableCell>
                <TableCell>
                  <Switch
                    checked={user.is_active}
                    onCheckedChange={(is_active) => updateMutation.mutate({ id: user.id, is_active })}
                  />
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" onClick={() => setDeleting(user)}>
                    <Trash2 className="h-4 w-4 text-red-500" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>

      <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) setNewUserEnvs(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create local user</DialogTitle>
            <DialogDescription>Set a password for local dev-mode login.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              createMutation.mutate({
                username: form.get("username"),
                password: form.get("password"),
                role: form.get("role"),
                email: form.get("email") || null,
                full_name: form.get("full_name") || null,
                deploy_environments: newUserEnvs,
              });
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="username">Username *</Label>
                <Input id="username" name="username" required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password *</Label>
                <Input id="password" name="password" type="password" required />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="full_name">Full name</Label>
                <Input id="full_name" name="full_name" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" name="email" type="email" />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select name="role" defaultValue="developer">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="viewer">Viewer</SelectItem>
                  <SelectItem value="developer">Developer</SelectItem>
                  <SelectItem value="admin">Administrator</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Deploy environments</Label>
              <DeployEnvironmentsSelect
                value={newUserEnvs}
                onChange={setNewUserEnvs}
              />
              <p className="text-xs text-muted-foreground">Restricts developer deployment targets. Admins are unrestricted.</p>
            </div>
            <DialogFooter>
              <Button type="submit" disabled={createMutation.isPending}>Create user</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete user "${deleting?.username}"?`}
        description="This cannot be undone. The user will lose all access immediately."
        confirmLabel="Delete"
        destructive
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="System configuration, notifications, API tokens and user management" />
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">
            <KeyRound className="h-4 w-4 mr-1" /> General
          </TabsTrigger>
          <TabsTrigger value="notifications">
            <Bell className="h-4 w-4 mr-1" /> Notifications
          </TabsTrigger>
          <TabsTrigger value="tokens">
            <KeyRound className="h-4 w-4 mr-1" /> API Tokens
          </TabsTrigger>
          <TabsTrigger value="users">
            <UsersIcon className="h-4 w-4 mr-1" /> Users
          </TabsTrigger>
        </TabsList>
        <TabsContent value="general"><GeneralTab /></TabsContent>
        <TabsContent value="notifications"><NotificationsTab /></TabsContent>
        <TabsContent value="tokens"><TokensTab /></TabsContent>
        <TabsContent value="users"><UsersTab /></TabsContent>
      </Tabs>
    </div>
  );
}

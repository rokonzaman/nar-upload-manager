"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatBytes, formatRelative } from "@/lib/utils";
import type {
  AuditLogOut,
  DashboardCharts,
  DashboardStats,
  DeploymentOut,
  NarBundleOut,
} from "@/lib/types";
import { PageHeader } from "@/components/layout/page-header";
import { StatCard } from "@/components/stat-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DeploymentStatusBadge } from "@/components/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  ArchiveRestore,
  HardDrive,
  Package,
  Rocket,
  Server,
  Timer,
  Layers,
} from "lucide-react";

const CHART_COLOR = "hsl(217.2 91.2% 59.8%)";
const CHART_COLOR_2 = "hsl(142.1 76.2% 36.3%)";

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.get<DashboardStats>("/dashboard/stats"),
  });
  const { data: charts, isLoading: chartsLoading } = useQuery({
    queryKey: ["dashboard-charts"],
    queryFn: () => api.get<DashboardCharts>("/dashboard/charts", { days: 30 }),
  });
  const { data: recentUploads } = useQuery({
    queryKey: ["recent-uploads"],
    queryFn: () => api.get<NarBundleOut[]>("/dashboard/recent-uploads", { limit: 5 }),
  });
  const { data: recentDeployments } = useQuery({
    queryKey: ["recent-deployments"],
    queryFn: () => api.get<DeploymentOut[]>("/dashboard/recent-deployments", { limit: 5 }),
  });
  const { data: activity } = useQuery({
    queryKey: ["recent-activity"],
    queryFn: () => api.get<AuditLogOut[]>("/dashboard/activity", { limit: 10 }),
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" description="Overview of your NiFi NAR ecosystem" />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="NiFi Servers" value={stats ? `${stats.enabled_servers}/${stats.total_servers}` : "—"} description="enabled / registered" icon={Server} loading={statsLoading} />
        <StatCard title="NAR Bundles" value={stats?.total_bundles ?? "—"} description={`${stats?.active_versions ?? 0} active versions`} icon={Package} loading={statsLoading} />
        <StatCard title="Storage Used" value={stats ? formatBytes(stats.storage_bytes) : "—"} description={`${formatBytes(stats?.backup_bytes)} in backups`} icon={HardDrive} loading={statsLoading} />
        <StatCard title="Deployments" value={stats?.total_deployments ?? "—"} description={`${stats?.failed_deployments ?? 0} failed`} icon={Rocket} loading={statsLoading} accent={stats && stats.failed_deployments > 0 ? "text-red-500" : undefined} />
        <StatCard title="Pending Cleanup" value={stats?.pending_cleanup ?? "—"} description="bundles eligible for retention" icon={Timer} loading={statsLoading} accent="text-amber-500" />
        <StatCard title="Backups" value={stats?.total_backups ?? "—"} description="restore points available" icon={ArchiveRestore} loading={statsLoading} />
        <StatCard title="Failed Deployments" value={stats?.failed_deployments ?? "—"} description="require attention" icon={AlertTriangle} loading={statsLoading} accent="text-red-500" />
        <StatCard title="Bundle Groups" value={charts?.top_bundles.length ?? "—"} description="tracked artifacts" icon={Layers} loading={chartsLoading} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Upload History</CardTitle>
            <CardDescription>NAR uploads over the last 30 days</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {chartsLoading ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={charts?.uploads ?? []}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
                  <YAxis allowDecimals={false} fontSize={11} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                  <Bar dataKey="count" fill={CHART_COLOR} radius={[4, 4, 0, 0]} name="Uploads" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Deployment Frequency</CardTitle>
            <CardDescription>Deployments over the last 30 days</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {chartsLoading ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={charts?.deployments ?? []}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
                  <YAxis allowDecimals={false} fontSize={11} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                  <Area type="monotone" dataKey="count" stroke={CHART_COLOR_2} fill={CHART_COLOR_2} fillOpacity={0.2} name="Deployments" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Storage Growth</CardTitle>
            <CardDescription>Cumulative repository size</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {chartsLoading ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={charts?.storage_growth ?? []}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
                  <YAxis tickFormatter={(v: number) => formatBytes(v, 0)} fontSize={11} />
                  <Tooltip
                    formatter={(value: number) => [formatBytes(value), "Storage"]}
                    contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                  />
                  <Line type="monotone" dataKey="bytes" stroke={CHART_COLOR} dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Most Deployed Bundles</CardTitle>
            <CardDescription>Top artifacts by deployment count</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {chartsLoading ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={charts?.top_bundles ?? []} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis type="number" allowDecimals={false} fontSize={11} />
                  <YAxis type="category" dataKey="artifact" width={180} fontSize={11} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
                  <Bar dataKey="deployment_count" fill={CHART_COLOR} radius={[0, 4, 4, 0]} name="Deployments" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Latest Uploads</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentUploads?.length === 0 && <p className="text-sm text-muted-foreground">No uploads yet.</p>}
            {recentUploads?.map((bundle) => (
              <div key={bundle.id} className="flex items-center justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="font-medium truncate">{bundle.artifact}</p>
                  <p className="text-xs text-muted-foreground">v{bundle.version} by {bundle.uploaded_by}</p>
                </div>
                <span className="text-xs text-muted-foreground shrink-0">{formatRelative(bundle.uploaded_at)}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Latest Deployments</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentDeployments?.length === 0 && <p className="text-sm text-muted-foreground">No deployments yet.</p>}
            {recentDeployments?.map((deployment) => (
              <div key={deployment.id} className="flex items-center justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="font-medium truncate">
                    {deployment.bundle?.artifact}:{deployment.bundle?.version}
                  </p>
                  <p className="text-xs text-muted-foreground">→ {deployment.server?.name}</p>
                </div>
                <DeploymentStatusBadge status={deployment.status} />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4" /> Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {activity?.length === 0 && <p className="text-sm text-muted-foreground">No activity yet.</p>}
            {activity?.map((entry) => (
              <div key={entry.id} className="text-sm">
                <p className="font-medium">
                  {entry.action} <span className="text-muted-foreground font-normal">by {entry.username}</span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {entry.bundle && `${entry.bundle}${entry.version ? `:${entry.version}` : ""} · `}
                  {formatRelative(entry.timestamp)}
                </p>
              </div>
            ))}
            <Link href="/audit" className="text-xs text-primary hover:underline block pt-1">
              View all audit logs →
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

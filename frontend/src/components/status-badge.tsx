import { Badge } from "@/components/ui/badge";
import { cn, DEPLOYMENT_STATUS_COLORS, ENVIRONMENT_COLORS, BUNDLE_STATUS_COLORS } from "@/lib/utils";

export function DeploymentStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("capitalize", DEPLOYMENT_STATUS_COLORS[status] ?? "")}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

export function EnvironmentBadge({ environment }: { environment: string }) {
  return (
    <Badge variant="outline" className={cn("font-mono", ENVIRONMENT_COLORS[environment] ?? "")}>
      {environment}
    </Badge>
  );
}

export function BundleStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("capitalize", BUNDLE_STATUS_COLORS[status] ?? "")}>
      {status}
    </Badge>
  );
}

export function EnabledBadge({ enabled }: { enabled: boolean }) {
  return (
    <Badge
      variant="outline"
      className={enabled ? "bg-emerald-500/15 text-emerald-500 border-emerald-500/30" : "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"}
    >
      {enabled ? "enabled" : "disabled"}
    </Badge>
  );
}

export function ResultBadge({ result }: { result: string }) {
  return (
    <Badge
      variant="outline"
      className={result === "success" ? "bg-emerald-500/15 text-emerald-500 border-emerald-500/30" : "bg-red-500/15 text-red-500 border-red-500/30"}
    >
      {result}
    </Badge>
  );
}

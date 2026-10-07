import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number | null | undefined, decimals = 1): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
}

export function formatDate(date: string | Date | null | undefined): string {
  if (!date) return "—";
  return new Date(date).toLocaleString();
}

export function formatRelative(date: string | Date | null | undefined): string {
  if (!date) return "—";
  const then = new Date(date).getTime();
  const diff = Date.now() - then;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(date).toLocaleDateString();
}

export const DEPLOYMENT_STATUS_COLORS: Record<string, string> = {
  success: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
  failed: "bg-red-500/15 text-red-500 border-red-500/30",
  in_progress: "bg-blue-500/15 text-blue-500 border-blue-500/30",
  pending: "bg-amber-500/15 text-amber-500 border-amber-500/30",
  rolled_back: "bg-purple-500/15 text-purple-500 border-purple-500/30",
  cancelled: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

export const ENVIRONMENT_COLORS: Record<string, string> = {
  DEV: "bg-blue-500/15 text-blue-500 border-blue-500/30",
  QA: "bg-amber-500/15 text-amber-500 border-amber-500/30",
  UAT: "bg-purple-500/15 text-purple-500 border-purple-500/30",
  STAGING: "bg-purple-500/15 text-purple-500 border-purple-500/30",
  PROD: "bg-red-500/15 text-red-500 border-red-500/30",
};

export const BUNDLE_STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
  deprecated: "bg-amber-500/15 text-amber-500 border-amber-500/30",
  archived: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

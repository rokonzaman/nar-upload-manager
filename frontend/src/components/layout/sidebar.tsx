"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/use-auth";
import {
  LayoutDashboard,
  Server,
  Package,
  UploadCloud,
  Rocket,
  ArchiveRestore,
  Database,
  Timer,
  ScrollText,
  Settings,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/servers", label: "Servers", icon: Server },
  { href: "/repository", label: "Repository", icon: Package },
  { href: "/upload", label: "Upload", icon: UploadCloud },
  { href: "/deployments", label: "Deployments", icon: Rocket },
  { href: "/backups", label: "Backups", icon: ArchiveRestore },
  { href: "/nexus", label: "Nexus", icon: Database },
  { href: "/retention", label: "Retention", icon: Timer },
  { href: "/audit", label: "Audit Logs", icon: ScrollText, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const { isAdmin } = useAuth();

  return (
    <aside className="hidden md:flex w-16 lg:w-60 flex-col border-r bg-card/50 min-h-screen sticky top-0">
      <div className="flex items-center gap-2 px-4 h-16 border-b">
        <Package className="h-6 w-6 text-primary shrink-0" />
        <span className="font-semibold hidden lg:inline truncate">NAR Manager</span>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin).map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
              title={item.label}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              <span className="hidden lg:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/use-auth";
import { ChevronRight, LogOut, Moon, Sun, User } from "lucide-react";
import { Fragment } from "react";

function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return <span className="text-sm text-muted-foreground">Dashboard</span>;
  return (
    <nav className="flex items-center text-sm text-muted-foreground">
      <Link href="/" className="hover:text-foreground">
        Home
      </Link>
      {segments.map((segment, index) => (
        <Fragment key={segment}>
          <ChevronRight className="h-3 w-3 mx-1" />
          <Link
            href={`/${segments.slice(0, index + 1).join("/")}`}
            className="capitalize hover:text-foreground"
          >
            {segment}
          </Link>
        </Fragment>
      ))}
    </nav>
  );
}

export function Topbar() {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();

  return (
    <header className="h-16 border-b flex items-center justify-between px-6 sticky top-0 bg-background/95 backdrop-blur z-40">
      <Breadcrumbs />
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          title="Toggle theme"
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2">
              <User className="h-4 w-4" />
              <span className="hidden sm:inline">{user?.full_name ?? user?.username}</span>
              <Badge variant="secondary" className="capitalize">
                {user?.role}
              </Badge>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span>{user?.full_name ?? user?.username}</span>
                <span className="text-xs font-normal text-muted-foreground">{user?.email ?? user?.username}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => void logout()} className="text-red-500 focus:text-red-500">
              <LogOut className="h-4 w-4" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

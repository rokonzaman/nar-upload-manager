"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface Props {
  value: string | null;
  onChange: (value: string | null) => void;
}

function parseEnvs(val: string | null): string[] {
  return val
    ? val.split(",").map((e) => e.trim().toUpperCase()).filter(Boolean)
    : [];
}

export function DeployEnvironmentsSelect({ value, onChange }: Props) {
  const { data: environments } = useQuery({
    queryKey: ["environments"],
    queryFn: () => api.get<string[]>("/servers/environments"),
  });

  const [selected, setSelected] = useState<string[]>(() => parseEnvs(value));

  useEffect(() => {
    setSelected(parseEnvs(value));
  }, [value]);

  const allEnvs = environments ?? ["DEV", "QA", "PROD"];

  const toggle = (env: string) => {
    const next = selected.includes(env)
      ? selected.filter((e) => e !== env)
      : [...selected, env];
    setSelected(next);
    onChange(next.length > 0 ? next.join(",") : null);
  };

  const label =
    selected.length > 0 ? (
      <div className="flex gap-1 flex-wrap">
        {selected.map((e) => (
          <Badge key={e} variant="secondary" className="text-xs">
            {e}
          </Badge>
        ))}
      </div>
    ) : (
      <span className="text-muted-foreground text-xs">All environments</span>
    );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="h-9 w-44 justify-between px-2">
          {label}
          <ChevronsUpDown className="h-3 w-3 ml-1 shrink-0 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-44">
        {allEnvs.map((env) => (
          <DropdownMenuItem key={env} onSelect={(e) => { e.preventDefault(); toggle(env); }}>
            <div className="flex items-center gap-2 w-full">
              <div className="flex h-4 w-4 items-center justify-center">
                {selected.includes(env) && <Check className="h-4 w-4" />}
              </div>
              <span>{env}</span>
            </div>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
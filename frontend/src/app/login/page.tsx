"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import type { AuthConfig } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { KeyRound, Loader2, Package } from "lucide-react";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [submitting, setSubmitting] = useState(false);

  const { data: config } = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => api.get<AuthConfig>("/auth/config"),
    retry: false,
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (values: LoginForm) => {
    setSubmitting(true);
    try {
      const user = await login(values.username, values.password);
      toast.success(`Welcome back, ${user.full_name ?? user.username}`);
      router.push("/");
    } catch (error) {
      toast.error((error as Error).message || "Invalid credentials");
    } finally {
      setSubmitting(false);
    }
  };

  const startSso = async () => {
    try {
      const redirectUri = `${window.location.origin}/login/callback`;
      const { authorization_url } = await api.get<{ authorization_url: string }>("/auth/keycloak/login", {
        redirect_uri: redirectUri,
      });
      window.location.href = authorization_url;
    } catch (error) {
      toast.error((error as Error).message);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-primary/10 p-4">
      <Card className="w-full max-w-md shadow-xl">
        <CardHeader className="text-center space-y-3">
          <div className="mx-auto rounded-full bg-primary/10 p-3 w-fit">
            <Package className="h-8 w-8 text-primary" />
          </div>
          <CardTitle className="text-2xl">{config?.app_name ?? "NiFi NAR Manager"}</CardTitle>
          <CardDescription>Sign in to manage your NiFi NAR deployments</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {(config?.dev_mode ?? true) && (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input id="username" autoComplete="username" {...register("username")} />
                {errors.username && <p className="text-xs text-destructive">{errors.username.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
                {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
              </div>
              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                Sign in
              </Button>
            </form>
          )}
          {config?.keycloak_enabled && (
            <>
              {config.dev_mode && <Separator />}
              <Button variant="outline" className="w-full" onClick={startSso}>
                <KeyRound className="h-4 w-4" /> Sign in with SSO (Keycloak)
              </Button>
            </>
          )}
          <p className="text-center text-xs text-muted-foreground">
            v{String(config?.version ?? "…").replace(/^v/i, "")}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

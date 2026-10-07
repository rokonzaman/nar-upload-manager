"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import type { TokenResponse } from "@/lib/types";
import { Loader2 } from "lucide-react";

function CallbackHandler() {
  const router = useRouter();
  const params = useSearchParams();
  const { loginWithToken } = useAuth();

  useEffect(() => {
    const code = params.get("code");
    if (!code) {
      toast.error("Missing authorization code");
      router.replace("/login");
      return;
    }
    api
      .post<TokenResponse>("/auth/keycloak/callback", {
        code,
        redirect_uri: `${window.location.origin}/login/callback`,
      })
      .then((response) => {
        loginWithToken(response);
        toast.success("Signed in via SSO");
        router.replace("/");
      })
      .catch((error) => {
        toast.error((error as Error).message);
        router.replace("/login");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex items-center gap-3 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" /> Completing sign-in…
      </div>
    </div>
  );
}

export default function LoginCallbackPage() {
  return (
    <Suspense>
      <CallbackHandler />
    </Suspense>
  );
}

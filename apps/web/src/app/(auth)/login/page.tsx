"use client";

import React from "react";
import { signIn } from "next-auth/react";
import { Shield } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-8 rounded-2xl border border-border bg-card p-8 shadow-xl gpu-glow">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10">
            <Shield className="h-8 w-8 text-primary" />
          </div>
          <h1 className="text-xl font-bold text-foreground">VisualSeek AI</h1>
          <p className="text-center text-sm text-muted-foreground">
            Sign in with your enterprise credentials
          </p>
        </div>

        {/* SSO Button */}
        <Button
          onClick={() => signIn("keycloak", { callbackUrl: "/cameras" })}
          className="w-full"
          size="lg"
        >
          Sign in with SSO
        </Button>

        {/* Footer */}
        <p className="text-center text-xs text-muted-foreground">
          Protected by enterprise-grade Keycloak SSO authentication
        </p>
      </div>
    </div>
  );
}

"use client";

import React from "react";
import { useSession, signOut } from "next-auth/react";
import { Bell, Search, LogOut, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useSearchStore } from "@/lib/store";

export function Header() {
  const { data: session } = useSession();
  const toggleSearch = useSearchStore((s) => s.toggle);

  const initials = session?.user?.name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) || "VQ";

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-6">
      {/* Left: breadcrumb area */}
      <div className="flex items-center gap-4">
        <h2 className="text-sm font-semibold text-foreground">Dashboard</h2>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2">
        {/* Search shortcut */}
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleSearch}
          className="hidden gap-2 text-muted-foreground sm:flex"
          aria-label="Open search dialog"
        >
          <Search className="h-4 w-4" />
          <span className="text-xs">Search</span>
          <kbd className="pointer-events-none ml-1 hidden rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground sm:inline-block">
            ⌘K
          </kbd>
        </Button>

        {/* Notifications */}
        <Button
          variant="ghost"
          size="icon"
          className="relative text-muted-foreground"
          aria-label="View notifications"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground">
            3
          </span>
        </Button>

        {/* Profile */}
        <div className="flex items-center gap-3 border-l border-border pl-3">
          <Avatar className="h-8 w-8">
            <AvatarImage src={session?.user?.image || ""} alt={session?.user?.name || "User"} />
            <AvatarFallback className="bg-primary/15 text-primary text-xs">
              {initials}
            </AvatarFallback>
          </Avatar>
          <div className="hidden flex-col md:flex">
            <span className="text-xs font-medium text-foreground">
              {session?.user?.name || "Guest"}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {session?.user?.role || "viewer"}
            </span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => signOut()}
            className="text-muted-foreground hover:text-destructive"
            aria-label="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  );
}

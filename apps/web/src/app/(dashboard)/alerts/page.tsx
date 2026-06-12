import React from "react";
import type { Metadata } from "next";
import { Bell } from "lucide-react";

export const metadata: Metadata = {
  title: "Alerts",
};

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
          <Bell className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-foreground">Alert Center</h1>
          <p className="text-sm text-muted-foreground">
            Real-time alerts and event notifications
          </p>
        </div>
      </div>
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-border">
        <p className="text-sm text-muted-foreground">Alert management coming soon</p>
      </div>
    </div>
  );
}

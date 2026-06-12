"use client";

import React from "react";
import { AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Notification {
  id: string;
  title: string;
  description: string;
  type: "info" | "warning" | "success" | "error";
  timestamp: string;
  read: boolean;
}

const mockNotifications: Notification[] = [
  {
    id: "1",
    title: "Camera Offline",
    description: "Front Lobby Camera has gone offline",
    type: "error",
    timestamp: "2 min ago",
    read: false,
  },
  {
    id: "2",
    title: "Object Detected",
    description: "Unrecognized vehicle in Parking Lot B",
    type: "warning",
    timestamp: "15 min ago",
    read: false,
  },
  {
    id: "3",
    title: "System Update",
    description: "Model v2.4 deployed successfully",
    type: "success",
    timestamp: "1 hr ago",
    read: true,
  },
];

const iconMap = {
  info: Info,
  warning: AlertTriangle,
  success: CheckCircle2,
  error: AlertTriangle,
};

const badgeMap = {
  info: "default" as const,
  warning: "warning" as const,
  success: "success" as const,
  error: "destructive" as const,
};

export function NotificationCenter() {
  return (
    <div className="w-80 rounded-lg border border-border bg-card p-4 shadow-xl">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Notifications</h3>
        <Badge variant="secondary">
          {mockNotifications.filter((n) => !n.read).length} new
        </Badge>
      </div>
      <div className="space-y-2">
        {mockNotifications.map((notification) => {
          const Icon = iconMap[notification.type];
          return (
            <div
              key={notification.id}
              className={cn(
                "flex gap-3 rounded-md p-2.5 transition-colors",
                notification.read
                  ? "opacity-60"
                  : "bg-muted/50"
              )}
            >
              <Icon
                className={cn(
                  "mt-0.5 h-4 w-4 shrink-0",
                  notification.type === "error" && "text-destructive",
                  notification.type === "warning" && "text-warning",
                  notification.type === "success" && "text-success",
                  notification.type === "info" && "text-info"
                )}
              />
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-foreground">
                    {notification.title}
                  </p>
                  <Badge variant={badgeMap[notification.type]} className="text-[10px]">
                    {notification.type}
                  </Badge>
                </div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {notification.description}
                </p>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  {notification.timestamp}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

"use client";

import React from "react";
import { cn } from "@/lib/utils";
import type { CameraStatus } from "@/components/features/video-player/types";

interface StatusBadgeProps {
  status: CameraStatus;
  showLabel?: boolean;
  className?: string;
}

const STATUS_CONFIG: Record<CameraStatus, { color: string; bgColor: string; label: string; pulse: boolean }> = {
  online: {
    color: "bg-success",
    bgColor: "bg-success/10 text-success",
    label: "Online",
    pulse: true,
  },
  offline: {
    color: "bg-destructive",
    bgColor: "bg-destructive/10 text-destructive",
    label: "Offline",
    pulse: false,
  },
  degraded: {
    color: "bg-warning",
    bgColor: "bg-warning/10 text-warning",
    label: "Degraded",
    pulse: false,
  },
};

export function StatusBadge({ status, showLabel = true, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium",
        config.bgColor,
        className
      )}
      title={config.label}
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          config.color,
          config.pulse && "animate-pulse"
        )}
      />
      {showLabel && <span>{config.label}</span>}
    </div>
  );
}

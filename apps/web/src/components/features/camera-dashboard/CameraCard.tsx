"use client";

import React from "react";
import { Camera as CameraIcon, Plus, Eye, MapPin, Activity, Cpu } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "./StatusBadge";
import type { Camera } from "@/components/features/video-player/types";
import { useCameraStore } from "@/lib/store";

interface CameraCardProps {
  camera: Camera;
  isSelected: boolean;
  isActive: boolean;
  onSelect: () => void;
  onView: () => void;
}

export function CameraCard({
  camera,
  isSelected,
  isActive,
  onSelect,
  onView,
}: CameraCardProps) {
  const { cameraNames } = useCameraStore();
  const cameraName = cameraNames[camera.id] || camera.name;

  const healthColor = 
    camera.status === "online" 
      ? "bg-primary" 
      : camera.status === "degraded" 
      ? "bg-warning" 
      : "bg-destructive";

  const healthPercent = 
    camera.status === "online" 
      ? 100 
      : camera.status === "degraded" 
      ? 60 
      : 0;

  return (
    <div
      className={cn(
        "group flex flex-col gap-2 rounded-xl border p-3.5 transition-all duration-300 cursor-pointer glass select-none",
        isActive
          ? "border-primary/80 bg-primary/[0.03] gpu-glow-green"
          : isSelected
          ? "border-accent/40 bg-accent/[0.01]"
          : "border-border/80 bg-card/40 hover:border-accent/30 hover:bg-muted/15"
      )}
      onClick={onView}
      data-cursor="pointer"
    >
      <div className="flex items-center gap-3">
        {/* Camera icon / thumbnail */}
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
            camera.status === "online"
              ? "bg-primary/5 border-primary/20"
              : camera.status === "degraded"
              ? "bg-warning/5 border-warning/20"
              : "bg-muted/5 border-border"
          )}
        >
          <CameraIcon
            className={cn(
              "h-4.5 w-4.5",
              camera.status === "online"
                ? "text-primary animate-pulse"
                : camera.status === "degraded"
                ? "text-warning"
                : "text-muted-foreground/45"
            )}
          />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold text-foreground truncate uppercase tracking-wide">
              {cameraName}
            </span>
            <StatusBadge status={camera.status} showLabel={false} />
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="flex items-center gap-0.5 text-[9px] text-muted-foreground/60 font-semibold uppercase">
              <MapPin className="h-2.5 w-2.5 text-accent" />
              {camera.location}
            </span>
          </div>
        </div>
      </div>

      {/* Grid of details */}
      {camera.status !== "offline" && (
        <div className="grid grid-cols-3 gap-1.5 pt-1.5 border-t border-border/40 mt-1">
          <div className="bg-background/80 border border-border/40 rounded px-1 py-0.5 text-center">
            <div className="text-[7px] text-muted-foreground uppercase font-bold tracking-wider">Format</div>
            <div className="font-mono text-[9px] font-bold text-foreground">{camera.resolution}</div>
          </div>
          <div className="bg-background/80 border border-border/40 rounded px-1 py-0.5 text-center">
            <div className="text-[7px] text-muted-foreground uppercase font-bold tracking-wider">Stream</div>
            <div className="font-mono text-[9px] font-bold text-foreground">{camera.health.fps} FPS</div>
          </div>
          <div className="bg-background/80 border border-border/40 rounded px-1 py-0.5 text-center">
            <div className="text-[7px] text-muted-foreground uppercase font-bold tracking-wider">Bitrate</div>
            <div className="font-mono text-[9px] font-bold text-foreground">
              {(camera.health.bitrate / 1000).toFixed(1)}M
            </div>
          </div>
        </div>
      )}

      {/* Dynamic Health Bar & Quick Actions */}
      <div className="flex items-center justify-between gap-3 mt-1 pt-1.5 border-t border-border/30">
        {/* Health bar */}
        <div className="flex-1">
          <div className="flex justify-between text-[7px] font-bold uppercase tracking-wider text-muted-foreground/50 mb-0.5">
            <span>Core Health</span>
            <span>{healthPercent}%</span>
          </div>
          <div className="h-1 w-full bg-border/45 rounded-full overflow-hidden">
            <div 
              className={cn("h-full rounded-full transition-all duration-700 ease-out", healthColor)} 
              style={{ width: `${healthPercent}%` }} 
            />
          </div>
        </div>

        {/* Quick action buttons */}
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-accent hover:bg-accent/10"
            onClick={(e) => {
              e.stopPropagation();
              onView();
            }}
            title="Inspect feed"
          >
            <Eye className="h-3 w-3" />
          </Button>
          {!isSelected && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-primary hover:bg-primary/10"
              onClick={(e) => {
                e.stopPropagation();
                onSelect();
              }}
              title="Add to command grid"
            >
              <Plus className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

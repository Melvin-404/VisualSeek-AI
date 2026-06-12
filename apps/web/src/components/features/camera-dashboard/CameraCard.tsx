"use client";

import React from "react";
import { Camera as CameraIcon, Plus, Eye, MapPin, Activity } from "lucide-react";
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

  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-lg border p-3 transition-all duration-200 cursor-pointer",
        isActive
          ? "border-primary bg-primary/5 gpu-glow"
          : isSelected
            ? "border-primary/30 bg-card"
            : "border-border bg-card hover:border-primary/20 hover:bg-muted/30"
      )}
      onClick={onView}
    >
      {/* Camera icon / thumbnail */}
      <div
        className={cn(
          "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
          camera.status === "online"
            ? "bg-primary/10"
            : camera.status === "degraded"
              ? "bg-warning/10"
              : "bg-muted"
        )}
      >
        <CameraIcon
          className={cn(
            "h-5 w-5",
            camera.status === "online"
              ? "text-primary"
              : camera.status === "degraded"
                ? "text-warning"
                : "text-muted-foreground"
          )}
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {cameraName}
          </span>
          <StatusBadge status={camera.status} showLabel={false} />
        </div>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <MapPin className="h-3 w-3" />
            {camera.location}
          </span>
        </div>
        {camera.status !== "offline" && (
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[10px] text-muted-foreground">
              {camera.resolution}
            </span>
            <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
              <Activity className="h-3 w-3" />
              {camera.health.fps} fps
            </span>
            <span className="text-[10px] text-muted-foreground">
              {(camera.health.bitrate / 1000).toFixed(1)} Mbps
            </span>
            {camera.health.latencyMs > 100 && (
              <span className="text-[10px] text-warning">
                {camera.health.latencyMs}ms
              </span>
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground"
          onClick={(e) => {
            e.stopPropagation();
            onView();
          }}
          title="View camera"
        >
          <Eye className="h-3.5 w-3.5" />
        </Button>
        {!isSelected && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground"
            onClick={(e) => {
              e.stopPropagation();
              onSelect();
            }}
            title="Add to grid"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

"use client";

import React from "react";
import { Grid2x2, Grid3x3, Square, LayoutGrid } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCameraStore } from "@/lib/store";
import { VideoPlayer } from "./VideoPlayer";
import { DetectionOverlay } from "./DetectionOverlay";
import { GRID_CONFIGS } from "./types";
import type { Camera, Detection, GridLayout } from "./types";
import { Button } from "@/components/ui/button";

interface CameraGridProps {
  cameras: Camera[];
  detections: Map<string, Detection[]>;
  getDetectionsForCamera: (cameraId: string) => Detection[];
  onTimeUpdate?: (cameraId: string, time: number) => void;
  onDurationChange?: (cameraId: string, duration: number) => void;
}

const GRID_OPTIONS: { layout: GridLayout; icon: React.ComponentType<{ className?: string }>; label: string }[] = [
  { layout: "1x1", icon: Square, label: "Single" },
  { layout: "2x2", icon: Grid2x2, label: "2×2" },
  { layout: "3x3", icon: Grid3x3, label: "3×3" },
  { layout: "4x4", icon: LayoutGrid, label: "4×4" },
];

export function CameraGrid({
  cameras,
  detections,
  getDetectionsForCamera,
  onTimeUpdate,
  onDurationChange,
}: CameraGridProps) {
  const {
    gridLayout,
    setGridLayout,
    activeCameraId,
    setActiveCamera,
    fullscreenCameraId,
    setFullscreenCamera,
    selectedCameras,
  } = useCameraStore();

  const config = GRID_CONFIGS[gridLayout];

  // Get cameras to display based on selection
  const displayCameras = selectedCameras
    .slice(0, config.maxCameras)
    .map((id) => cameras.find((c) => c.id === id))
    .filter((c): c is Camera => c !== undefined);

  // Handle fullscreen camera
  if (fullscreenCameraId) {
    const camera = cameras.find((c) => c.id === fullscreenCameraId);
    if (camera) {
      return (
        <div className="relative">
          {/* Fullscreen exit button */}
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-foreground">{camera.name}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFullscreenCamera(null)}
            >
              Exit Fullscreen
            </Button>
          </div>
          <VideoPlayer
            camera={camera}
            isFullscreen={false}
            isActive
            onFullscreenToggle={() => setFullscreenCamera(null)}
          >
            <DetectionOverlay detections={getDetectionsForCamera(camera.id)} />
          </VideoPlayer>
        </div>
      );
    }
  }

  return (
    <div className="space-y-3">
      {/* Grid layout selector */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
        {GRID_OPTIONS.map(({ layout, icon: Icon, label }) => (
          <Button
            key={layout}
            variant={gridLayout === layout ? "default" : "ghost"}
            size="sm"
            className={cn(
              "gap-1.5 text-xs",
              gridLayout === layout && "bg-primary text-primary-foreground"
            )}
            onClick={() => setGridLayout(layout)}
            title={label}
          >
            <Icon className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{label}</span>
          </Button>
        ))}
      </div>

      {/* Camera grid */}
      <div
        className="grid gap-2 transition-all duration-300"
        style={{
          gridTemplateColumns: `repeat(${config.cols}, 1fr)`,
          gridTemplateRows: `repeat(${config.rows}, 1fr)`,
        }}
      >
        {displayCameras.map((camera) => (
          <VideoPlayer
            key={camera.id}
            camera={camera}
            isActive={activeCameraId === camera.id}
            showControls={gridLayout === "1x1" || gridLayout === "2x2"}
            onClick={() => setActiveCamera(camera.id)}
            onDoubleClick={() => setFullscreenCamera(camera.id)}
            onFullscreenToggle={() => {
              setFullscreenCamera(
                fullscreenCameraId === camera.id ? null : camera.id
              );
            }}
            onTimeUpdate={onTimeUpdate ? (time) => onTimeUpdate(camera.id, time) : undefined}
            onDurationChange={onDurationChange ? (duration) => onDurationChange(camera.id, duration) : undefined}
          >
            <DetectionOverlay detections={getDetectionsForCamera(camera.id)} />
          </VideoPlayer>
        ))}

        {/* Empty slots */}
        {Array.from({ length: Math.max(0, config.maxCameras - displayCameras.length) }).map((_, i) => (
          <div
            key={`empty-${i}`}
            className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-border bg-card/50"
          >
            <span className="text-xs text-muted-foreground">No camera assigned</span>
          </div>
        ))}
      </div>
    </div>
  );
}

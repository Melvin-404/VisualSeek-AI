"use client";

import React, { useState, useMemo, useCallback } from "react";
import {
  Camera,
  ChevronRight,
  ChevronLeft,
  Filter,
  Bookmark,
  Wifi,
  Clock,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useCameraStore } from "@/lib/store";
import { MOCK_CAMERAS, generateMockTimelineEvents } from "@/lib/mock-data";
import { useDetectionWebSocket } from "@/hooks/useDetectionWebSocket";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { CameraGrid } from "@/components/features/video-player/CameraGrid";
import { Timeline } from "@/components/features/video-player/Timeline";
import { CameraCard } from "@/components/features/camera-dashboard/CameraCard";
import { StatusBadge } from "@/components/features/camera-dashboard/StatusBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { CameraStatus } from "@/components/features/video-player/types";
import { GRID_CONFIGS } from "@/components/features/video-player/types";

const MOCK_DURATION = 3600; // 1 hour

export default function CamerasPage() {
  const {
    activeCameraId,
    setActiveCamera,
    selectedCameras,
    setSelectedCameras,
    fullscreenCameraId,
    bookmarks,
    addBookmark,
    cameraNames,
    gridLayout,
    requestSeek,
  } = useCameraStore();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [statusFilter, setStatusFilter] = useState<CameraStatus | "all">("all");

  // Track actual playback times and durations for visible cameras
  const [videoTimes, setVideoTimes] = useState<Record<string, number>>({});
  const [videoDurations, setVideoDurations] = useState<Record<string, number>>({});

  const handleTimeUpdate = useCallback((cameraId: string, time: number) => {
    setVideoTimes((prev) => ({ ...prev, [cameraId]: time }));
  }, []);

  const handleDurationChange = useCallback((cameraId: string, duration: number) => {
    setVideoDurations((prev) => ({ ...prev, [cameraId]: duration }));
  }, []);

  // WebSocket detections (mock in dev)
  const { getDetectionsForCamera, connectionStatus, latencyMs, detections } =
    useDetectionWebSocket({
      cameraIds: selectedCameras,
      enabled: true,
    });

  const activeDuration = videoDurations[activeCameraId || ""] || 30;

  // Timeline events for active camera
  const timelineEvents = useMemo(() => {
    if (!activeCameraId) return [];
    return generateMockTimelineEvents(activeCameraId, activeDuration);
  }, [activeCameraId, activeDuration]);

  // Cameras currently displayed in the preview frame (active grid)
  const visibleCameras = useMemo(() => {
    const config = GRID_CONFIGS[gridLayout];
    const activeGridCameraIds = selectedCameras.slice(0, config.maxCameras);
    return MOCK_CAMERAS.filter((c) => activeGridCameraIds.includes(c.id));
  }, [gridLayout, selectedCameras]);

  // Filter visible cameras
  const filteredCameras = useMemo(() => {
    if (statusFilter === "all") return visibleCameras;
    return visibleCameras.filter((c) => c.status === statusFilter);
  }, [visibleCameras, statusFilter]);

  // Camera counts by status (for visible cameras only)
  const statusCounts = useMemo(() => {
    const counts = { online: 0, offline: 0, degraded: 0 };
    visibleCameras.forEach((c) => counts[c.status]++);
    return counts;
  }, [visibleCameras]);

  const handleAddToGrid = useCallback(
    (cameraId: string) => {
      if (!selectedCameras.includes(cameraId)) {
        setSelectedCameras([...selectedCameras, cameraId]);
      }
    },
    [selectedCameras, setSelectedCameras]
  );

  const handleBookmark = useCallback(() => {
    if (!activeCameraId) return;
    const currentTime = videoTimes[activeCameraId] || 0;
    addBookmark({
      id: `bm-${Date.now()}`,
      cameraId: activeCameraId,
      startTime: currentTime,
      endTime: currentTime + 30,
      label: `Bookmark at ${new Date().toLocaleTimeString()}`,
      createdAt: new Date().toISOString(),
    });
  }, [activeCameraId, videoTimes, addBookmark]);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onBookmark: handleBookmark,
    enabled: !fullscreenCameraId,
  });

  return (
    <div className="flex h-full">
      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden p-4">
        {/* Top bar */}
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
              <Camera className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-base font-bold text-foreground">Camera Dashboard</h1>
              <p className="text-[11px] text-muted-foreground">
                {statusCounts.online} online • {statusCounts.degraded} degraded • {statusCounts.offline} offline
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Connection status */}
            <div className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5">
              <Wifi
                className={cn(
                  "h-3.5 w-3.5",
                  connectionStatus === "connected"
                    ? "text-success"
                    : "text-destructive"
                )}
              />
              <span className="text-[11px] text-muted-foreground">
                {connectionStatus === "connected"
                  ? `Live • ${latencyMs}ms`
                  : connectionStatus}
              </span>
            </div>

            {/* Bookmarks count */}
            {bookmarks.length > 0 && (
              <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                <Bookmark className="h-3.5 w-3.5" />
                {bookmarks.length}
              </Button>
            )}

            {/* Toggle sidebar */}
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label={sidebarOpen ? "Hide camera list" : "Show camera list"}
            >
              {sidebarOpen ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronLeft className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {/* Camera grid */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          <CameraGrid
            cameras={MOCK_CAMERAS}
            detections={detections}
            getDetectionsForCamera={getDetectionsForCamera}
            onTimeUpdate={handleTimeUpdate}
            onDurationChange={handleDurationChange}
          />
        </div>

        {/* Timeline (show when a camera is active) */}
        {activeCameraId && (
          <div className="mt-3 rounded-lg border border-border bg-card p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-medium text-foreground">
                  Timeline —{" "}
                  {cameraNames[activeCameraId] || MOCK_CAMERAS.find((c) => c.id === activeCameraId)?.name || "Camera"}
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-foreground p-0"
                onClick={() => setActiveCamera(null)}
                title="Close timeline"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
            <Timeline
              events={timelineEvents}
              currentTime={videoTimes[activeCameraId] || 0}
              duration={activeDuration}
              onSeek={(time) => requestSeek(activeCameraId, time)}
              onRangeSelect={(start, end) => {
                console.log("Export range:", start, end);
              }}
            />
          </div>
        )}
      </div>

      {/* Right sidebar — Camera list */}
      {sidebarOpen && (
        <div className="w-72 shrink-0 border-l border-border bg-sidebar overflow-y-auto">
          <div className="p-3">
            {/* Header */}
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">All Cameras</h2>
              <Badge variant="secondary">{visibleCameras.length}</Badge>
            </div>

            {/* Status filter */}
            <div className="mb-3 flex items-center gap-1">
              <Button
                variant={statusFilter === "all" ? "default" : "ghost"}
                size="sm"
                className="h-7 text-[11px]"
                onClick={() => setStatusFilter("all")}
              >
                All
              </Button>
              <Button
                variant={statusFilter === "online" ? "default" : "ghost"}
                size="sm"
                className="h-7 text-[11px]"
                onClick={() => setStatusFilter("online")}
              >
                Online ({statusCounts.online})
              </Button>
              <Button
                variant={statusFilter === "offline" ? "default" : "ghost"}
                size="sm"
                className="h-7 text-[11px]"
                onClick={() => setStatusFilter("offline")}
              >
                Offline ({statusCounts.offline})
              </Button>
            </div>

            {/* Camera list */}
            <div className="space-y-1.5">
              {filteredCameras.map((camera) => (
                <CameraCard
                  key={camera.id}
                  camera={camera}
                  isSelected={selectedCameras.includes(camera.id)}
                  isActive={activeCameraId === camera.id}
                  onSelect={() => handleAddToGrid(camera.id)}
                  onView={() => setActiveCamera(camera.id)}
                />
              ))}
            </div>
          </div>

          {/* Keyboard shortcuts help */}
          <div className="border-t border-border p-3">
            <p className="mb-1.5 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
              Keyboard Shortcuts
            </p>
            <div className="grid grid-cols-2 gap-y-1 text-[10px] text-muted-foreground">
              <span><kbd className="rounded border border-border bg-muted px-1">1-9</kbd> Select camera</span>
              <span><kbd className="rounded border border-border bg-muted px-1">F</kbd> Fullscreen</span>
              <span><kbd className="rounded border border-border bg-muted px-1">G</kbd> Change grid</span>
              <span><kbd className="rounded border border-border bg-muted px-1">B</kbd> Bookmark</span>
              <span><kbd className="rounded border border-border bg-muted px-1">P</kbd> PiP mode</span>
              <span><kbd className="rounded border border-border bg-muted px-1">Esc</kbd> Exit</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

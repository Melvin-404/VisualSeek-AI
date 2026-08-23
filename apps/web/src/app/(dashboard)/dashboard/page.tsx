"use client";

import React, { useState, useMemo, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Camera,
  Search,
  Wifi,
  Clock,
  X,
  Database,
  AlertTriangle,
  Activity,
  Bookmark,
  ChevronRight,
  ChevronLeft,
  Settings,
  History,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useCameraStore } from "@/lib/store";
import { MOCK_CAMERAS, generateMockTimelineEvents } from "@/lib/mock-data";
import { useDetectionWebSocket } from "@/hooks/useDetectionWebSocket";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { CameraGrid } from "@/components/features/video-player/CameraGrid";
import { Timeline } from "@/components/features/video-player/Timeline";
import { CameraCard } from "@/components/features/camera-dashboard/CameraCard";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { CameraStatus } from "@/components/features/video-player/types";
import { GRID_CONFIGS } from "@/components/features/video-player/types";
import { useSearchHistoryContext } from "@/contexts/SearchHistoryContext";

export default function DashboardPage() {
  const router = useRouter();
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

  const { history } = useSearchHistoryContext();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [statusFilter, setStatusFilter] = useState<CameraStatus | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Track playback time
  const [videoTimes, setVideoTimes] = useState<Record<string, number>>({});
  const [videoDurations, setVideoDurations] = useState<Record<string, number>>({});

  const handleTimeUpdate = useCallback((cameraId: string, time: number) => {
    setVideoTimes((prev) => ({ ...prev, [cameraId]: time }));
  }, []);

  const handleDurationChange = useCallback((cameraId: string, duration: number) => {
    setVideoDurations((prev) => ({ ...prev, [cameraId]: duration }));
  }, []);

  // WebSocket detections
  const { getDetectionsForCamera, connectionStatus, latencyMs, detections } =
    useDetectionWebSocket({
      cameraIds: selectedCameras,
      enabled: true,
    });

  const activeDuration = videoDurations[activeCameraId || ""] || 30;

  const timelineEvents = useMemo(() => {
    if (!activeCameraId) return [];
    return generateMockTimelineEvents(activeCameraId, activeDuration);
  }, [activeCameraId, activeDuration]);

  const visibleCameras = useMemo(() => {
    const config = GRID_CONFIGS[gridLayout];
    const activeGridCameraIds = selectedCameras.slice(0, config.maxCameras);
    return MOCK_CAMERAS.filter((c) => activeGridCameraIds.includes(c.id));
  }, [gridLayout, selectedCameras]);

  const filteredCameras = useMemo(() => {
    if (statusFilter === "all") return visibleCameras;
    return visibleCameras.filter((c) => c.status === statusFilter);
  }, [visibleCameras, statusFilter]);

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

  useKeyboardShortcuts({
    onBookmark: handleBookmark,
    enabled: !fullscreenCameraId,
  });

  const executeSearch = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) return;
    router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
  };

  const handleExampleClick = (query: string) => {
    setSearchQuery(query);
    router.push(`/search?q=${encodeURIComponent(query)}`);
  };

  return (
    <div className="flex h-full">
      {/* Center Main Dashboard Content */}
      <div className="flex flex-1 flex-col overflow-hidden p-6 space-y-6">
        
        {/* Row 3: Live Camera Grid Section */}
        <div className="flex-1 flex flex-col min-h-0 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="h-1.5 w-1.5 bg-primary rounded-full animate-ping" />
              <h2 className="text-sm font-bold text-foreground">Live Camera Overview</h2>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1">
                <Wifi
                  className={cn(
                    "h-3.5 w-3.5",
                    connectionStatus === "connected" ? "text-success" : "text-destructive"
                  )}
                />
                <span className="text-[10px] font-semibold text-muted-foreground">
                  {connectionStatus === "connected" ? `Connected • ${latencyMs}ms` : connectionStatus}
                </span>
              </div>
              <Button
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => setSidebarOpen(!sidebarOpen)}
                aria-label={sidebarOpen ? "Hide info sidebar" : "Show info sidebar"}
              >
                {sidebarOpen ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
              </Button>
            </div>
          </div>

          {/* Grid display */}
          <div className="flex-1 min-h-0 overflow-y-auto rounded-xl border border-border bg-card/30 p-2">
            <CameraGrid
              cameras={MOCK_CAMERAS}
              detections={detections}
              getDetectionsForCamera={getDetectionsForCamera}
              onTimeUpdate={handleTimeUpdate}
              onDurationChange={handleDurationChange}
            />
          </div>

          {/* Timeline details */}
          {activeCameraId && (
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs font-semibold text-foreground">
                    Timeline: {cameraNames[activeCameraId] || MOCK_CAMERAS.find((c) => c.id === activeCameraId)?.name || "Camera"}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  onClick={() => setActiveCamera(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <Timeline
                events={timelineEvents}
                currentTime={videoTimes[activeCameraId] || 0}
                duration={activeDuration}
                onSeek={(time) => requestSeek(activeCameraId, time)}
                onRangeSelect={(start, end) => console.log("Range selected:", start, end)}
              />
            </div>
          )}
        </div>
      </div>

      {/* Reorganized Right-Side Panel: Compact Information Sidebar */}
      {sidebarOpen && (
        <div className="w-80 shrink-0 border-l border-border bg-sidebar flex flex-col overflow-y-auto">
          
          {/* Section 1: ALL CAMERAS List */}
          <div className="p-4 border-b border-border space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider">All Cameras</h3>
              <Badge variant="secondary">{visibleCameras.length} Active</Badge>
            </div>
            
            {/* Filter buttons */}
            <div className="flex items-center gap-1.5">
              <Button
                variant={statusFilter === "all" ? "default" : "ghost"}
                size="sm"
                className="h-7 text-[10px] px-2.5 rounded-md"
                onClick={() => setStatusFilter("all")}
              >
                All
              </Button>
              <Button
                variant={statusFilter === "online" ? "default" : "ghost"}
                size="sm"
                className="h-7 text-[10px] px-2.5 rounded-md"
                onClick={() => setStatusFilter("online")}
              >
                Online ({statusCounts.online})
              </Button>
              <Button
                variant={statusFilter === "offline" ? "default" : "ghost"}
                size="sm"
                className="h-7 text-[10px] px-2.5 rounded-md"
                onClick={() => setStatusFilter("offline")}
              >
                Offline ({statusCounts.offline})
              </Button>
            </div>

            {/* Cameras Scroll list */}
            <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
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

          {/* Section 2: RECENT SEARCHES */}
          <div className="p-4 border-b border-border space-y-3">
            <h3 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
              <History className="h-3.5 w-3.5 text-primary" /> Recent Searches
            </h3>
            {history.length === 0 ? (
              <p className="text-[10px] text-muted-foreground italic px-1">No recent searches</p>
            ) : (
              <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                {history.slice(0, 3).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => router.push(`/search?q=${encodeURIComponent(item.query)}`)}
                    className="w-full text-left text-[11px] truncate bg-card/40 hover:bg-muted text-foreground border border-border px-2.5 py-1.5 rounded-lg transition-all"
                  >
                    {item.query}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Section 3: SHORTCUTS & ACTION OPTIONS */}
          <div className="p-4 border-b border-border space-y-3 flex-1">
            <h3 className="text-xs font-bold text-foreground uppercase tracking-wider">Shortcuts</h3>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                size="sm"
                className="text-[10px] py-3 h-auto justify-start gap-1.5 rounded-lg border-border"
                onClick={() => router.push("/history")}
              >
                <History className="h-3.5 w-3.5 text-primary" /> History Logs
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-[10px] py-3 h-auto justify-start gap-1.5 rounded-lg border-border"
                onClick={() => router.push("/analytics")}
              >
                <Activity className="h-3.5 w-3.5 text-primary" /> AI Analytics
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-[10px] py-3 h-auto justify-start gap-1.5 rounded-lg border-border"
                onClick={() => router.push("/settings")}
              >
                <Settings className="h-3.5 w-3.5 text-primary" /> System Config
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-[10px] py-3 h-auto justify-start gap-1.5 rounded-lg border-border"
                onClick={() => router.push("/alerts")}
              >
                <AlertTriangle className="h-3.5 w-3.5 text-primary" /> Alerts Feed
              </Button>
            </div>
          </div>

          {/* Keyboard Shortcuts Help */}
          <div className="bg-card/20 p-4 border-t border-border mt-auto">
            <p className="mb-2 text-[9px] font-bold text-muted-foreground uppercase tracking-wider">
              Control Panel Keybinds
            </p>
            <div className="grid grid-cols-2 gap-y-1.5 text-[10px] text-muted-foreground">
              <span><kbd className="rounded border border-border bg-muted px-1">1-9</kbd> Select Cam</span>
              <span><kbd className="rounded border border-border bg-muted px-1">F</kbd> Fullscreen</span>
              <span><kbd className="rounded border border-border bg-muted px-1">G</kbd> Grid Style</span>
              <span><kbd className="rounded border border-border bg-muted px-1">B</kbd> Bookmark</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

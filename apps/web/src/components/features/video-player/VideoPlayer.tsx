"use client";
import React, { useRef } from "react";
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Maximize,
  Minimize,
  PictureInPicture2,
  Wifi,
  WifiOff,
  Loader2,
  RotateCcw,
  Pencil,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useHlsPlayer } from "@/hooks/useHlsPlayer";
import { Button } from "@/components/ui/button";
import type { Camera } from "./types";
import { useCameraStore } from "@/lib/store";

interface VideoPlayerProps {
  camera: Camera;
  showControls?: boolean;
  isFullscreen?: boolean;
  isActive?: boolean;
  onFullscreenToggle?: () => void;
  onClick?: () => void;
  onDoubleClick?: () => void;
  onTimeUpdate?: (time: number) => void;
  onDurationChange?: (duration: number) => void;
  children?: React.ReactNode; // For overlay
}

export function VideoPlayer({
  camera,
  showControls = true,
  isFullscreen = false,
  isActive = false,
  onFullscreenToggle,
  onClick,
  onDoubleClick,
  onTimeUpdate,
  onDurationChange,
  children,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isMuted, setIsMuted] = React.useState(true);
  const [showControlsBar, setShowControlsBar] = React.useState(false);

  const { cameraNames, setCameraName, seekRequest, clearSeekRequest } = useCameraStore();
  const cameraName = cameraNames[camera.id] || camera.name;

  const [isEditing, setIsEditing] = React.useState(false);
  const [editValue, setEditValue] = React.useState(cameraName);

  React.useEffect(() => {
    setEditValue(cameraName);
  }, [cameraName]);

  React.useEffect(() => {
    if (seekRequest && seekRequest.cameraId === camera.id && videoRef.current) {
      videoRef.current.currentTime = seekRequest.time;
      clearSeekRequest();
    }
  }, [seekRequest, camera.id, clearSeekRequest]);
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    isPlaying,
    isBuffering,
    error,
    bandwidth,
    currentLevel,
    levels,
    togglePlay,
    togglePiP,
  } = useHlsPlayer(videoRef, {
    streamUrl: camera.status !== "offline" ? camera.streamUrl : "",
    autoplay: true,
    muted: true,
  });

  const handleMouseEnter = () => {
    if (showControls) {
      setShowControlsBar(true);
      if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
    }
  };

  const handleMouseLeave = () => {
    if (showControls) {
      hideTimeoutRef.current = setTimeout(() => setShowControlsBar(false), 2000);
    }
  };

  const handleMouseMove = () => {
    if (showControls) {
      setShowControlsBar(true);
      if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = setTimeout(() => setShowControlsBar(false), 2000);
    }
  };

  const toggleMute = () => {
    if (videoRef.current) {
      videoRef.current.muted = !videoRef.current.muted;
      setIsMuted(videoRef.current.muted);
    }
  };

  const currentRes = levels[currentLevel];

  // Offline state
  if (camera.status === "offline") {
    return (
      <div
        className={cn(
          "relative flex aspect-video items-center justify-center rounded-lg border bg-card",
          isActive ? "border-primary gpu-glow" : "border-border"
        )}
        onClick={onClick}
      >
        <div className="flex flex-col items-center gap-2 text-muted-foreground">
          <WifiOff className="h-8 w-8" />
          <span className="text-xs font-medium">No Signal</span>
          <span className="text-[10px]">{cameraName}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group relative aspect-video overflow-hidden rounded-lg border bg-black transition-all duration-200",
        isActive ? "border-primary gpu-glow" : "border-border hover:border-primary/30",
        isFullscreen && "fixed inset-0 z-50 rounded-none border-0"
      )}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onMouseMove={handleMouseMove}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
    >
      {/* Video element */}
      <video
        ref={videoRef}
        className="h-full w-full object-cover"
        muted={isMuted}
        playsInline
        crossOrigin="anonymous"
        loop
        onTimeUpdate={onTimeUpdate ? (e) => onTimeUpdate(e.currentTarget.currentTime) : undefined}
        onDurationChange={onDurationChange ? (e) => onDurationChange(e.currentTarget.duration) : undefined}
      />

      {/* Detection overlay (passed as children) */}
      {children}

      {/* Buffering indicator */}
      {isBuffering && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60">
          <div className="flex flex-col items-center gap-2 text-center">
            <WifiOff className="h-6 w-6 text-destructive" />
            <span className="text-xs text-destructive">{error}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                window.location.reload();
              }}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              Retry
            </Button>
          </div>
        </div>
      )}

      {/* Camera label (always visible) */}
      <div className="absolute left-2 top-2 flex items-center gap-1.5 rounded-md bg-black/70 px-2 py-1 backdrop-blur-sm group/label z-10">
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            camera.status === "online" ? "bg-success animate-pulse" : "bg-warning"
          )}
        />
        {isEditing ? (
          <input
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setCameraName(camera.id, editValue);
                setIsEditing(false);
              } else if (e.key === "Escape") {
                setEditValue(cameraName);
                setIsEditing(false);
              }
            }}
            onBlur={() => {
              setCameraName(camera.id, editValue);
              setIsEditing(false);
            }}
            className="bg-transparent border-b border-white text-white text-[11px] outline-none w-28 px-1 py-0.5 focus:border-primary"
            autoFocus
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          />
        ) : (
          <div className="flex items-center gap-1">
            <span className="text-[11px] font-medium text-white">{cameraName}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsEditing(true);
              }}
              className="text-white/60 hover:text-white ml-1.5 opacity-0 group-hover/label:opacity-100 transition-opacity p-0.5 rounded hover:bg-white/10"
              title="Edit name"
            >
              <Pencil className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>

      {/* Bandwidth indicator */}
      {bandwidth > 0 && (
        <div className="absolute right-2 top-2 flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 backdrop-blur-sm">
          <Wifi className="h-3 w-3 text-success" />
          <span className="text-[10px] text-white">
            {currentRes ? `${currentRes.height}p` : "Auto"}
          </span>
        </div>
      )}

      {/* Controls bar */}
      {showControls && (
        <div
          className={cn(
            "absolute bottom-0 left-0 right-0 flex items-center gap-1 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-8 transition-opacity duration-300",
            showControlsBar ? "opacity-100" : "opacity-0"
          )}
        >
          {/* Play/Pause */}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-white hover:bg-white/20 hover:text-white"
            onClick={(e) => {
              e.stopPropagation();
              togglePlay();
            }}
          >
            {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </Button>

          {/* Mute */}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-white hover:bg-white/20 hover:text-white"
            onClick={(e) => {
              e.stopPropagation();
              toggleMute();
            }}
          >
            {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
          </Button>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Bandwidth */}
          {bandwidth > 0 && (
            <span className="text-[10px] text-white/70">
              {(bandwidth / 1000).toFixed(1)} Mbps
            </span>
          )}

          {/* PiP */}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-white hover:bg-white/20 hover:text-white"
            onClick={(e) => {
              e.stopPropagation();
              togglePiP();
            }}
          >
            <PictureInPicture2 className="h-3.5 w-3.5" />
          </Button>

          {/* Fullscreen */}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-white hover:bg-white/20 hover:text-white"
            onClick={(e) => {
              e.stopPropagation();
              onFullscreenToggle?.();
            }}
          >
            {isFullscreen ? (
              <Minimize className="h-3.5 w-3.5" />
            ) : (
              <Maximize className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      )}
    </div>
  );
}

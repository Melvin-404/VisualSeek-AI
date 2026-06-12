"use client";

import React, { useRef, useState, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";
import type { TimelineEvent } from "./types";

interface TimelineProps {
  events: TimelineEvent[];
  currentTime: number;
  duration: number;
  onSeek: (time: number) => void;
  onRangeSelect?: (start: number, end: number) => void;
}

const EVENT_COLORS: Record<string, string> = {
  motion: "#3b82f6",
  object: "#22c55e",
  alert: "#ef4444",
  bookmark: "#eab308",
};

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function Timeline({
  events,
  currentTime,
  duration,
  onSeek,
  onRangeSelect,
}: TimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const [hoverX, setHoverX] = useState(0);
  const [rangeStart, setRangeStart] = useState<number | null>(null);

  const getTimeFromX = useCallback(
    (clientX: number): number => {
      const track = trackRef.current;
      if (!track || duration <= 0) return 0;
      const rect = track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      return ratio * duration;
    },
    [duration]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const time = getTimeFromX(e.clientX);
      if (e.shiftKey && onRangeSelect) {
        setRangeStart(time);
      } else {
        setIsDragging(true);
        onSeek(time);
      }
    },
    [getTimeFromX, onSeek, onRangeSelect]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const time = getTimeFromX(e.clientX);
      const track = trackRef.current;
      if (track) {
        const rect = track.getBoundingClientRect();
        setHoverX(e.clientX - rect.left);
      }
      setHoverTime(time);
      if (isDragging) {
        onSeek(time);
      }
    },
    [getTimeFromX, isDragging, onSeek]
  );

  const handleMouseUp = useCallback(
    (e: React.MouseEvent) => {
      if (rangeStart !== null && onRangeSelect) {
        const endTime = getTimeFromX(e.clientX);
        onRangeSelect(Math.min(rangeStart, endTime), Math.max(rangeStart, endTime));
        setRangeStart(null);
      }
      setIsDragging(false);
    },
    [rangeStart, onRangeSelect, getTimeFromX]
  );

  useEffect(() => {
    const handleGlobalMouseUp = () => {
      setIsDragging(false);
      setRangeStart(null);
    };
    window.addEventListener("mouseup", handleGlobalMouseUp);
    return () => window.removeEventListener("mouseup", handleGlobalMouseUp);
  }, []);

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="space-y-2">
      {/* Time labels */}
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>{formatTime(currentTime)}</span>
        <div className="flex items-center gap-3">
          {Object.entries(EVENT_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: color }} />
              <span className="capitalize">{type}</span>
            </div>
          ))}
        </div>
        <span>{formatTime(duration)}</span>
      </div>

      {/* Timeline track */}
      <div
        ref={trackRef}
        className="relative h-8 cursor-pointer rounded-lg bg-muted/50 border border-border"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => setHoverTime(null)}
        role="slider"
        aria-label="Video timeline"
        aria-valuenow={currentTime}
        aria-valuemin={0}
        aria-valuemax={duration}
      >
        {/* Event markers */}
        {events.map((event) => {
          const left = (event.startTime / duration) * 100;
          const width = ((event.endTime - event.startTime) / duration) * 100;
          return (
            <div
              key={event.id}
              className="absolute top-1 bottom-1 rounded-sm opacity-60 hover:opacity-100 transition-opacity"
              style={{
                left: `${left}%`,
                width: `${Math.max(width, 0.3)}%`,
                backgroundColor: EVENT_COLORS[event.type] || "#666",
              }}
              title={`${event.label} (${formatTime(event.startTime)})`}
            />
          );
        })}

        {/* Progress bar */}
        <div
          className="absolute top-0 bottom-0 left-0 rounded-l-lg bg-primary/20"
          style={{ width: `${progress}%` }}
        />

        {/* Playhead */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-primary shadow-lg shadow-primary/50 transition-all"
          style={{ left: `${progress}%` }}
        >
          <div className="absolute -left-1.5 -top-1 h-3 w-3 rounded-full border-2 border-primary bg-background" />
        </div>

        {/* Hover tooltip */}
        {hoverTime !== null && (
          <div
            className="absolute -top-8 -translate-x-1/2 rounded bg-card border border-border px-2 py-0.5 text-[10px] text-foreground shadow-lg pointer-events-none"
            style={{ left: `${hoverX}px` }}
          >
            {formatTime(hoverTime)}
          </div>
        )}

        {/* Range selection overlay */}
        {rangeStart !== null && hoverTime !== null && (
          <div
            className="absolute top-0 bottom-0 bg-primary/20 border border-primary/40"
            style={{
              left: `${(Math.min(rangeStart, hoverTime) / duration) * 100}%`,
              width: `${(Math.abs(hoverTime - rangeStart) / duration) * 100}%`,
            }}
          />
        )}
      </div>

      {/* Hint */}
      <p className="text-[10px] text-muted-foreground">
        Click to seek • Shift+drag to select range for export
      </p>
    </div>
  );
}

"use client";

import React, { useState } from "react";
import { Clock, Maximize2, Camera, Video, AlertTriangle, Info, MoveRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSession } from "next-auth/react";

interface Detection {
  label: string;
  bbox: [number, number, number, number];
  attributes?: Record<string, string>;
}

interface SearchResult {
  id: string;
  camera_id: string;
  timestamp_ms: number;
  frame_number: number;
  segment_id: string;
  object_classes: string[];
  score: number;
  raw_labels: {
    detections: Detection[];
    description: string;
    video_path: string;
  };
  dominant_colour?: string;
  vehicle_type?: string;
  upper_colour?: string;
  lower_colour?: string;
  carried_items?: string[];
  gender_estimate?: string;
  action_status?: string;
  action_verified?: boolean;
  event_start_ms?: number;
  event_end_ms?: number;
}

interface ResultCardProps {
  result: SearchResult;
  onAnalyse: (result: SearchResult) => void;
  activeQuery?: string;
}

const CAMERA_NAMES: Record<string, string> = {
  "cam-lobby": "Lobby Entrance Camera",
  "cam-parking": "Parking Lot West Feed",
  "cam-roadway": "Roadway Intersection North",
  "cam-dock": "Dock Loading Bay Area",
};

export default function ResultCard({ result, onAnalyse, activeQuery = "" }: ResultCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [imgError, setImgError] = useState(false);
  const { data: session } = useSession();

  const token = session?.accessToken || "mock-token";
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
  const cropUrl = `${apiUrl.replace(/\/$/, "")}/api/v1/detections/${result.id}/crop?token=${token}`;

  const formatVideoTime = (ms: number) => {
    const totalSecs = Math.floor(ms / 1000);
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const isEventResult = result.event_start_ms !== undefined && result.event_end_ms !== undefined;
  const isActionQuery = !!result.action_status;

  const cameraLabel = CAMERA_NAMES[result.camera_id] || result.camera_id;

  // Derive a clean "object" label from detections
  const primaryDetection = result.raw_labels.detections?.[0];
  const detectedObject = primaryDetection
    ? [primaryDetection.attributes?.color, primaryDetection.label].filter(Boolean).join(" ")
    : result.object_classes?.[0] || "Object";

  // Extract action from result if present
  const actionLabel = primaryDetection?.attributes?.action;

  /**
   * Returns a single short sentence explaining this match.
   * Uses only real data — no invented information.
   */
  const buildWhyExplanation = () => {
    // Action status from temporal analysis takes priority
    if (result.action_status) {
      return result.action_status;
    }
    // Motion event: vehicle was tracked across frames
    if (isEventResult) {
      return `${detectedObject.charAt(0).toUpperCase() + detectedObject.slice(1)} detected moving across frames from ${formatVideoTime(result.event_start_ms!)} to ${formatVideoTime(result.event_end_ms!)}.`;
    }
    // Static object: semantic match
    return result.raw_labels.description;
  };

  const whyExplanation = buildWhyExplanation();

  return (
    <div
      className="rounded-xl overflow-hidden border border-border hover:border-primary/50 transition-all duration-200 group flex flex-col bg-card/40 backdrop-blur-sm shadow-sm hover:shadow-primary/5"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* ─── VIDEO / FRAME ─── */}
      <div
        className="aspect-video w-full bg-black relative cursor-pointer overflow-hidden"
        onClick={() => onAnalyse(result)}
      >
        {/* Image (default) → Video (on hover) */}
        {!isHovered && !imgError ? (
          <img
            src={cropUrl}
            alt={result.raw_labels.description}
            className="w-full h-full object-cover transition-all duration-350"
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <video
            src={result.raw_labels.video_path}
            className="w-full h-full object-cover pointer-events-none"
            muted
            playsInline
            loop
            ref={(el) => {
              if (el) {
                if (isHovered) {
                  const seekTime = result.event_start_ms !== undefined
                    ? result.event_start_ms / 1000.0
                    : result.timestamp_ms / 1000.0;
                  el.currentTime = seekTime;
                  el.play().catch(() => {});
                } else {
                  el.pause();
                }
              }
            }}
          />
        )}

        {/* Detection bounding boxes overlay */}
        {result.raw_labels.detections?.map((det, detIdx) => {
          const [xmin, ymin, xmax, ymax] = det.bbox;
          return (
            <div
              key={detIdx}
              style={{
                position: "absolute",
                left: `${xmin * 100}%`,
                top: `${ymin * 100}%`,
                width: `${(xmax - xmin) * 100}%`,
                height: `${(ymax - ymin) * 100}%`,
              }}
              className="border-2 border-primary/90 pointer-events-none rounded-sm shadow-[0_0_6px_rgba(56,189,248,0.4)] z-10"
            />
          );
        })}

        {/* Camera label — top left */}
        <div className="absolute top-2 left-2 z-10">
          <Badge className="bg-black/80 backdrop-blur-sm text-[10px] font-bold border-border/50 text-white px-2 py-0.5 flex items-center gap-1">
            <Camera className="h-2.5 w-2.5" />
            {cameraLabel}
          </Badge>
        </div>

        {/* Relevance score — top right */}
        <div className="absolute top-2 right-2 z-10">
          <Badge className="bg-primary/90 text-primary-foreground text-[10px] font-bold px-2 py-0.5 shadow-md">
            Score: {(result.score * 100).toFixed(0)}
          </Badge>
        </div>

        {/* Timestamp / event window — bottom left */}
        <div className="absolute bottom-2 left-2 bg-black/80 backdrop-blur-sm px-2 py-0.5 rounded text-[10px] font-bold text-white z-10 flex items-center gap-1">
          <Clock className="h-2.5 w-2.5 text-primary" />
          {isEventResult ? (
            <span>{formatVideoTime(result.event_start_ms!)} – {formatVideoTime(result.event_end_ms!)}</span>
          ) : (
            <span>{formatVideoTime(result.timestamp_ms)}</span>
          )}
        </div>

        {/* Hover play overlay */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-all z-20">
          <div className="h-10 w-10 bg-primary rounded-full flex items-center justify-center text-primary-foreground shadow-lg transform scale-90 group-hover:scale-100 transition-all">
            <Video className="h-4 w-4" />
          </div>
        </div>
      </div>

      {/* ─── METADATA GRID ─── */}
      <div className="p-4 border-b border-border/50 grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
        <div className="flex flex-col gap-0.5">
          <span className="text-muted-foreground uppercase tracking-wider text-[9px] font-bold">Camera</span>
          <span className="text-foreground font-semibold">{cameraLabel}</span>
        </div>

        <div className="flex flex-col gap-0.5">
          <span className="text-muted-foreground uppercase tracking-wider text-[9px] font-bold">
            {isEventResult ? "Time Window" : "Timestamp"}
          </span>
          <span className="text-foreground font-semibold font-mono">
            {isEventResult
              ? `${formatVideoTime(result.event_start_ms!)} – ${formatVideoTime(result.event_end_ms!)}`
              : formatVideoTime(result.timestamp_ms)}
          </span>
        </div>

        <div className="flex flex-col gap-0.5">
          <span className="text-muted-foreground uppercase tracking-wider text-[9px] font-bold">Object</span>
          <span className="text-foreground font-semibold capitalize">
            {detectedObject || "—"}
          </span>
        </div>

        <div className="flex flex-col gap-0.5">
          <span className="text-muted-foreground uppercase tracking-wider text-[9px] font-bold">Relevance</span>
          <span className="text-primary font-bold">{(result.score * 100).toFixed(0)} / 100</span>
        </div>

        {(actionLabel || isActionQuery) && (
          <div className="flex flex-col gap-0.5 col-span-2">
            <span className="text-muted-foreground uppercase tracking-wider text-[9px] font-bold">Action</span>
            <span className="text-foreground font-semibold capitalize">
              {actionLabel || "Detected (see explanation below)"}
            </span>
          </div>
        )}
      </div>

      {/* ─── WHY THIS MATCH? ─── */}
      <div className="px-4 py-3 flex-grow">
        <div className={`rounded-lg p-3 text-xs leading-relaxed ${
          result.action_status
            ? "bg-amber-500/5 border border-amber-500/25"
            : "bg-primary/5 border border-primary/15"
        }`}>
          <div className="flex items-center gap-1.5 mb-1.5">
            {result.action_status ? (
              <AlertTriangle className="h-3 w-3 text-amber-400 shrink-0" />
            ) : (
              <Info className="h-3 w-3 text-primary shrink-0" />
            )}
            <span className={`uppercase tracking-widest text-[9px] font-bold ${
              result.action_status ? "text-amber-400" : "text-primary"
            }`}>
              Why this match?
            </span>
          </div>
          <p className={`leading-relaxed ${
            result.action_status ? "text-amber-200/80" : "text-foreground/80"
          }`}>
            {whyExplanation}
          </p>
        </div>
      </div>

      {/* ─── ACTION BUTTONS ─── */}
      <div className="px-4 pb-4 flex gap-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          className="flex-1 h-8 text-xs text-foreground cursor-pointer border-border hover:border-primary/40 hover:text-primary transition-all"
          onClick={() => onAnalyse(result)}
        >
          <MoveRight className="h-3 w-3 mr-1.5" />
          View Context
        </Button>
        <Button
          size="sm"
          className="flex-1 h-8 text-xs cursor-pointer bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 hover:border-primary/60 shadow-none transition-all"
          onClick={() => onAnalyse(result)}
        >
          <Maximize2 className="h-3 w-3 mr-1.5" />
          Analyse Frame
        </Button>
      </div>
    </div>
  );
}

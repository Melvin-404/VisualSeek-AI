"use client";

import React, { useState, useRef, useEffect } from "react";
import { Camera, X, Play, Pause, VolumeX, Volume2, Target, Share2, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import ChatInterface from "@/components/features/search/ChatInterface";

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
  action_status?: string;
  action_verified?: boolean;
  event_start_ms?: number;
  event_end_ms?: number;
}

const CAMERA_NAMES: Record<string, string> = {
  "cam-lobby": "Lobby Entrance Camera",
  "cam-parking": "Parking Lot West Feed",
  "cam-roadway": "Roadway Intersection North",
  "cam-dock": "Dock Loading Bay Area",
};

export default function SearchPage() {
  const [activeResult, setActiveResult] = useState<SearchResult | null>(null);
  const [videoCurrentTime, setVideoCurrentTime] = useState(0);
  const [modalIsMuted, setModalIsMuted] = useState(true);
  const [modalIsPlaying, setModalIsPlaying] = useState(true);
  const modalVideoRef = useRef<HTMLVideoElement | null>(null);

  // Sync video timeline seek in modal
  useEffect(() => {
    if (activeResult && modalVideoRef.current) {
      const seekTime = activeResult.event_start_ms !== undefined 
        ? activeResult.event_start_ms / 1000.0 
        : activeResult.timestamp_ms / 1000.0;
      modalVideoRef.current.currentTime = seekTime;
      if (modalIsPlaying) {

        modalVideoRef.current.play().catch(() => {});
      }
    }
  }, [activeResult, modalIsPlaying]);

  const handleTimeUpdate = () => {
    if (modalVideoRef.current) {
      setVideoCurrentTime(modalVideoRef.current.currentTime);
    }
  };

  const formatVideoTime = (ms: number) => {
    const totalSecs = Math.floor(ms / 1000);
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const renderModalBoundingBoxes = () => {
    if (!activeResult) return null;
    const detections = activeResult.raw_labels.detections || [];
    
    // Check if the current playback time is within 1.5 seconds of the matched frame
    const targetSec = activeResult.timestamp_ms / 1000.0;
    const isClose = Math.abs(videoCurrentTime - targetSec) < 1.5;
    if (!isClose) return null;

    return detections.map((det, idx) => {
      const [xmin, ymin, xmax, ymax] = det.bbox;
      const borderColors: Record<string, string> = {
        person: "#10b981", // emerald
        car: "#3b82f6", // blue
        suv: "#3b82f6",
        bus: "#eab308", // yellow
        motorcycle: "#06b6d4", // cyan
        truck: "#f97316", // orange
        backpack: "#a855f7", // purple
        laptop: "#ec4899", // pink
        forklift: "#76b900", // nvidia primary
      };
      
      const color = borderColors[det.label.toLowerCase()] || "#76b900";

      return (
        <div
          key={idx}
          style={{
            position: "absolute",
            left: `${xmin * 100}%`,
            top: `${ymin * 100}%`,
            width: `${(xmax - xmin) * 100}%`,
            height: `${(ymax - ymin) * 100}%`,
            borderColor: color,
          }}
          className="border-2 border-dashed pointer-events-none rounded shadow-[0_0_8px_rgba(118,185,0,0.4)]"
        >
          <span
            style={{ backgroundColor: color }}
            className="absolute -top-5 left-0 px-1 text-[9px] font-bold text-black rounded uppercase"
          >
            {det.label} {det.attributes?.color || det.attributes?.clothing || ""}
          </span>
        </div>
      );
    });
  };

  return (
    <div className="space-y-6">
      {/* Visual Search Chat Interface Dashboard */}
      <ChatInterface onAnalyseFrame={setActiveResult} />

      {/* Modal Dialog for Analyse Frame Bounding Box Seek Playback */}
      {activeResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
          <div className="bg-card border border-border rounded-2xl overflow-hidden max-w-4xl w-full shadow-2xl relative flex flex-col max-h-[90vh]">
            
            {/* Modal Header */}
            <div className="p-4 border-b border-border flex justify-between items-center bg-card-foreground/[0.02]">
              <div className="flex items-center gap-2">
                <Camera className="h-4 w-4 text-primary" />
                <span className="text-sm font-bold text-foreground">
                  Frame Analyzer - {CAMERA_NAMES[activeResult.camera_id] || activeResult.camera_id}
                </span>
              </div>
              <button
                className="text-muted-foreground hover:text-foreground cursor-pointer p-1 rounded-lg hover:bg-muted"
                onClick={() => setActiveResult(null)}
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Video Canvas Container with Bounding Boxes */}
            <div className="relative aspect-video w-full bg-black flex-1 min-h-[300px]">
              <video
                ref={modalVideoRef}
                src={activeResult.raw_labels.video_path}
                className="h-full w-full object-contain"
                muted={modalIsMuted}
                autoPlay
                loop
                onTimeUpdate={handleTimeUpdate}
                onClick={() => setModalIsPlaying(!modalIsPlaying)}
              />

              {/* Precise Absolute BBox Render Layer */}
              {renderModalBoundingBoxes()}

              {/* Video control status overlay (Play indicator) */}
              {!modalIsPlaying && (
                <div
                  className="absolute inset-0 flex items-center justify-center bg-black/30 cursor-pointer"
                  onClick={() => setModalIsPlaying(true)}
                >
                  <div className="h-14 w-14 bg-primary rounded-full flex items-center justify-center text-primary-foreground shadow-lg">
                    <Play className="h-6 w-6 fill-current ml-1" />
                  </div>
                </div>
              )}
            </div>

            {/* Seeking Controls bar */}
            <div className="p-4 border-t border-border bg-card space-y-4">
              {/* Timeline seek bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-[10px] text-muted-foreground font-bold">
                  {activeResult.event_start_ms !== undefined && activeResult.event_end_ms !== undefined ? (
                    <span>Match event: {formatVideoTime(activeResult.event_start_ms)} - {formatVideoTime(activeResult.event_end_ms)}</span>
                  ) : (
                    <span>Match point: {formatVideoTime(activeResult.timestamp_ms)}</span>
                  )}
                  <span>

                    Playback:{" "}
                    {modalVideoRef.current ? formatVideoTime(modalVideoRef.current.currentTime * 1000) : "00:00"}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max={modalVideoRef.current?.duration || 60}
                  step="0.05"
                  className="w-full accent-primary bg-border h-1 rounded cursor-pointer focus:outline-none"
                  value={videoCurrentTime}
                  onChange={(e) => {
                    const time = parseFloat(e.target.value);
                    setVideoCurrentTime(time);
                    if (modalVideoRef.current) {
                      modalVideoRef.current.currentTime = time;
                    }
                  }}
                />
              </div>

              {/* Buttons controls */}
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8 text-foreground cursor-pointer"
                    onClick={() => {
                      if (modalVideoRef.current) {
                        if (modalIsPlaying) {
                          modalVideoRef.current.pause();
                        } else {
                          modalVideoRef.current.play().catch(() => {});
                        }
                        setModalIsPlaying(!modalIsPlaying);
                      }
                    }}
                  >
                    {modalIsPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5 fill-current ml-0.5" />}
                  </Button>

                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8 text-foreground cursor-pointer"
                    onClick={() => setModalIsMuted(!modalIsMuted)}
                  >
                    {modalIsMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
                  </Button>

                  {/* Reset to match marker */}
                  <Button
                    variant="secondary"
                    size="sm"
                    className="text-xs h-8 text-foreground cursor-pointer"
                    onClick={() => {
                      if (modalVideoRef.current) {
                        const seekTime = activeResult.event_start_ms !== undefined 
                          ? activeResult.event_start_ms / 1000.0 
                          : activeResult.timestamp_ms / 1000.0;
                        modalVideoRef.current.currentTime = seekTime;
                      }
                    }}
                  >
                    Seek to Match
                  </Button>
                </div>

                {/* Right side sharing details */}
                <div className="flex items-center gap-2">
                  <span className="text-[10px] bg-muted px-2 py-1 rounded border border-border text-muted-foreground flex items-center gap-1 font-bold">
                    <Target className="h-3 w-3 text-primary" />
                    RELEVANCE SCORE: {(activeResult.score * 100).toFixed(0)}
                  </span>
                  <Button variant="outline" size="sm" className="h-8 text-foreground cursor-pointer">
                    <Share2 className="h-3.5 w-3.5 mr-1" />
                    Share
                  </Button>
                </div>
              </div>

              {/* Event Description Panel */}
              <div className="bg-muted border border-border rounded-xl p-3 text-xs leading-relaxed text-foreground">
                <div className="font-bold text-muted-foreground uppercase text-[9px] mb-1 tracking-wider">
                  Semantic description matches
                </div>
                &ldquo;{activeResult.raw_labels.description}&rdquo;
                <div className="mt-2 text-[10px] text-muted-foreground flex items-center gap-3">
                  <span>Frame: #{activeResult.frame_number}</span>
                  <span>Segment: {activeResult.segment_id}</span>
                  <span>Camera: {activeResult.camera_id}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

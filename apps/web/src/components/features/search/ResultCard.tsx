"use client";

import React, { useState } from "react";
import { Play, Clock, Target, Maximize2, Tag, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

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

  // Formats milliseconds into timeline format (mm:ss)
  const formatVideoTime = (ms: number) => {
    const totalSecs = Math.floor(ms / 1000);
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  // Highlights matches inside text based on the active query terms (visual result explanation)
  const renderMatchExplanation = () => {
    const desc = result.raw_labels.description;
    const queryTerms = activeQuery
      .toLowerCase()
      .split(" ")
      .filter((w) => w.length > 2);

    if (queryTerms.length === 0) {
      return <p className="text-xs text-foreground font-medium">{desc}</p>;
    }

    // Replace terms with colored spans
    const escapedTerms = queryTerms.map(t => t.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&'));
    const regex = new RegExp(`\\b(${escapedTerms.join("|")})\\b`, "gi");
    const parts = desc.split(regex);

    return (
      <p className="text-xs text-foreground font-medium leading-relaxed">
        {parts.map((part, i) => {
          const isMatch = queryTerms.includes(part.toLowerCase());
          return isMatch ? (
            <span
              key={i}
              className="bg-primary/20 text-primary border-b border-primary/45 px-1 py-0.5 rounded font-bold"
            >
              {part}
            </span>
          ) : (
            <span key={i}>{part}</span>
          );
        })}
      </p>
    );
  };

  return (
    <div
      className="glass rounded-xl overflow-hidden shadow hover:shadow-primary/5 border border-border hover:border-primary/40 transition-all duration-200 group flex flex-col h-full"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Bounded Video Preview Frame */}
      <div
        className="aspect-video w-full bg-black relative cursor-pointer overflow-hidden"
        onClick={() => onAnalyse(result)}
      >
        {/* Video Player */}
        <video
          src={result.raw_labels.video_path}
          className="w-full h-full object-cover pointer-events-none"
          muted
          playsInline
          loop
          ref={(el) => {
            if (el) {
              if (isHovered) {
                el.currentTime = result.timestamp_ms / 1000.0;
                el.play().catch(() => {});
              } else {
                el.pause();
              }
            }
          }}
        />

        {/* Frame detection bbox outline static overlay */}
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
              className="border border-primary/70 pointer-events-none rounded-sm shadow-[0_0_4px_rgba(118,185,0,0.3)]"
            />
          );
        })}

        {/* Floating badging */}
        <div className="absolute top-2 left-2 flex gap-1.5 z-10">
          <Badge className="bg-black/80 backdrop-blur-sm text-[10px] font-bold border-border text-white px-2 py-0.5">
            {CAMERA_NAMES[result.camera_id] || result.camera_id}
          </Badge>
        </div>

        <div className="absolute top-2 right-2 flex gap-1.5 z-10">
          <Badge className="bg-primary/95 text-primary-foreground text-[10px] font-bold px-2 py-0.5 shadow-md">
            {(result.score * 100).toFixed(0)}% Match
          </Badge>
        </div>

        {/* Hover play prompt */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-all z-20">
          <div className="h-10 w-10 bg-primary rounded-full flex items-center justify-center text-primary-foreground shadow-lg transform scale-90 group-hover:scale-100 transition-all">
            <Play className="h-4 w-4 fill-current ml-0.5" />
          </div>
        </div>

        {/* Bounding box timestamp indicator */}
        <div className="absolute bottom-2 left-2 bg-black/75 px-1.5 py-0.5 rounded text-[10px] font-bold text-white z-10 flex items-center gap-1 backdrop-blur-sm">
          <Clock className="h-2.5 w-2.5 text-primary" />
          {formatVideoTime(result.timestamp_ms)}
        </div>
      </div>

      {/* Metadata detail block */}
      <div className="p-4 flex-grow flex flex-col justify-between">
        <div className="space-y-3">
          {/* Visual Match Explanation Highlighted text */}
          {renderMatchExplanation()}

          {/* Inline Badge Explaining matches */}
          <div className="flex flex-wrap gap-1.5 pt-1">
            <Badge variant="outline" className="text-[9px] border-primary/30 text-primary bg-primary/5 px-2 py-0">
              <CheckCircle2 className="h-2.5 w-2.5 mr-1 text-primary" />
              Satisfies Class: {result.object_classes.join(", ")}
            </Badge>
            {result.raw_labels.detections?.[0]?.attributes && (
              <Badge variant="outline" className="text-[9px] border-border text-muted-foreground px-2 py-0">
                Attributes: {Object.values(result.raw_labels.detections[0].attributes).join(", ")}
              </Badge>
            )}
          </div>
        </div>

        <div className="flex justify-between items-center pt-2 border-t border-border mt-4">
          <span className="text-[10px] text-muted-foreground flex items-center gap-1">
            <Tag className="h-2.5 w-2.5 text-primary" />
            Segment: {result.segment_id}
          </span>
          
          <button
            className="text-[10px] text-primary font-bold hover:underline cursor-pointer uppercase flex items-center gap-0.5"
            onClick={() => onAnalyse(result)}
          >
            Analyse Frame
            <Maximize2 className="h-2.5 w-2.5 ml-0.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

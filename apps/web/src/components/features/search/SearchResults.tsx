"use client";

import React, { useState } from "react";
import { SlidersHorizontal, Download, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { motion, Variants } from "framer-motion";
import ResultCard from "./ResultCard";

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

interface SearchResultsProps {
  results: SearchResult[];
  activeQuery: string;
  onAnalyse: (result: SearchResult) => void;
}

const listContainerVariants: Variants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.06,
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { 
    opacity: 1, 
    y: 0, 
    transition: { 
      type: "spring", 
      stiffness: 120, 
      damping: 14 
    } 
  },
};

export default function SearchResults({ results, activeQuery, onAnalyse }: SearchResultsProps) {
  const [cameraFilter, setCameraFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"score" | "time">("score");

  // Filters & sorts combined search matches
  const processedResults = results
    .filter((r) => cameraFilter === "all" || r.camera_id === cameraFilter)
    .sort((a, b) => {
      if (sortBy === "time") {
        return a.timestamp_ms - b.timestamp_ms;
      }
      return b.score - a.score;
    });

  // Handles export to CSV or JSON formats
  const handleExport = (format: "json" | "csv") => {
    if (processedResults.length === 0) return;

    let dataStr = "";
    let mimeType = "";
    let filename = "";

    const querySlug = activeQuery ? activeQuery.replace(/\s+/g, "_") : "all_results";

    if (format === "json") {
      dataStr = JSON.stringify(processedResults, null, 2);
      mimeType = "application/json";
      filename = `vision_query_export_${querySlug}.json`;
    } else {
      const headers = ["ID", "Camera ID", "Timestamp (ms)", "Frame No", "Relevance Score", "Description"];
      const rows = processedResults.map((r) => [
        r.id,
        r.camera_id,
        r.timestamp_ms,
        r.frame_number,
        (r.score * 100).toFixed(1) + "%",
        r.raw_labels.description.replace(/"/g, '""'),
      ]);
      dataStr = [headers.join(","), ...rows.map((row) => row.map((val) => `"${val}"`).join(","))].join("\n");
      mimeType = "text/csv";
      filename = `vision_query_export_${querySlug}.csv`;
    }

    const blob = new Blob([dataStr], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* Filtering Options Header */}
      {results.length > 0 && (
        <div className="glass rounded-xl px-4 py-3 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border border-border">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            <span className="text-xs font-bold text-foreground">
              Found {processedResults.length} matches in video index
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs">
            {/* Camera dropdown filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground">Camera:</span>
              <select
                className="bg-background border border-border rounded-md px-2 py-1 text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
                value={cameraFilter}
                onChange={(e) => setCameraFilter(e.target.value)}
              >
                <option value="all">All Feeds</option>
                <option value="cam-lobby">Lobby entrance</option>
                <option value="cam-parking">Parking lot</option>
                <option value="cam-roadway">Roadway</option>
                <option value="cam-dock">Dock bay</option>
              </select>
            </div>

            {/* Sorting dropdown */}
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground">Sort:</span>
              <select
                className="bg-background border border-border rounded-md px-2 py-1 text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "score" | "time")}
              >
                <option value="score">Relevance Score</option>
                <option value="time">Timestamp</option>
              </select>
            </div>

            {/* Exporting actions */}
            <div className="flex items-center gap-1.5 border-l border-border pl-4">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-muted-foreground hover:text-foreground text-[11px] cursor-pointer"
                onClick={() => handleExport("csv")}
              >
                <Download className="h-3 w-3 mr-1" />
                CSV
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-muted-foreground hover:text-foreground text-[11px] cursor-pointer"
                onClick={() => handleExport("json")}
              >
                <Download className="h-3 w-3 mr-1" />
                JSON
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Grid displays */}
      {processedResults.length > 0 ? (
        <motion.div
          variants={listContainerVariants}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
        >
          {processedResults.map((result) => (
            <motion.div key={result.id} variants={itemVariants}>
              <ResultCard
                result={result}
                onAnalyse={onAnalyse}
                activeQuery={activeQuery}
              />
            </motion.div>
          ))}
        </motion.div>
      ) : (
        <div className="glass rounded-xl p-10 text-center border-dashed border-border flex flex-col items-center justify-center gap-2">
          <EyeOff className="h-8 w-8 text-muted-foreground" />
          <h3 className="text-sm font-bold text-foreground mt-2">No matching frames</h3>
          <p className="text-xs text-muted-foreground max-w-sm mx-auto">
            Try adjusting your query scope or selecting a different camera filter.
          </p>
        </div>
      )}
    </div>
  );
}

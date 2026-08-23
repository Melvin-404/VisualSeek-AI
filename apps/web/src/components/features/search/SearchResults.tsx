"use client";

import React, { useState } from "react";
import { SlidersHorizontal, Download, EyeOff, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  action_status?: string;
  action_verified?: boolean;
  event_start_ms?: number;
  event_end_ms?: number;
}

interface IntentData {
  intent_type?: string;
  object_class?: string;
  color?: string;
  action?: string;
  is_action_query?: boolean;
  camera_ids?: string[];
  rewritten_query?: string;
}

interface SearchResultsProps {
  results: SearchResult[];
  activeQuery: string;
  intent?: IntentData | null;
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
      damping: 14,
    },
  },
};

function buildSummaryText(
  results: SearchResult[],
  intent: IntentData | null | undefined,
  query: string
): string {
  return "";
}

export default function SearchResults({ results, activeQuery, intent, onAnalyse }: SearchResultsProps) {
  const [cameraFilter, setCameraFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"score" | "time">("score");

  const processedResults = results
    .filter((r) => cameraFilter === "all" || r.camera_id === cameraFilter)
    .sort((a, b) => {
      if (sortBy === "time") return a.timestamp_ms - b.timestamp_ms;
      return b.score - a.score;
    });

  const handleExport = (format: "json" | "csv") => {
    if (processedResults.length === 0) return;
    let dataStr = "";
    let mimeType = "";
    let filename = "";
    const querySlug = activeQuery ? activeQuery.replace(/\s+/g, "_") : "all_results";

    if (format === "json") {
      dataStr = JSON.stringify(processedResults, null, 2);
      mimeType = "application/json";
      filename = `visualseek_export_${querySlug}.json`;
    } else {
      const headers = ["ID", "Camera ID", "Timestamp (ms)", "Frame No", "Relevance Score", "Description"];
      const rows = processedResults.map((r) => [
        r.id,
        r.camera_id,
        r.timestamp_ms,
        r.frame_number,
        (r.score * 100).toFixed(1),
        r.raw_labels.description.replace(/"/g, '""'),
      ]);
      dataStr = [headers.join(","), ...rows.map((row) => row.map((val) => `"${val}"`).join(","))].join("\n");
      mimeType = "text/csv";
      filename = `visualseek_export_${querySlug}.csv`;
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

  // Compact label: "Found N moments for: [query snippet]"
  const querySnippet = activeQuery.length > 50 ? activeQuery.slice(0, 50) + "…" : activeQuery;
  const resultLabel = results.length === 0
    ? "No matching moments found"
    : `Found ${results.length} relevant moment${results.length !== 1 ? "s" : ""} for: ${querySnippet}`;

  return (
    <div className="space-y-4">

      {/* ─── COMPACT RESULT HEADER ─── */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-1">
        <div className="flex items-center gap-2 min-w-0">
          <Search className="h-3.5 w-3.5 text-primary shrink-0" />
          <span className="text-sm font-semibold text-foreground truncate">{resultLabel}</span>
        </div>
        {/* Attribute pills — only rendered if extracted */}
        {(intent?.object_class || intent?.action) && (
          <div className="flex flex-wrap gap-1.5 sm:border-l sm:border-border/60 sm:pl-4">
            {intent.object_class && (
              <span className="inline-flex items-center text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-primary/10 border border-primary/25 text-primary">
                {[intent.color, intent.object_class].filter(Boolean).join(" ")}
              </span>
            )}
            {intent.action && (
              <span className="inline-flex items-center text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/25 text-amber-400">
                {intent.action}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ─── FILTER BAR ─── */}
      {results.length > 0 && (
        <div className="rounded-xl px-4 py-3 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border border-border bg-card/30">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-bold text-foreground">
              {processedResults.length} of {results.length} moment{results.length !== 1 ? "s" : ""} shown
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground">Camera:</span>
              <select
                className="bg-background border border-border rounded-md px-2 py-1 text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
                value={cameraFilter}
                onChange={(e) => setCameraFilter(e.target.value)}
              >
                <option value="all">All Feeds</option>
                <option value="cam-lobby">Lobby Entrance</option>
                <option value="cam-parking">Parking Lot</option>
                <option value="cam-roadway">Roadway</option>
                <option value="cam-dock">Dock Bay</option>
              </select>
            </div>

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

            <div className="flex items-center gap-1.5 border-l border-border pl-4">
              <Button variant="ghost" size="sm" className="h-7 px-2 text-muted-foreground hover:text-foreground text-[11px] cursor-pointer" onClick={() => handleExport("csv")}>
                <Download className="h-3 w-3 mr-1" />CSV
              </Button>
              <Button variant="ghost" size="sm" className="h-7 px-2 text-muted-foreground hover:text-foreground text-[11px] cursor-pointer" onClick={() => handleExport("json")}>
                <Download className="h-3 w-3 mr-1" />JSON
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ─── RESULT GRID ─── */}
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
        <div className="rounded-xl p-10 text-center border border-dashed border-border flex flex-col items-center justify-center gap-3 bg-card/20">
          <EyeOff className="h-8 w-8 text-muted-foreground" />
          <div>
            <h3 className="text-sm font-bold text-foreground">No matching moments</h3>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto mt-1">
              {cameraFilter !== "all"
                ? "Try changing the camera filter or selecting All Feeds."
                : "No results matched your query. Try adjusting the search terms."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

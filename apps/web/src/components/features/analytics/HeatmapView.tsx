"use client";

import React, { useEffect, useState } from "react";
import { Info } from "lucide-react";

interface HeatmapHour {
  hour: number;
  lobby: number;
  parking_lot_a: number;
  parking_lot_b: number;
  loading_dock: number;
  entrance: number;
}

const ZONES = [
  { key: "lobby", name: "Lobby Area" },
  { key: "entrance", name: "Main Entrance" },
  { key: "parking_lot_a", name: "Parking Lot A" },
  { key: "parking_lot_b", name: "Parking Lot B" },
  { key: "loading_dock", name: "Loading Dock" }
];

const generateMockHeatmapData = (): HeatmapHour[] => {
  const data: HeatmapHour[] = [];
  for (let h = 0; h < 24; h++) {
    const isPeak = (h >= 8 && h <= 10) || (h >= 12 && h <= 14) || (h >= 17 && h <= 19);
    const baseMultiplier = isPeak ? 3 : 1;
    data.push({
      hour: h,
      lobby: Math.floor((h % 3 === 0 ? 5 : 2) * baseMultiplier + (h % 5)),
      parking_lot_a: Math.floor((h % 2 === 0 ? 8 : 4) * baseMultiplier + (h % 4)),
      parking_lot_b: Math.floor((h % 4 === 0 ? 6 : 1) * baseMultiplier + (h % 3)),
      loading_dock: Math.floor((h % 5 === 0 ? 4 : 0) * baseMultiplier + (h % 2)),
      entrance: Math.floor((h % 3 === 0 ? 7 : 3) * baseMultiplier + (h % 6)),
    });
  }
  return data;
};

export function HeatmapView() {
  const [data, setData] = useState<HeatmapHour[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredCell, setHoveredCell] = useState<{
    zone: string;
    hour: number;
    value: number;
  } | null>(null);

  useEffect(() => {
    const fetchHeatmap = async () => {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!apiUrl) {
        setData(generateMockHeatmapData());
        setLoading(false);
        return;
      }
      try {
        const token = "mock-token";
        const res = await fetch(`${apiUrl}/api/v1/analytics/heatmap`, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "X-Tenant-ID": "22222222-2222-2222-2222-222222222222"
          }
        });
        if (res.ok) {
          const heatmapData = await res.json();
          setData(heatmapData);
        } else {
          setData(generateMockHeatmapData());
        }
      } catch (err) {
        console.error("Failed to fetch heatmap data", err);
        setData(generateMockHeatmapData());
      } finally {
        setLoading(false);
      }
    };

    fetchHeatmap();
  }, []);

  if (loading || data.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 animate-pulse">
        <div className="h-6 w-48 rounded bg-muted" />
        <div className="mt-6 h-64 rounded bg-muted" />
      </div>
    );
  }

  // Find max value in data to scale colors
  let maxValue = 1;
  data.forEach((hourData) => {
    ZONES.forEach((zone) => {
      const val = (hourData as any)[zone.key] || 0;
      if (val > maxValue) {
        maxValue = val;
      }
    });
  });

  const getColorClass = (value: number) => {
    if (value === 0) return "bg-muted/10";
    const ratio = value / maxValue;
    if (ratio < 0.2) return "bg-primary/20 text-foreground";
    if (ratio < 0.4) return "bg-primary/40 text-foreground";
    if (ratio < 0.6) return "bg-primary/60 text-primary-foreground";
    if (ratio < 0.8) return "bg-primary/85 text-primary-foreground";
    return "bg-primary text-primary-foreground shadow-sm shadow-primary/20";
  };

  return (
    <div 
      className="rounded-xl border border-border/80 bg-card/45 glass p-6 select-none relative"
      data-cursor="explore"
    >
      {/* HUD Tech Corner Elements */}
      <div className="absolute top-1.5 left-1.5 w-1.5 h-1.5 border-t border-l border-muted-foreground/30" />
      <div className="absolute top-1.5 right-1.5 w-1.5 h-1.5 border-t border-r border-muted-foreground/30" />
      <div className="absolute bottom-1.5 left-1.5 w-1.5 h-1.5 border-b border-l border-muted-foreground/30" />
      <div className="absolute bottom-1.5 right-1.5 w-1.5 h-1.5 border-b border-r border-muted-foreground/30" />

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-border/40 pb-4 mb-6">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
            Foot Traffic Heatmap
            <span className="group relative cursor-pointer">
              <Info className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              <span className="absolute bottom-6 left-1/2 -translate-x-1/2 scale-0 rounded-md bg-popover p-2 text-[10px] text-popover-foreground w-48 transition-all duration-200 group-hover:scale-100 border border-border z-10">
                Displays real-time and historical foot traffic density based on person detections.
              </span>
            </span>
          </h3>
          <p className="text-[10px] font-medium text-muted-foreground/80">
            Density distribution per zone per hour of the day
          </p>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
          <span>Less</span>
          <div className="h-3 w-3 rounded-sm bg-muted/10 border border-border/50" />
          <div className="h-3 w-3 rounded-sm bg-primary/20 border border-primary/10" />
          <div className="h-3 w-3 rounded-sm bg-primary/50 border border-primary/25" />
          <div className="h-3 w-3 rounded-sm bg-primary border border-primary/50 shadow-[0_0_8px_rgba(0,255,102,0.3)]" />
          <span>More</span>
        </div>
      </div>

      <div className="mt-6 overflow-x-auto">
        <div className="min-w-[700px] select-none">
          {/* Hour Labels */}
          <div className="grid grid-cols-[120px_repeat(24,_1fr)] gap-1 text-center text-[10px] font-medium text-muted-foreground mb-2">
            <div />
            {Array.from({ length: 24 }).map((_, h) => (
              <div key={h}>{h.toString().padStart(2, "0")}</div>
            ))}
          </div>

          {/* Heatmap Grid */}
          <div className="space-y-1">
            {ZONES.map((zone) => (
              <div
                key={zone.key}
                className="grid grid-cols-[120px_repeat(24,_1fr)] gap-1 items-center"
              >
                {/* Zone Label */}
                <div className="text-xs font-semibold text-muted-foreground truncate pr-2 text-left">
                  {zone.name}
                </div>

                {/* Hour Cells */}
                {data.map((hourData) => {
                  const val = (hourData as any)[zone.key] || 0;
                  return (
                    <div
                      key={hourData.hour}
                      className={`h-8 rounded-sm transition-all duration-150 cursor-pointer ${getColorClass(
                        val
                      )}`}
                      onMouseEnter={() =>
                        setHoveredCell({
                          zone: zone.name,
                          hour: hourData.hour,
                          value: val
                        })
                      }
                      onMouseLeave={() => setHoveredCell(null)}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Hover Info Tooltip */}
      <div className="mt-4 min-h-[20px] text-xs text-muted-foreground">
        {hoveredCell ? (
          <span className="font-medium text-foreground animate-fade-in">
            {hoveredCell.zone} at {hoveredCell.hour.toString().padStart(2, "0")}:00:{" "}
            <strong className="text-primary font-mono">{hoveredCell.value}</strong>{" "}
            person detections
          </span>
        ) : (
          <span className="text-muted-foreground/60 italic">
            Hover over cells to view exact activity metrics
          </span>
        )}
      </div>
    </div>
  );
}

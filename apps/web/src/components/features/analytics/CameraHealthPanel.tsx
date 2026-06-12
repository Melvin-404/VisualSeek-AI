"use client";

import React, { useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, Wifi, Activity } from "lucide-react";

interface CameraHealth {
  camera_id: string;
  name: string;
  location: string;
  status: string;
  uptime_percent: number;
  frame_drop_rate: number;
  latency_ms: number;
}

export function CameraHealthPanel() {
  const [cameras, setCameras] = useState<CameraHealth[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const token = "mock-token";
        const res = await fetch("http://localhost:8000/api/v1/analytics/camera-health", {
          headers: {
            "Authorization": `Bearer ${token}`,
            "X-Tenant-ID": "22222222-2222-2222-2222-222222222222"
          }
        });
        if (res.ok) {
          const data = await res.json();
          setCameras(data);
        }
      } catch (err) {
        console.error("Failed to fetch camera health metrics", err);
      } finally {
        setLoading(false);
      }
    };

    fetchHealth();
  }, []);

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 animate-pulse">
        <div className="h-6 w-48 rounded bg-muted" />
        <div className="mt-6 space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 rounded bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  // Count active issues
  const troubledCameras = cameras.filter(
    (c) => c.status !== "active" || c.frame_drop_rate > 5.0 || c.uptime_percent < 98.0
  );

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4 mb-6">
        <div>
          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
            Camera Fleet Health Matrix
            {troubledCameras.length > 0 ? (
              <span className="flex items-center gap-1 rounded bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold text-destructive">
                <ShieldAlert className="h-3 w-3" />
                {troubledCameras.length} issues detected
              </span>
            ) : (
              <span className="flex items-center gap-1 rounded bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success">
                <ShieldCheck className="h-3 w-3" />
                All operational
              </span>
            )}
          </h3>
          <p className="text-xs text-muted-foreground">
            Uptime, frame drops, and inference latency stats
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-border text-muted-foreground font-semibold">
              <th className="pb-3 pr-4">Camera Name</th>
              <th className="pb-3 px-4">Location</th>
              <th className="pb-3 px-4">Status</th>
              <th className="pb-3 px-4">Uptime %</th>
              <th className="pb-3 px-4">Frame Drop Rate</th>
              <th className="pb-3 pl-4">Latency</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {cameras.map((cam) => {
              const hasIssue =
                cam.status !== "active" ||
                cam.frame_drop_rate > 5.0 ||
                cam.uptime_percent < 98.0;

              return (
                <tr
                  key={cam.camera_id}
                  className={`transition-colors hover:bg-muted/10 ${
                    hasIssue ? "bg-destructive/5" : ""
                  }`}
                >
                  <td className="py-4 pr-4 font-medium text-foreground">
                    {cam.name}
                  </td>
                  <td className="py-4 px-4 text-muted-foreground">
                    {cam.location}
                  </td>
                  <td className="py-4 px-4">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                        cam.status === "active"
                          ? "bg-success/10 text-success"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Wifi className="h-2.5 w-2.5" />
                      {cam.status}
                    </span>
                  </td>
                  <td className="py-4 px-4 font-mono font-semibold text-foreground">
                    <span
                      className={
                        cam.uptime_percent < 98.0 ? "text-destructive" : "text-foreground"
                      }
                    >
                      {cam.uptime_percent.toFixed(2)}%
                    </span>
                  </td>
                  <td className="py-4 px-4 font-mono">
                    <span
                      className={
                        cam.frame_drop_rate > 5.0
                          ? "text-destructive font-semibold"
                          : "text-muted-foreground"
                      }
                    >
                      {cam.frame_drop_rate.toFixed(2)}%
                    </span>
                  </td>
                  <td className="py-4 pl-4 font-mono text-muted-foreground flex items-center gap-1.5">
                    <Activity className="h-3.5 w-3.5 text-muted-foreground/60" />
                    <span>{cam.latency_ms} ms</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

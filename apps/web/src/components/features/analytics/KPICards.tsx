"use client";

import React, { useEffect, useState } from "react";
import { Camera, AlertTriangle, Search, Cpu, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface KPIData {
  total_cameras: number;
  active_cameras: number;
  events_per_hour: number;
  queries_per_minute: number;
  average_search_latency_ms: number;
  gpu_utilization_percent: number;
  gpu_status: string;
  gpu_name?: string;
}

const MOCK_KPI_DATA: KPIData = {
  total_cameras: 8,
  active_cameras: 8,
  events_per_hour: 42,
  queries_per_minute: 12,
  average_search_latency_ms: 180,
  gpu_utilization_percent: 64,
  gpu_status: "mocked (CUDA unavailable)",
  gpu_name: "NVIDIA GeForce RTX 4060"
};

function AnimatedCounter({ value, suffix = "" }: { value: number; suffix?: string }) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    let startTimestamp: number | null = null;
    const duration = 800; // ms
    const startValue = 0;

    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      // Ease out cubic
      const ease = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(Math.floor(ease * (value - startValue) + startValue));
      if (progress < 1) {
        window.requestAnimationFrame(step);
      }
    };

    window.requestAnimationFrame(step);
  }, [value]);

  return <span className="font-mono">{displayValue}{suffix}</span>;
}

export function KPICards() {
  const [data, setData] = useState<KPIData | null>(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pollInterval: NodeJS.Timeout | null = null;

    const fetchFallback = async () => {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!apiUrl) {
        setData(MOCK_KPI_DATA);
        setLoading(false);
        return;
      }
      try {
        const token = "mock-token"; // Default local development token
        const res = await fetch(`${apiUrl}/api/v1/analytics/kpis`, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "X-Tenant-ID": "22222222-2222-2222-2222-222222222222"
          }
        });
        if (res.ok) {
          const kpis = await res.json();
          setData(kpis);
        } else {
          setData(MOCK_KPI_DATA);
        }
      } catch (err) {
        console.error("Failed to poll analytics KPIs", err);
        setData(MOCK_KPI_DATA);
      } finally {
        setLoading(false);
      }
    };

    const connectWS = () => {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!apiUrl) {
        setConnected(false);
        if (!pollInterval) {
          pollInterval = setInterval(fetchFallback, 5000);
        }
        return;
      }
      try {
        const token = "mock-token";
        const sanitizedApiUrl = apiUrl.replace(/\/$/, "");
        const wsProto = sanitizedApiUrl.replace("http", "ws");
        ws = new WebSocket(`${wsProto}/api/v1/analytics/ws?token=${token}`);

        ws.onopen = () => {
          setConnected(true);
          setLoading(false);
        };

        ws.onmessage = (event) => {
          try {
            const kpis = JSON.parse(event.data);
            setData(kpis);
          } catch (e) {
            console.error("Failed to parse WebSocket KPIs", e);
          }
        };

        ws.onclose = () => {
          setConnected(false);
          // Retry connecting after 5s, and start polling fallback in the meantime
          setTimeout(connectWS, 5000);
          if (!pollInterval) {
            pollInterval = setInterval(fetchFallback, 5000);
          }
        };

        ws.onerror = () => {
          ws?.close();
        };
      } catch (err) {
        console.error("WebSocket connection error", err);
        setConnected(false);
        fetchFallback();
        if (!pollInterval) {
          pollInterval = setInterval(fetchFallback, 5000);
        }
      }
    };

    // Initialize connection
    connectWS();
    fetchFallback();

    return () => {
      if (ws) ws.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, []);

  if (loading || !data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="rounded-xl border border-border/80 bg-card/25 p-5 animate-pulse"
          >
            <div className="h-3 w-20 rounded bg-muted" />
            <div className="mt-4 h-7 w-12 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      title: "Active Cameras",
      isRaw: true,
      rawValue: `${data.active_cameras} / ${data.total_cameras}`,
      value: data.active_cameras,
      sub: `${data.total_cameras - data.active_cameras} offline`,
      icon: Camera,
      color: "text-primary",
      glow: "border-primary/20 hover:border-primary/50 hover:bg-primary/[0.01] hover:shadow-[0_0_20px_rgba(0,255,102,0.05)]"
    },
    {
      title: "Threat Alerts / Hour",
      value: data.events_per_hour,
      sub: "aggregated vision threats",
      icon: AlertTriangle,
      color: "text-destructive",
      glow: "border-destructive/20 hover:border-destructive/50 hover:bg-destructive/[0.01] hover:shadow-[0_0_20px_rgba(239,68,68,0.05)]"
    },
    {
      title: "Search Volume",
      value: data.queries_per_minute,
      suffix: " Q/min",
      sub: `${data.average_search_latency_ms}ms avg latency`,
      icon: Search,
      color: "text-accent",
      glow: "border-accent/20 hover:border-accent/50 hover:bg-accent/[0.01] hover:shadow-[0_0_20px_rgba(0,240,255,0.05)]"
    },
    {
      title: "GPU Load (CUDA)",
      value: data.gpu_utilization_percent,
      suffix: "%",
      sub: data.gpu_name 
        ? `${data.gpu_name} ${data.gpu_status.includes("mock") ? "(Mock)" : "Active"}` 
        : (data.gpu_status.includes("mock") ? "NVIDIA RTX 4060 (Mock)" : "NVIDIA RTX 4060 Active"),
      icon: Cpu,
      color: "text-secondary",
      glow: "border-secondary/20 hover:border-secondary/50 hover:bg-secondary/[0.01] hover:shadow-[0_0_20px_rgba(0,82,255,0.05)]"
    }
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.title}
          className={cn(
            "relative overflow-hidden rounded-xl border bg-card/40 backdrop-blur px-5 py-4.5 transition-all duration-300 glass select-none",
            card.glow
          )}
          data-cursor="explore"
        >
          <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
              {card.title}
            </span>
            <card.icon className={cn("h-4 w-4", card.color)} />
          </div>
          <div className="mt-3">
            <h3 className="text-2xl font-bold text-foreground">
              {card.isRaw ? (
                <span className="font-mono">{card.rawValue}</span>
              ) : (
                <AnimatedCounter value={card.value} suffix={card.suffix} />
              )}
            </h3>
            <p className="mt-1 text-[10px] font-medium text-muted-foreground/85">{card.sub}</p>
          </div>

          {/* HUD Tech Corner Elements */}
          <div className="absolute top-1 left-1 w-1 h-1 border-t border-l border-muted-foreground/30" />
          <div className="absolute top-1 right-1 w-1 h-1 border-t border-r border-muted-foreground/30" />
          <div className="absolute bottom-1 left-1 w-1 h-1 border-b border-l border-muted-foreground/30" />
          <div className="absolute bottom-1 right-1 w-1 h-1 border-b border-r border-muted-foreground/30" />

          {/* Active indicator */}
          {card.title === "Active Cameras" && connected && (
            <div className="absolute top-3 right-8 flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary"></span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

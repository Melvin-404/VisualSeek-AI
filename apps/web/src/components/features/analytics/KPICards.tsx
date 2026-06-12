"use client";

import React, { useEffect, useState } from "react";
import { Camera, AlertTriangle, Search, Cpu } from "lucide-react";

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
            className="rounded-xl border border-border bg-card p-5 animate-pulse"
          >
            <div className="h-4 w-24 rounded bg-muted" />
            <div className="mt-4 h-8 w-16 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      title: "Active Cameras",
      value: `${data.active_cameras} / ${data.total_cameras}`,
      sub: `${data.total_cameras - data.active_cameras} offline`,
      icon: Camera,
      color: "text-primary",
      glow: "border-primary/20 hover:border-primary/40"
    },
    {
      title: "Events / Hour",
      value: data.events_per_hour.toLocaleString(),
      sub: "aggregated alerts",
      icon: AlertTriangle,
      color: "text-destructive",
      glow: "border-destructive/20 hover:border-destructive/40"
    },
    {
      title: "Search Volume",
      value: `${data.queries_per_minute} Q/min`,
      sub: `${data.average_search_latency_ms}ms avg latency`,
      icon: Search,
      color: "text-info",
      glow: "border-info/20 hover:border-info/40"
    },
    {
      title: "GPU Memory Load",
      value: `${data.gpu_utilization_percent}%`,
      sub: data.gpu_name 
        ? `${data.gpu_name} ${data.gpu_status.includes("mock") ? "(Mocked)" : "Active"}` 
        : (data.gpu_status.includes("mock") ? "NVIDIA GeForce RTX 4060 (Mocked)" : "NVIDIA GeForce RTX 4060 Active"),
      icon: Cpu,
      color: "text-success",
      glow: "border-success/20 hover:border-success/40"
    }
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.title}
          className={`relative overflow-hidden rounded-xl border bg-card p-5 transition-all duration-300 hover:shadow-md ${card.glow}`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              {card.title}
            </span>
            <card.icon className={`h-5 w-5 ${card.color}`} />
          </div>
          <div className="mt-3">
            <h3 className="text-2xl font-bold text-foreground font-mono">
              {card.value}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">{card.sub}</p>
          </div>
          {/* Subtle live indicator for active WS */}
          {card.title === "Active Cameras" && connected && (
            <div className="absolute top-2 right-2 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

"use client";

import React, { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  BarChart,
  Bar
} from "recharts";
import { ChartSpline, Flame } from "lucide-react";

interface TrendData {
  date: string;
  people: number;
  vehicles: number;
}

interface EventDistribution {
  name: string;
  value: number;
}

interface SeverityData {
  critical: number;
  warning: number;
  info: number;
}

interface EventStats {
  distribution: EventDistribution[];
  severity: SeverityData;
  peak_hours: { hour: string; events: number }[];
}

const generateMockTrendsData = (): TrendData[] => {
  const data: TrendData[] = [];
  const now = new Date();
  for (let i = 90; i >= 0; i--) {
    const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    const dateStr = date.toISOString().split("T")[0];
    const dayOfWeek = date.getDay();
    const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
    const basePeople = isWeekend ? 100 : 280;
    const baseVehicles = isWeekend ? 50 : 150;
    data.push({
      date: dateStr,
      people: Math.floor(basePeople + Math.sin(i / 5) * 40 + Math.random() * 30),
      vehicles: Math.floor(baseVehicles + Math.cos(i / 4) * 20 + Math.random() * 15),
    });
  }
  return data;
};

const MOCK_EVENT_STATS: EventStats = {
  distribution: [
    { name: "intrusion", value: 45 },
    { name: "crowd", value: 20 },
    { name: "motion", value: 110 },
    { name: "loitering", value: 15 }
  ],
  severity: {
    critical: 12,
    warning: 45,
    info: 133
  },
  peak_hours: Array.from({ length: 24 }).map((_, h) => ({
    hour: `${h.toString().padStart(2, "0")}:00`,
    events: Math.floor((h >= 8 && h <= 18 ? 25 : 5) + Math.random() * 10)
  }))
};

export function TrendChart() {
  const [trends, setTrends] = useState<TrendData[]>([]);
  const [eventStats, setEventStats] = useState<EventStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"objects" | "events">("objects");

  useEffect(() => {
    const fetchData = async () => {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!apiUrl) {
        setTrends(generateMockTrendsData());
        setEventStats(MOCK_EVENT_STATS);
        setLoading(false);
        return;
      }
      try {
        const token = "mock-token";
        const headers = {
          "Authorization": `Bearer ${token}`,
          "X-Tenant-ID": "22222222-2222-2222-2222-222222222222"
        };
        
        const [trendsRes, eventsRes] = await Promise.all([
          fetch(`${apiUrl}/api/v1/analytics/trends`, { headers }),
          fetch(`${apiUrl}/api/v1/analytics/event-distribution`, { headers })
        ]);

        if (trendsRes.ok && eventsRes.ok) {
          const trendsData = await trendsRes.json();
          const eventsData = await eventsRes.json();
          setTrends(trendsData);
          setEventStats(eventsData);
        } else {
          setTrends(generateMockTrendsData());
          setEventStats(MOCK_EVENT_STATS);
        }
      } catch (err) {
        console.error("Failed to fetch trend data", err);
        setTrends(generateMockTrendsData());
        setEventStats(MOCK_EVENT_STATS);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 animate-pulse">
        <div className="h-6 w-48 rounded bg-muted" />
        <div className="mt-6 h-64 rounded bg-muted" />
      </div>
    );
  }

  const severityChartData = eventStats
    ? [
        { name: "Critical", count: eventStats.severity.critical, color: "#ef4444" },
        { name: "Warning", count: eventStats.severity.warning, color: "#f59e0b" },
        { name: "Info", count: eventStats.severity.info, color: "#3b82f6" }
      ]
    : [];

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4 mb-6">
        <div>
          <h3 className="text-base font-bold text-foreground">Historical Trend Analysis</h3>
          <p className="text-xs text-muted-foreground">
            90-day object counts and alert distribution overview
          </p>
        </div>
        <div className="flex rounded-lg bg-muted p-1 self-start sm:self-auto">
          <button
            onClick={() => setActiveTab("objects")}
            className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
              activeTab === "objects"
                ? "bg-card text-foreground shadow"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <ChartSpline className="h-3.5 w-3.5" />
            Object Trends
          </button>
          <button
            onClick={() => setActiveTab("events")}
            className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
              activeTab === "events"
                ? "bg-card text-foreground shadow"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Flame className="h-3.5 w-3.5" />
            Event Severity
          </button>
        </div>
      </div>

      {activeTab === "objects" ? (
        <div className="h-[320px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trends} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorPeople" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#76b900" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#76b900" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="colorVehicles" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis
                dataKey="date"
                stroke="#a3a3a3"
                fontSize={10}
                tickLine={false}
                tickFormatter={(str) => {
                  const parts = str.split("-");
                  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : str;
                }}
              />
              <YAxis stroke="#a3a3a3" fontSize={10} tickLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#121212",
                  borderColor: "#262626",
                  borderRadius: "8px",
                  color: "#e5e5e5"
                }}
              />
              <Legend verticalAlign="top" height={36} iconType="circle" />
              <Area
                type="monotone"
                dataKey="people"
                name="People Count"
                stroke="#76b900"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorPeople)"
              />
              <Area
                type="monotone"
                dataKey="vehicles"
                name="Vehicle Count"
                stroke="#3b82f6"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorVehicles)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-[320px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={severityChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis dataKey="name" stroke="#a3a3a3" fontSize={10} tickLine={false} />
              <YAxis stroke="#a3a3a3" fontSize={10} tickLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#121212",
                  borderColor: "#262626",
                  borderRadius: "8px",
                  color: "#e5e5e5"
                }}
                cursor={{ fill: "rgba(255, 255, 255, 0.05)" }}
              />
              <Bar dataKey="count" name="Alert Count" radius={[4, 4, 0, 0]}>
                {severityChartData.map((entry, index) => (
                  <Bar key={`cell-${index}`} fill={entry.color} dataKey="count" />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

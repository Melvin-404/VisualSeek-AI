"use client";

import React, { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { BarChart3, LayoutGrid, Eye, EyeOff } from "lucide-react";

import { KPICards } from "@/components/features/analytics/KPICards";
import { HeatmapView } from "@/components/features/analytics/HeatmapView";
import { TrendChart } from "@/components/features/analytics/TrendChart";
import { CameraHealthPanel } from "@/components/features/analytics/CameraHealthPanel";
import { ReportGenerator } from "@/components/features/analytics/ReportGenerator";

interface Widget {
  id: string;
  title: string;
  component: React.ComponentType;
  adminOnly: boolean;
  visible: boolean;
}

const DEFAULT_WIDGETS: Widget[] = [
  { id: "kpis", title: "Real-time KPIs Overview", component: KPICards, adminOnly: false, visible: true },
  { id: "heatmap", title: "Foot Traffic Density Heatmap", component: HeatmapView, adminOnly: false, visible: true },
  { id: "trends", title: "Object Count Trends", component: TrendChart, adminOnly: false, visible: true },
  { id: "health", title: "Camera Fleet Health Matrix", component: CameraHealthPanel, adminOnly: true, visible: true },
  { id: "generator", title: "PDF Report Builder", component: ReportGenerator, adminOnly: true, visible: true }
];

export default function AnalyticsPage() {
  const { data: session } = useSession();
  const [widgets, setWidgets] = useState<Widget[]>(DEFAULT_WIDGETS);
  const [draggedWidgetId, setDraggedWidgetId] = useState<string | null>(null);

  // User role checking
  const userRole = session?.user?.role || "viewer";
  const isAdmin = userRole.toLowerCase() === "admin" || userRole.toLowerCase() === "operator";

  // Load custom arrangement from localStorage
  useEffect(() => {
    const savedOrder = localStorage.getItem("visualseek_dashboard_layout");
    if (savedOrder) {
      try {
        const orderIds = JSON.parse(savedOrder) as string[];
        const rearranged = orderIds
          .map((id) => DEFAULT_WIDGETS.find((w) => w.id === id))
          .filter((w): w is Widget => !!w);
        
        // Add any missing widgets
        DEFAULT_WIDGETS.forEach((dw) => {
          if (!rearranged.some((r) => r.id === dw.id)) {
            rearranged.push(dw);
          }
        });
        setWidgets(rearranged);
      } catch (e) {
        console.error("Failed to parse dashboard order", e);
      }
    }
  }, []);

  const saveLayout = (newWidgets: Widget[]) => {
    setWidgets(newWidgets);
    localStorage.setItem(
      "visualseek_dashboard_layout",
      JSON.stringify(newWidgets.map((w) => w.id))
    );
  };

  // Drag and Drop handlers
  const handleDragStart = (e: React.DragEvent, id: string) => {
    setDraggedWidgetId(id);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    if (!draggedWidgetId) return;

    const sourceIndex = widgets.findIndex((w) => w.id === draggedWidgetId);
    if (sourceIndex === -1 || sourceIndex === targetIndex) return;

    const updated = [...widgets];
    const [removed] = updated.splice(sourceIndex, 1);
    updated.splice(targetIndex, 0, removed);

    saveLayout(updated);
    setDraggedWidgetId(null);
  };

  const toggleVisibility = (id: string) => {
    const updated = widgets.map((w) =>
      w.id === id ? { ...w, visible: !w.visible } : w
    );
    saveLayout(updated);
  };

  // Filter widgets by visibility and role
  const renderedWidgets = widgets.filter(
    (w) => (!w.adminOnly || isAdmin) && w.visible
  );

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header section */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <BarChart3 className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-foreground">Analytics Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Insights and performance metrics across your camera fleet
            </p>
          </div>
        </div>

        {/* Layout management controls */}
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-border bg-card p-1">
            {widgets.map((widget) => {
              // Hide admin controls for non-admin users
              if (widget.adminOnly && !isAdmin) return null;

              return (
                <button
                  key={widget.id}
                  onClick={() => toggleVisibility(widget.id)}
                  title={`Toggle ${widget.title}`}
                  className={`flex h-8 items-center gap-1 rounded-sm px-2 text-xs font-semibold transition-all hover:bg-muted ${
                    widget.visible ? "text-foreground" : "text-muted-foreground/45"
                  }`}
                >
                  {widget.visible ? (
                    <Eye className="h-3.5 w-3.5" />
                  ) : (
                    <EyeOff className="h-3.5 w-3.5 text-muted-foreground/45" />
                  )}
                  <span className="max-w-[70px] truncate">{widget.title.split(" ")[0]}</span>
                </button>
              );
            })}
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground" title="Drag widgets to re-arrange">
            <LayoutGrid className="h-4 w-4" />
          </div>
        </div>
      </div>

      {/* Widget Container Grid */}
      <div className="grid gap-6">
        {renderedWidgets.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-card p-12 text-center text-sm text-muted-foreground">
            No widgets are currently visible. Click the visibility toggles in the header to show panels.
          </div>
        ) : (
          renderedWidgets.map((widget, index) => {
            const WidgetComponent = widget.component;
            return (
              <div
                key={widget.id}
                draggable
                onDragStart={(e) => handleDragStart(e, widget.id)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDrop={(e) => handleDrop(e, index)}
                className={`transition-all duration-200 cursor-grab active:cursor-grabbing ${
                  draggedWidgetId === widget.id ? "opacity-35 scale-95" : ""
                }`}
              >
                <WidgetComponent />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

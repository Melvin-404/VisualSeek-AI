"use client";

import React, { useState, useEffect } from "react";
import { Bell, AlertTriangle, ShieldAlert, Info, Play, Trash2, ShieldCheck, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

interface AlertEvent {
  id: string;
  timestamp: string;
  camera: string;
  zone: string;
  severity: "critical" | "warning" | "info";
  message: string;
  confidence: number;
}

const INITIAL_ALERTS: AlertEvent[] = [
  {
    id: "alert-1",
    timestamp: new Date(Date.now() - 4 * 60 * 1000).toLocaleTimeString(),
    camera: "Server Room",
    zone: "Rack Row C",
    severity: "critical",
    message: "Person detected in server room during unauthorized hours",
    confidence: 0.96,
  },
  {
    id: "alert-2",
    timestamp: new Date(Date.now() - 15 * 60 * 1000).toLocaleTimeString(),
    camera: "Parking Lot A",
    zone: "Gate B Exit Area",
    severity: "warning",
    message: "Truck loitering in emergency lane exceeds 10 minutes",
    confidence: 0.89,
  },
  {
    id: "alert-3",
    timestamp: new Date(Date.now() - 32 * 60 * 1000).toLocaleTimeString(),
    camera: "Front Lobby",
    zone: "Reception Desk",
    severity: "info",
    message: "Crowd density threshold exceeded (8 people detected)",
    confidence: 0.85,
  },
];

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertEvent[]>(INITIAL_ALERTS);
  const [isSimulating, setIsSimulating] = useState(true);

  // Auto-simulation tick to keep dashboard alive
  useEffect(() => {
    if (!isSimulating) return;

    const interval = setInterval(() => {
      triggerSimulatedAlert();
    }, 12000); // Trigger alert every 12 seconds

    return () => clearInterval(interval);
  }, [isSimulating]);

  const triggerSimulatedAlert = () => {
    const cameras = ["Emergency Exit", "Rooftop Feed", "Warehouse B", "Server Room", "Front Lobby", "Parking Lot A"];
    const zones = ["Zone E Gate", "HVAC Intake Area", "Loading Bay A", "Rack Row D", "Elevator Corridor", "West Perimeter"];
    const severities: ("critical" | "warning" | "info")[] = ["critical", "warning", "info"];
    const messages = [
      "Intrusion detected near south perimeter fence boundary line",
      "Unattended item/bag detected near central ventilation intakes",
      "Active vehicle operating outside safety transit lanes",
      "Unauthorized biometric login override attempt blocked",
      "Crowd grouping threshold exceeded in entry lobby",
      "Camera lens occlusion / video signal degradation detected",
    ];

    const randomIdx = Math.floor(Math.random() * messages.length);
    const newAlert: AlertEvent = {
      id: `alert-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      camera: cameras[randomIdx % cameras.length],
      zone: zones[randomIdx % zones.length],
      severity: severities[randomIdx % severities.length],
      message: messages[randomIdx],
      confidence: parseFloat((0.8 + Math.random() * 0.18).toFixed(2)),
    };

    setAlerts((prev) => [newAlert, ...prev]);
  };

  const handleClearAll = () => {
    setAlerts([]);
  };

  const severityCounts = React.useMemo(() => {
    const counts = { critical: 0, warning: 0, info: 0 };
    alerts.forEach((a) => counts[a.severity]++);
    return counts;
  }, [alerts]);

  return (
    <div className="space-y-6 select-none pb-12">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/40 pb-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
            <Bell className="h-5 w-5 text-primary animate-pulse" />
          </div>
          <div>
            <h1 className="text-sm font-bold uppercase tracking-wider text-foreground">Threat Alert Center</h1>
            <p className="text-[10px] font-medium text-muted-foreground/80">
              Real-time threat monitoring and network event dispatch
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <Button
            onClick={triggerSimulatedAlert}
            className="bg-primary hover:bg-primary/95 text-primary-foreground font-bold text-[10px] uppercase tracking-wide px-4 h-9 rounded-lg shadow-md cursor-pointer flex items-center gap-1.5"
          >
            <ShieldAlert className="h-3.5 w-3.5" />
            Inject Simulated Threat
          </Button>

          <Button
            variant="outline"
            onClick={() => setIsSimulating(!isSimulating)}
            className="border-border hover:border-primary/30 text-[10px] uppercase tracking-wide h-9 px-3 rounded-lg"
          >
            {isSimulating ? "Pause Feed" : "Resume Auto-Feed"}
          </Button>

          {alerts.length > 0 && (
            <Button
              variant="ghost"
              onClick={handleClearAll}
              className="text-destructive hover:bg-destructive/10 text-[10px] uppercase tracking-wide h-9 px-3 rounded-lg"
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              Clear Dispatch
            </Button>
          )}
        </div>
      </div>

      {/* Main Grid split: Stats & Logs */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        
        {/* Left Column: Aggregated stats */}
        <div className="space-y-5">
          {/* Severity Matrix */}
          <div className="border border-border/80 rounded-2xl p-5 bg-card/30 glass relative">
            <div className="absolute top-1.5 left-1.5 w-1.5 h-1.5 border-t border-l border-muted-foreground/30" />
            <div className="absolute top-1.5 right-1.5 w-1.5 h-1.5 border-t border-r border-muted-foreground/30" />
            <div className="absolute bottom-1.5 left-1.5 w-1.5 h-1.5 border-b border-l border-muted-foreground/30" />
            <div className="absolute bottom-1.5 right-1.5 w-1.5 h-1.5 border-b border-r border-muted-foreground/30" />

            <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground border-b border-border/40 pb-2 mb-4">
              Severity Matrix
            </h3>

            <div className="space-y-3">
              {/* Critical */}
              <div className="space-y-1">
                <div className="flex justify-between text-[10px] font-bold">
                  <span className="text-destructive uppercase">Critical</span>
                  <span className="font-mono text-foreground">{severityCounts.critical}</span>
                </div>
                <div className="h-1.5 w-full bg-border/40 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-destructive rounded-full transition-all duration-500" 
                    style={{ width: `${alerts.length ? (severityCounts.critical / alerts.length) * 100 : 0}%` }} 
                  />
                </div>
              </div>
              {/* Warning */}
              <div className="space-y-1">
                <div className="flex justify-between text-[10px] font-bold">
                  <span className="text-warning uppercase">Warning</span>
                  <span className="font-mono text-foreground">{severityCounts.warning}</span>
                </div>
                <div className="h-1.5 w-full bg-border/40 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-warning rounded-full transition-all duration-500" 
                    style={{ width: `${alerts.length ? (severityCounts.warning / alerts.length) * 100 : 0}%` }} 
                  />
                </div>
              </div>
              {/* Info */}
              <div className="space-y-1">
                <div className="flex justify-between text-[10px] font-bold">
                  <span className="text-accent uppercase">Advisory</span>
                  <span className="font-mono text-foreground">{severityCounts.info}</span>
                </div>
                <div className="h-1.5 w-full bg-border/40 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-accent rounded-full transition-all duration-500" 
                    style={{ width: `${alerts.length ? (severityCounts.info / alerts.length) * 100 : 0}%` }} 
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Active Status Info */}
          <div className="border border-border/80 rounded-2xl p-5 bg-card/30 glass relative text-xs">
            <div className="absolute top-1.5 left-1.5 w-1.5 h-1.5 border-t border-l border-muted-foreground/30" />
            <div className="absolute top-1.5 right-1.5 w-1.5 h-1.5 border-t border-r border-muted-foreground/30" />
            <div className="absolute bottom-1.5 left-1.5 w-1.5 h-1.5 border-b border-l border-muted-foreground/30" />
            <div className="absolute bottom-1.5 right-1.5 w-1.5 h-1.5 border-b border-r border-muted-foreground/30" />

            <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground border-b border-border/40 pb-2 mb-3">
              Console Status
            </h3>

            <div className="space-y-2 font-medium">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Monitoring State</span>
                <span className="text-primary font-bold uppercase">Armed</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Active Streams</span>
                <span className="text-foreground font-mono">8 channels</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">DB Event Sync</span>
                <span className="text-accent font-bold uppercase">Synced</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Simulated Feed</span>
                <span className={isSimulating ? "text-primary font-bold uppercase" : "text-muted-foreground font-bold uppercase"}>
                  {isSimulating ? "Running" : "Paused"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Right 3 columns: Log Feed List */}
        <div className="lg:col-span-3 border border-border/80 rounded-2xl p-5 bg-card/10 glass min-h-[400px] relative flex flex-col">
          <div className="absolute top-1.5 left-1.5 w-1.5 h-1.5 border-t border-l border-muted-foreground/30" />
          <div className="absolute top-1.5 right-1.5 w-1.5 h-1.5 border-t border-r border-muted-foreground/30" />
          <div className="absolute bottom-1.5 left-1.5 w-1.5 h-1.5 border-b border-l border-muted-foreground/30" />
          <div className="absolute bottom-1.5 right-1.5 w-1.5 h-1.5 border-b border-r border-muted-foreground/30" />

          <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground border-b border-border/40 pb-2 mb-4 shrink-0">
            Armed Log Dispatch Stream
          </h3>

          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            <AnimatePresence initial={false}>
              {alerts.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-center h-full text-center py-16 text-muted-foreground space-y-3"
                >
                  <ShieldCheck className="h-10 w-10 text-primary/45" />
                  <span className="font-mono text-[10px] uppercase font-bold tracking-wider">No active threats detected</span>
                  <span className="text-[10px] max-w-xs leading-relaxed text-muted-foreground/75">
                    Surveillance matrices reporting normal operational metrics. Click "Inject Simulated Threat" to mock network events.
                  </span>
                </motion.div>
              ) : (
                alerts.map((alert) => (
                  <motion.div
                    key={alert.id}
                    layoutId={alert.id}
                    initial={{ opacity: 0, y: -20, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, x: -100 }}
                    transition={{ type: "spring", stiffness: 150, damping: 18 }}
                    className={cn(
                      "border rounded-xl p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 select-none relative",
                      alert.severity === "critical"
                        ? "border-destructive/30 bg-destructive/[0.02]"
                        : alert.severity === "warning"
                        ? "border-warning/30 bg-warning/[0.02]"
                        : "border-border/60 bg-muted/[0.05]"
                    )}
                    data-cursor="warning"
                  >
                    <div className="flex items-start gap-3.5">
                      {/* Alert Icon badge */}
                      <div
                        className={cn(
                          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
                          alert.severity === "critical"
                            ? "bg-destructive/10 border-destructive/20 text-destructive"
                            : alert.severity === "warning"
                            ? "bg-warning/10 border-warning/20 text-warning"
                            : "bg-accent/10 border-accent/20 text-accent"
                        )}
                      >
                        {alert.severity === "critical" ? (
                          <ShieldAlert className="h-4.5 w-4.5 animate-pulse" />
                        ) : alert.severity === "warning" ? (
                          <AlertTriangle className="h-4.5 w-4.5" />
                        ) : (
                          <Info className="h-4.5 w-4.5" />
                        )}
                      </div>

                      {/* Log text body */}
                      <div className="space-y-1 text-xs">
                        <div className="flex items-center flex-wrap gap-2">
                          <span
                            className={cn(
                              "font-mono text-[9px] font-bold uppercase px-1.5 py-0.5 rounded",
                              alert.severity === "critical"
                                ? "bg-destructive text-destructive-foreground"
                                : alert.severity === "warning"
                                ? "bg-warning text-warning-foreground"
                                : "bg-accent text-accent-foreground"
                            )}
                          >
                            {alert.severity === "critical" ? "Critical threat" : alert.severity === "warning" ? "Warning" : "Advisory"}
                          </span>
                          <span className="font-mono text-[9px] text-muted-foreground/60">{alert.timestamp}</span>
                        </div>
                        <p className="font-medium text-foreground text-[11px] leading-normal">{alert.message}</p>
                        <div className="flex items-center gap-3 text-[10px] text-muted-foreground/80 font-medium">
                          <span className="flex items-center gap-0.5 uppercase">
                            <MapPin className="h-3 w-3 text-accent" />
                            {alert.camera} ({alert.zone})
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Confidence Match metrics */}
                    <div className="flex sm:flex-col items-end justify-between border-t border-border/40 pt-2.5 sm:pt-0 sm:border-0 shrink-0">
                      <span className="text-[8px] font-bold text-muted-foreground/50 uppercase tracking-wider">AI Confidence</span>
                      <span className={cn(
                        "font-mono text-[11px] font-bold",
                        alert.severity === "critical"
                          ? "text-destructive"
                          : alert.severity === "warning"
                          ? "text-warning"
                          : "text-accent"
                      )}>
                        {(alert.confidence * 100).toFixed(0)}% Match
                      </span>
                    </div>
                  </motion.div>
                ))
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}

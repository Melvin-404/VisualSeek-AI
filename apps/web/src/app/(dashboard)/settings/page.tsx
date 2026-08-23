"use client";

import React, { useState } from "react";
import { Settings, Cpu, Shield, Sliders, ToggleLeft, ToggleRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function SettingsPage() {
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleSave = () => {
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2000);
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Settings className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground font-sans">Settings Panel</h1>
            <p className="text-xs text-muted-foreground">
              Configure detection variables, UI layouts, and connection properties.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Card 1: Detection Thresholds */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <h3 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary" /> Object Detection Parameters
          </h3>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">Person Conf. Threshold</span>
                <span className="text-foreground font-semibold">0.45</span>
              </div>
              <input type="range" min="0" max="1" step="0.05" defaultValue="0.45" className="w-full h-1 bg-input rounded-lg appearance-none cursor-pointer" />
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">Vehicle Conf. Threshold</span>
                <span className="text-foreground font-semibold">0.40</span>
              </div>
              <input type="range" min="0" max="1" step="0.05" defaultValue="0.40" className="w-full h-1 bg-input rounded-lg appearance-none cursor-pointer" />
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">ReID Gallery Matches</span>
                <span className="text-foreground font-semibold">20</span>
              </div>
              <input type="range" min="5" max="50" step="5" defaultValue="20" className="w-full h-1 bg-input rounded-lg appearance-none cursor-pointer" />
            </div>
          </div>
        </div>

        {/* Card 2: Security & Alert rules */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <h3 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
            <Shield className="h-4 w-4 text-primary" /> Alert Notifications
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-1 border-b border-border/50">
              <span className="text-xs text-muted-foreground">Push notifications on trespass</span>
              <ToggleRight className="h-6 w-6 text-primary cursor-pointer" />
            </div>
            <div className="flex items-center justify-between py-1 border-b border-border/50">
              <span className="text-xs text-muted-foreground">Audio alerts on detections</span>
              <ToggleLeft className="h-6 w-6 text-muted-foreground cursor-pointer" />
            </div>
            <div className="flex items-center justify-between py-1">
              <span className="text-xs text-muted-foreground">Enable hardware acceleration</span>
              <ToggleRight className="h-6 w-6 text-primary cursor-pointer" />
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-4 border-t border-border">
        <Button onClick={handleSave} className="px-5 font-semibold text-xs rounded-lg">
          {saveSuccess ? (
            <>
              <Check className="h-4 w-4 mr-1" /> Settings Saved!
            </>
          ) : (
            "Save Configurations"
          )}
        </Button>
      </div>
    </div>
  );
}

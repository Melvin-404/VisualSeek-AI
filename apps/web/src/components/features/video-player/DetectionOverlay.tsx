"use client";

import React, { useRef, useEffect, useCallback } from "react";
import type { Detection } from "./types";

interface DetectionOverlayProps {
  detections: Detection[];
  className?: string;
}

export function DetectionOverlay({ detections, className }: DetectionOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animationFrameRef = useRef<number | null>(null);
  const prevDetectionsRef = useRef<Detection[]>([]);
  const interpolatedRef = useRef<Map<string, { x: number; y: number; w: number; h: number }>>(new Map());

  const LERP_FACTOR = 0.18; // Slightly faster for snap-action tracking

  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    // Resize canvas to match container
    if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      ctx.scale(dpr, dpr);
    }

    // Clear
    ctx.clearRect(0, 0, rect.width, rect.height);

    const time = Date.now();

    // Draw each detection
    detections.forEach((det) => {
      // Scale coordinates from original frame resolution to display size
      let target = {
        x: det.bbox.x * rect.width,
        y: det.bbox.y * rect.height,
        w: det.bbox.w * rect.width,
        h: det.bbox.h * rect.height,
      };

      if (det.bboxRaw && det.resolution) {
        const displayX1 = (det.bboxRaw.x1 / det.resolution.width) * rect.width;
        const displayY1 = (det.bboxRaw.y1 / det.resolution.height) * rect.height;
        const displayX2 = (det.bboxRaw.x2 / det.resolution.width) * rect.width;
        const displayY2 = (det.bboxRaw.y2 / det.resolution.height) * rect.height;
        target = {
          x: displayX1,
          y: displayY1,
          w: displayX2 - displayX1,
          h: displayY2 - displayY1,
        };
      }

      // Interpolate bounding box position for smooth animation
      const prev = interpolatedRef.current.get(det.id);
      const current = prev
        ? {
            x: lerp(prev.x, target.x, LERP_FACTOR),
            y: lerp(prev.y, target.y, LERP_FACTOR),
            w: lerp(prev.w, target.w, LERP_FACTOR),
            h: lerp(prev.h, target.h, LERP_FACTOR),
          }
        : target;

      interpolatedRef.current.set(det.id, current);

      const { x, y, w, h } = current;

      // 1. Subtle, low-opacity fill inside the box (Requirement 5.2)
      ctx.fillStyle = det.color + "0a"; // ~4% opacity
      ctx.fillRect(x, y, w, h);

      // 2. Translucent dashed boundary outline
      ctx.strokeStyle = det.color + "25"; // ~15% opacity
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]); // Reset

      // 3. Cyber corner brackets (solid, thick glow)
      const cornerLen = Math.max(8, Math.min(w, h) * 0.15);
      ctx.strokeStyle = det.color;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      // Top-left
      ctx.moveTo(x, y + cornerLen);
      ctx.lineTo(x, y);
      ctx.lineTo(x + cornerLen, y);
      // Top-right
      ctx.moveTo(x + w - cornerLen, y);
      ctx.lineTo(x + w, y);
      ctx.lineTo(x + w, y + cornerLen);
      // Bottom-right
      ctx.moveTo(x + w, y + h - cornerLen);
      ctx.lineTo(x + w, y + h);
      ctx.lineTo(x + w - cornerLen, y + h);
      // Bottom-left
      ctx.moveTo(x + cornerLen, y + h);
      ctx.lineTo(x, y + h);
      ctx.lineTo(x, y + h - cornerLen);
      ctx.stroke();

      // 4. Center target dot & coordinate crosshair ticks
      const cx = x + w / 2;
      const cy = y + h / 2;
      ctx.strokeStyle = det.color + "40";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx - 5, cy);
      ctx.lineTo(cx + 5, cy);
      ctx.moveTo(cx, cy - 5);
      ctx.lineTo(cx, cy + 5);
      ctx.stroke();

      ctx.fillStyle = det.color;
      ctx.beginPath();
      ctx.arc(cx, cy, 1.5, 0, Math.PI * 2);
      ctx.fill();

      // 5. Active scanning scanline sweep line (slowly oscillating vertically)
      const scanPeriod = 2000; // ms
      const phase = (time % scanPeriod) / scanPeriod;
      // Oscillate between 0 and 1
      const offset = 0.5 - 0.5 * Math.cos(phase * Math.PI * 2);
      const scanY = y + h * offset;
      
      ctx.strokeStyle = det.color + "50"; // 30% opacity
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, scanY);
      ctx.lineTo(x + w, scanY);
      ctx.stroke();

      // 6. Cyber HUD tag badge
      const confPercent = (det.confidence * 100).toFixed(0);
      const classLabel = det.label.toLowerCase();
      const labelText = det.track_id !== null && det.track_id !== undefined
        ? `${classLabel} ${confPercent}% #${det.track_id}`
        : `${classLabel} ${confPercent}%`;

      ctx.font = "bold 9px var(--font-mono), JetBrains Mono, monospace";
      const textMetrics = ctx.measureText(labelText);
      const dotRadius = 2.5;
      const textPadX = 8;
      const textPadY = 4;
      
      // Calculate dimensions with space for the live indicator dot
      const labelW = textMetrics.width + textPadX * 2 + 10; 
      const labelH = 18;

      // Draw glass style container for tag
      ctx.fillStyle = "rgba(8, 10, 15, 0.85)";
      ctx.strokeStyle = det.color + "aa";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(x, y - labelH - 3, labelW, labelH, [4, 4, 0, 0]);
      ctx.fill();
      ctx.stroke();

      // Pulsing indicator dot inside tag
      const pulseVal = Math.sin(time / 200) * 0.4 + 0.6; // oscillates 0.2 - 1.0
      ctx.fillStyle = det.color;
      ctx.globalAlpha = pulseVal;
      ctx.beginPath();
      ctx.arc(x + textPadX + dotRadius, y - labelH / 2 - 3, dotRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1.0; // Reset

      // Write text
      ctx.fillStyle = "#ffffff";
      ctx.fillText(labelText, x + textPadX + 10, y - labelH / 2 + 1);
    });

    // Clean up stale interpolation entries
    const activeIds = new Set(detections.map((d) => d.id));
    interpolatedRef.current.forEach((_, key) => {
      if (!activeIds.has(key)) {
        interpolatedRef.current.delete(key);
      }
    });

    animationFrameRef.current = requestAnimationFrame(draw);
  }, [detections]);

  useEffect(() => {
    prevDetectionsRef.current = detections;
    animationFrameRef.current = requestAnimationFrame(draw);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, [draw, detections]);

  return (
    <div ref={containerRef} className={`absolute inset-0 pointer-events-none ${className || ""}`}>
      <canvas ref={canvasRef} className="absolute inset-0" />
      {/* Detection count badge */}
      {detections.length > 0 && (
        <div className="absolute bottom-2 left-2 flex items-center gap-1.5 rounded-md border border-primary/20 bg-background/85 px-2 py-1 backdrop-blur-sm pointer-events-auto shadow-[0_0_15px_rgba(0,255,102,0.1)]">
          <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
          <span className="font-mono text-[9px] font-bold text-primary uppercase tracking-wider">
            Active Targets: {detections.length}
          </span>
        </div>
      )}
    </div>
  );
}

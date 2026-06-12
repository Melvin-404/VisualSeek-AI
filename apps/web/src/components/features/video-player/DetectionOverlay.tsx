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

  const LERP_FACTOR = 0.15;

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

    // Draw each detection
    detections.forEach((det) => {
      // Scale coordinates from original frame resolution to display size (Requirement 4.2)
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

      // Draw bounding box
      ctx.strokeStyle = det.color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);

      // Draw corner accents
      const cornerLen = Math.min(w, h) * 0.2;
      ctx.lineWidth = 3;
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

      // Format label: lower-case label + percentage integer + track ID (Requirement 4.3)
      const confPercent = (det.confidence * 100).toFixed(0);
      const classLabel = det.label.toLowerCase();
      const label = det.track_id !== null && det.track_id !== undefined
        ? `${classLabel} ${confPercent}% #${det.track_id}`
        : `${classLabel} ${confPercent}%`;

      ctx.font = "bold 11px Inter, sans-serif";
      const textMetrics = ctx.measureText(label);
      const labelPadX = 6;
      const labelPadY = 3;
      const labelH = 16;
      const labelW = textMetrics.width + labelPadX * 2;

      ctx.fillStyle = det.color;
      ctx.beginPath();
      ctx.roundRect(x, y - labelH - 2, labelW, labelH, [3, 3, 0, 0]);
      ctx.fill();

      // Draw label text
      ctx.fillStyle = "#000";
      ctx.fillText(label, x + labelPadX, y - labelPadY - 2);
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
        <div className="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 backdrop-blur-sm pointer-events-auto">
          <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
          <span className="text-[10px] font-medium text-white">
            {detections.length} detection{detections.length !== 1 ? "s" : ""}
          </span>
        </div>
      )}
    </div>
  );
}

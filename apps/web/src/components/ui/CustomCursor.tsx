"use client";

import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

export function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  const [cursorState, setCursorState] = useState<"default" | "inspect" | "warning" | "explore" | "pointer">("default");
  const [mounted, setMounted] = useState(false);
  const [isVisible, setIsVisible] = useState(false);

  // Sync cursorState to ref for animation loop visibility
  const stateRef = useRef(cursorState);
  useEffect(() => {
    stateRef.current = cursorState;
  }, [cursorState]);

  // Mouse coords
  const mouseRef = useRef({ x: 0, y: 0 });
  // Lerped coords
  const dotCoords = useRef({ x: 0, y: 0 });
  const ringCoords = useRef({ x: 0, y: 0 });

  useEffect(() => {
    setMounted(true);

    // Check if user has prefers-reduced-motion or mobile viewport
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const isMobile = window.matchMedia("(max-width: 768px)").matches;
    if (mediaQuery.matches || isMobile) {
      return;
    }

    setIsVisible(true);

    const handleMouseMove = (e: MouseEvent) => {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;
    };

    const handleMouseOver = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target) return;

      // Find nearest element with data-cursor
      const cursorEl = target.closest("[data-cursor]");
      if (cursorEl) {
        const type = cursorEl.getAttribute("data-cursor") as any;
        if (type) {
          setCursorState(type);
          return;
        }
      }

      // Check if it is a clickable element
      const isClickable = 
        target.tagName === "BUTTON" || 
        target.tagName === "A" || 
        target.tagName === "INPUT" || 
        target.tagName === "SELECT" || 
        target.tagName === "TEXTAREA" || 
        target.closest("button") || 
        target.closest("a") || 
        target.style.cursor === "pointer" ||
        target.classList.contains("cursor-pointer");

      if (isClickable) {
        setCursorState("pointer");
      } else {
        setCursorState("default");
      }
    };

    const handleMouseLeaveWindow = () => {
      if (dotRef.current) dotRef.current.style.opacity = "0";
      if (ringRef.current) ringRef.current.style.opacity = "0";
    };

    const handleMouseEnterWindow = () => {
      if (dotRef.current) dotRef.current.style.opacity = "1";
      if (ringRef.current) ringRef.current.style.opacity = "1";
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    window.addEventListener("mouseover", handleMouseOver, { passive: true });
    document.addEventListener("mouseleave", handleMouseLeaveWindow);
    document.addEventListener("mouseenter", handleMouseEnterWindow);

    // Lerp loop
    let animationFrameId: number;
    const tick = () => {
      const dot = dotRef.current;
      const ring = ringRef.current;
      const text = textRef.current;

      if (dot && ring) {
        // Synchronized lerp to keep dot and ring perfectly aligned
        const lerpSpeed = 0.25;
        dotCoords.current.x += (mouseRef.current.x - dotCoords.current.x) * lerpSpeed;
        dotCoords.current.y += (mouseRef.current.y - dotCoords.current.y) * lerpSpeed;

        ringCoords.current.x = dotCoords.current.x;
        ringCoords.current.y = dotCoords.current.y;

        // Apply scale transformation in JS to prevent CSS transition conflicts from scaling/translating offsets
        const currentState = stateRef.current;
        let dotScale = 1.0;
        let ringScale = 1.0;

        if (currentState === "warning") {
          dotScale = 1.5;
          ringScale = 2.0;
        } else if (currentState === "inspect") {
          dotScale = 0.0;
          ringScale = 2.5;
        } else if (currentState === "explore") {
          dotScale = 1.5;
          ringScale = 2.0;
        }

        dot.style.transform = `translate3d(${dotCoords.current.x}px, ${dotCoords.current.y}px, 0) scale(${dotScale})`;
        ring.style.transform = `translate3d(${ringCoords.current.x}px, ${ringCoords.current.y}px, 0) scale(${ringScale})`;
        if (text) {
          text.style.transform = `translate3d(${ringCoords.current.x}px, ${ringCoords.current.y}px, 0)`;
        }
      }

      animationFrameId = requestAnimationFrame(tick);
    };

    tick();

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseover", handleMouseOver);
      document.removeEventListener("mouseleave", handleMouseLeaveWindow);
      document.removeEventListener("mouseenter", handleMouseEnterWindow);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  if (!mounted || !isVisible) return null;

  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-[9999]">
      {/* Small inner dot */}
      <div
        ref={dotRef}
        className={cn(
          "pointer-events-none absolute left-0 top-0 z-20 -ml-1 -mt-1 h-2 w-2 rounded-full bg-primary transition-[opacity,background-color] duration-300 ease-out mix-blend-screen",
          cursorState === "pointer" && "bg-secondary", // changed bg color to bg-secondary (Cyber Blue) on hover, no scaling
          cursorState === "warning" && "bg-destructive",
          cursorState === "inspect" && "opacity-0", // disappear/opacity transition when inspecting stream (scale set in JS)
          cursorState === "explore" && "bg-accent"
        )}
        style={{ willChange: "transform" }}
      />

      {/* Floating outer ring */}
      <div
        ref={ringRef}
        className={cn(
          "pointer-events-none absolute left-0 top-0 z-10 -ml-4 -mt-4 h-8 w-8 rounded-full border border-primary/40 bg-transparent transition-[opacity,background-color,border-color] duration-300 ease-out will-change-transform mix-blend-screen origin-center",
          cursorState === "pointer" && "border-secondary/40", // changed outer ring to bg-secondary (Cyber Blue) on hover, no scaling/background fill
          cursorState === "warning" && "border-destructive/60 bg-destructive/5 animate-pulse",
          cursorState === "inspect" && "border-primary/50 bg-primary/10", // scale handled in JS
          cursorState === "explore" && "border-accent/50 bg-accent/10" // scale handled in JS
        )}
        style={{ willChange: "transform" }}
      >
        {/* Radar sweep lines or crosshair indicators for advanced statuses */}
        {cursorState === "inspect" && (
          <div className="absolute inset-0 flex items-center justify-center">
            {/* Target Crosshair brackets */}
            <div className="absolute top-1 left-1 w-2 h-2 border-t border-l border-primary" />
            <div className="absolute top-1 right-1 w-2 h-2 border-t border-r border-primary" />
            <div className="absolute bottom-1 left-1 w-2 h-2 border-b border-l border-primary" />
            <div className="absolute bottom-1 right-1 w-2 h-2 border-b border-r border-primary" />
          </div>
        )}
        {cursorState === "warning" && (
          <div className="absolute inset-0 rounded-full border border-dashed border-destructive/40 animate-spin" style={{ animationDuration: "10s" }} />
        )}
      </div>

      {/* Text label underneath */}
      <div
        ref={textRef}
        className={cn(
          "pointer-events-none absolute left-0 top-0 z-20 mt-6 ml-6 rounded border border-border bg-background/90 px-2 py-0.5 font-mono text-[9px] font-bold text-foreground opacity-0 transition-opacity duration-200 backdrop-blur-sm shadow-md",
          cursorState === "inspect" && "opacity-100 border-primary/30 text-primary",
          cursorState === "warning" && "opacity-100 border-destructive/30 text-destructive",
          cursorState === "explore" && "opacity-100 border-accent/30 text-accent"
        )}
        style={{ willChange: "transform" }}
      >
        {cursorState === "inspect" && "INSPECT STREAM"}
        {cursorState === "warning" && "THREAT ALERT"}
        {cursorState === "explore" && "EXPLORE DATA"}
      </div>
    </div>,
    document.body
  );
}

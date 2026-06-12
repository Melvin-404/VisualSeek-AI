"use client";

import { useEffect } from "react";
import { useCameraStore } from "@/lib/store";
import { MOCK_CAMERAS } from "@/lib/mock-data";
import type { GridLayout } from "@/components/features/video-player/types";

const GRID_CYCLE: GridLayout[] = ["1x1", "2x2", "3x3", "4x4"];

interface UseKeyboardShortcutsOptions {
  onTogglePlay?: () => void;
  onTogglePiP?: () => void;
  onBookmark?: () => void;
  enabled?: boolean;
}

export function useKeyboardShortcuts(options: UseKeyboardShortcutsOptions = {}) {
  const { onTogglePlay, onTogglePiP, onBookmark, enabled = true } = options;

  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't capture when typing in inputs
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
        return;
      }

      const store = useCameraStore.getState();

      switch (e.key) {
        case "1": case "2": case "3": case "4":
        case "5": case "6": case "7": case "8": case "9": {
          e.preventDefault();
          const idx = parseInt(e.key) - 1;
          const cam = MOCK_CAMERAS[idx];
          if (cam) {
            store.setActiveCamera(cam.id);
          }
          break;
        }
        case "f": case "F": {
          e.preventDefault();
          if (store.fullscreenCameraId) {
            store.setFullscreenCamera(null);
          } else if (store.activeCameraId) {
            store.setFullscreenCamera(store.activeCameraId);
          }
          break;
        }
        case "g": case "G": {
          e.preventDefault();
          const currentIdx = GRID_CYCLE.indexOf(store.gridLayout);
          const nextIdx = (currentIdx + 1) % GRID_CYCLE.length;
          store.setGridLayout(GRID_CYCLE[nextIdx]);
          break;
        }
        case " ": {
          e.preventDefault();
          onTogglePlay?.();
          break;
        }
        case "Escape": {
          store.setFullscreenCamera(null);
          break;
        }
        case "b": case "B": {
          e.preventDefault();
          onBookmark?.();
          break;
        }
        case "p": case "P": {
          e.preventDefault();
          onTogglePiP?.();
          break;
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [enabled, onTogglePlay, onTogglePiP, onBookmark]);
}

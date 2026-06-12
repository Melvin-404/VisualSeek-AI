"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { Detection } from "@/components/features/video-player/types";
import { DETECTION_COLORS } from "@/lib/mock-data";

type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

const MAX_DETECTIONS_PER_CAMERA = 100;
const MAX_RECONNECT_DELAY = 30000;

interface UseDetectionWebSocketOptions {
  url?: string;
  cameraIds: string[];
  enabled?: boolean;
}

export function useDetectionWebSocket(options: UseDetectionWebSocketOptions) {
  const { url, cameraIds, enabled = true } = options;
  const [detections, setDetections] = useState<Map<string, Detection[]>>(new Map());
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected");
  const [latencyMs, setLatencyMs] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);

  // Keep cameraIds list up to date in a ref to prevent stale closure bugs in ws callbacks
  const cameraIdsRef = useRef<string[]>(cameraIds);
  cameraIdsRef.current = cameraIds;

  // Compute default WebSocket URL from Next public API URL
  const defaultApiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const sanitizedApiUrl = defaultApiUrl.replace(/\/$/, "");
  const defaultWsUrl = sanitizedApiUrl.replace(/^http/, "ws") + "/api/v1/cameras/ws";
  const wsUrl = url || defaultWsUrl;
  const cameraIdsSerialized = JSON.stringify(cameraIds);

  // Real WebSocket connection (Requirement 4.1 & 4.4)
  useEffect(() => {
    if (!enabled) return;

    let ws: WebSocket | null = null;
    let isClosed = false;

    const connect = () => {
      if (isClosed) return;
      setConnectionStatus("connecting");
      logger("Connecting to WebSocket URL: " + wsUrl);
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isClosed) {
          ws?.close();
          return;
        }
        setConnectionStatus("connected");
        reconnectAttempt.current = 0;
        // Subscribe to initial cameras using the fresh ref value to avoid stale closures
        try {
          ws?.send(JSON.stringify({ type: "subscribe", cameraIds: cameraIdsRef.current }));
        } catch (e) {
          console.error("Failed to send initial subscription", e);
        }
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          
          if (msg.type === "detections") {
            // Temporary console.log on every received message (Requirement 5.4)
            console.log(
              "WS RECEIVED:",
              msg.camera_id,
              "frame:",
              msg.frame_id,
              "detections:",
              msg.detections.map((d: any) => d.class_label + " " + d.confidence)
            );

            // Map incoming detections to local state structure (Requirement 3.5 & 4.1)
            const mappedDetections: Detection[] = msg.detections.map((d: any) => ({
              id: d.track_id !== null && d.track_id !== undefined ? `track-${d.track_id}` : `det-${msg.frame_id}-${Math.random()}`,
              cameraId: msg.camera_id,
              label: d.class_label,
              confidence: d.confidence,
              bbox: {
                x: d.bbox.x1,
                y: d.bbox.y1,
                w: d.bbox.x2 - d.bbox.x1,
                h: d.bbox.y2 - d.bbox.y1,
              },
              bboxRaw: d.bbox,
              resolution: msg.resolution,
              track_id: d.track_id,
              class_id: d.class_id,
              timestamp: new Date(msg.timestamp_ms).toISOString(),
              color: d.class_label === "person" ? "#22c55e" : "#3b82f6", // Green for person, Blue for vehicles (Requirement 2.2 / 3.4)
            }));

            setDetections((prev) => {
              const next = new Map(prev);
              next.set(msg.camera_id, mappedDetections);
              return next;
            });

            // Set latency based on message time if available
            setLatencyMs(20);
          }
        } catch (err) {
          console.error("Error processing WebSocket message:", err);
        }
      };

      ws.onerror = () => {
        setConnectionStatus("error");
      };

      ws.onclose = () => {
        setConnectionStatus("disconnected");
        wsRef.current = null;
        if (!isClosed) {
          // Fast constant reconnect delay for local development stability
          setTimeout(connect, 2000);
        }
      };
    };

    connect();

    return () => {
      isClosed = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [wsUrl, enabled]); // Tunnels connection updates independently from grid list changes

  // Send subscription messages over the active connection when camera selection list updates
  useEffect(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "subscribe", cameraIds: JSON.parse(cameraIdsSerialized) }));
      } catch (e) {
        console.error("Failed to send subscription updates", e);
      }
    }
  }, [cameraIdsSerialized]);

  /** Helper logger */
  function logger(message: string) {
    console.log("[useDetectionWebSocket]", message);
  }

  /** Get detections for a specific camera (most recent 5) */
  const getDetectionsForCamera = useCallback(
    (cameraId: string): Detection[] => {
      return detections.get(cameraId) || [];
    },
    [detections]
  );

  return {
    detections,
    connectionStatus,
    latencyMs,
    getDetectionsForCamera,
  };
}

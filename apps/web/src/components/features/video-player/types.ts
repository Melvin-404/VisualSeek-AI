/** Camera status */
export type CameraStatus = "online" | "offline" | "degraded";

/** Grid layout options */
export type GridLayout = "1x1" | "2x2" | "3x3" | "4x4";

/** Camera health metrics */
export interface CameraHealthMetrics {
  bitrate: number; // kbps
  fps: number;
  packetLoss: number; // percentage 0-100
  latencyMs: number;
  lastHeartbeat: string; // ISO timestamp
}

/** Camera definition */
export interface Camera {
  id: string;
  name: string;
  location: string;
  streamUrl: string;
  thumbnailUrl: string;
  status: CameraStatus;
  resolution: string;
  fps: number;
  health: CameraHealthMetrics;
}

/** Bounding box (normalized 0-1 coordinates) */
export interface BoundingBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Real-time detection event */
export interface Detection {
  id: string;
  cameraId: string;
  label: string;
  confidence: number; // 0-1
  bbox: BoundingBox;
  timestamp: string; // ISO timestamp
  color: string; // hex color
  bboxRaw?: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  };
  resolution?: {
    width: number;
    height: number;
  };
  track_id?: number | null;
  class_id?: number;
}

/** Timeline event types */
export type TimelineEventType = "motion" | "object" | "alert" | "bookmark";

/** Timeline event marker */
export interface TimelineEvent {
  id: string;
  cameraId: string;
  type: TimelineEventType;
  startTime: number; // seconds from start
  endTime: number;
  label: string;
}

/** Clip bookmark */
export interface Bookmark {
  id: string;
  cameraId: string;
  startTime: number;
  endTime: number;
  label: string;
  createdAt: string;
}

/** Grid layout config mapping */
export const GRID_CONFIGS: Record<GridLayout, { cols: number; rows: number; maxCameras: number }> = {
  "1x1": { cols: 1, rows: 1, maxCameras: 1 },
  "2x2": { cols: 2, rows: 2, maxCameras: 4 },
  "3x3": { cols: 3, rows: 3, maxCameras: 9 },
  "4x4": { cols: 4, rows: 4, maxCameras: 16 },
};

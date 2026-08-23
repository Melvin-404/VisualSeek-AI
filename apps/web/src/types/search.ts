export interface Detection {
  label: string;
  bbox: [number, number, number, number];
  attributes?: Record<string, string>;
}

export interface SearchResult {
  id: string;
  camera_id: string;
  timestamp_ms: number;
  frame_number: number;
  segment_id: string;
  object_classes: string[];
  score: number;
  raw_labels: {
    detections: Detection[];
    description: string;
    video_path: string;
  };
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  results?: SearchResult[];
  intent?: any;
  isStreaming?: boolean;
  timestamp: Date | string;
}

export interface SearchSnapshot {
  messages: ChatMessage[];
  visualMatches: SearchResult[];
  nluIntent: any | null;
  sessionId: string;
}

export interface SearchHistoryItem {
  id: string;
  query: string;
  timestamp: number;
  snapshot: SearchSnapshot | null;
}

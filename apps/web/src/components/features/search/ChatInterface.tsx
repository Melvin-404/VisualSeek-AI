"use client";

import React, { useState, useEffect, useRef } from "react";
import { useSession } from "next-auth/react";
import { env } from "@/env";
import {
  Send,
  Loader2,
  Download,
  AlertCircle,
  Clock,
  Sparkles,
  Bot,
  User,
  ArrowRight,
  Plus,
  Bell,
  Trash2,
  ChevronRight,
  Maximize2,
  X,
  Target,
  Cpu
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import VoiceInput from "./VoiceInput";
import SearchResults from "./SearchResults";

interface Detection {
  label: string;
  bbox: [number, number, number, number];
  attributes?: Record<string, string>;
}

interface SearchResult {
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

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  results?: SearchResult[];
  intent?: any;
  isStreaming?: boolean;
  timestamp: Date;
}

interface ChatInterfaceProps {
  onAnalyseFrame: (result: SearchResult) => void;
}

const MOCK_ANSWERS: Record<string, {
  text: string;
  results: SearchResult[];
  intent: any;
  suggestions: string[];
}> = {
  "show red cars in parking lot": {
    text: "I analyzed the video segments for Parking Lot A. I found 2 instances of red vehicles matching your description during the requested time window.",
    intent: {
      intent_type: "search",
      object_class: "vehicle",
      color: "red",
      camera_ids: ["cam-004"],
      time_range: { description: "Last 2 hours" },
      negations: [],
      rewritten_query: "find red vehicles/cars in parking lot feeds"
    },
    suggestions: [
      "Are any of them parked in Lot B?",
      "Show me their license plates",
      "Alert me when a red car enters"
    ],
    results: [
      {
        id: "res-001",
        camera_id: "Parking Lot A",
        timestamp_ms: 17811000,
        frame_number: 1420,
        segment_id: "seg-parking-001",
        object_classes: ["vehicle"],
        score: 0.94,
        raw_labels: {
          detections: [
            { label: "vehicle", bbox: [0.2, 0.4, 0.15, 0.2], attributes: { color: "red", type: "sedan" } }
          ],
          description: "Red sedan entering parking lot slot A4",
          video_path: "/uploads/video-parking.mp4"
        }
      },
      {
        id: "res-002",
        camera_id: "Parking Lot A",
        timestamp_ms: 28400000,
        frame_number: 2280,
        segment_id: "seg-parking-002",
        object_classes: ["vehicle"],
        score: 0.89,
        raw_labels: {
          detections: [
            { label: "vehicle", bbox: [0.55, 0.35, 0.18, 0.22], attributes: { color: "red", type: "suv" } }
          ],
          description: "Red SUV parked near the emergency exit pathway",
          video_path: "/uploads/video-parking.mp4"
        }
      }
    ]
  },
  "find people with backpacks in lobby": {
    text: "Reviewing the Front Lobby camera feeds. I detected 2 individuals carrying backpacks entering the building. Both detections occurred near the security checkpoint.",
    intent: {
      intent_type: "search",
      object_class: "person",
      attributes: { carrying: "backpack" },
      camera_ids: ["cam-003"],
      time_range: { description: "Today" },
      negations: [],
      rewritten_query: "detect persons carrying backpacks in lobby area"
    },
    suggestions: [
      "Did they exit the building?",
      "Show close-up of their faces",
      "Monitor the lobby for backpacks"
    ],
    results: [
      {
        id: "res-003",
        camera_id: "Front Lobby",
        timestamp_ms: 1450000,
        frame_number: 650,
        segment_id: "seg-lobby-001",
        object_classes: ["person"],
        score: 0.91,
        raw_labels: {
          detections: [
            { label: "person", bbox: [0.4, 0.25, 0.12, 0.45], attributes: { clothing: "dark jacket", carrying: "backpack" } }
          ],
          description: "Person in black jacket carrying a grey backpack walking past reception desk",
          video_path: "/uploads/video-lobby.mp4"
        }
      }
    ]
  },
  "yellow forklift near dock loading area": {
    text: "Scanning Warehouse B and Loading Dock cameras. I identified a yellow forklift operating near Loading Bay 2. The operator appears to be unloading shipments.",
    intent: {
      intent_type: "search",
      object_class: "vehicle",
      attributes: { type: "forklift", color: "yellow" },
      camera_ids: ["cam-007"],
      time_range: { description: "Last 24 hours" },
      negations: [],
      rewritten_query: "find yellow forklifts near loading dock zones"
    },
    suggestions: [
      "Is it obstructing the path?",
      "Show forklift activity over the last hour",
      "Alert if forklift is active after hours"
    ],
    results: [
      {
        id: "res-004",
        camera_id: "Warehouse B",
        timestamp_ms: 5400000,
        frame_number: 1800,
        segment_id: "seg-warehouse-001",
        object_classes: ["vehicle"],
        score: 0.95,
        raw_labels: {
          detections: [
            { label: "vehicle", bbox: [0.25, 0.45, 0.22, 0.3], attributes: { color: "yellow", subtype: "forklift" } }
          ],
          description: "Yellow forklift moving cargo crates near Bay 2 loading zone",
          video_path: "/uploads/video-parking.mp4"
        }
      }
    ]
  }
};

const DEFAULT_MOCK_ANSWER = {
  text: "I searched the active video feeds for your query. The AI engine processed the natural language constraints and generated a response based on simulated video detection indices.",
  intent: {
    intent_type: "search",
    object_class: "various",
    camera_ids: [],
    time_range: { description: "All active feeds" },
    negations: [],
    rewritten_query: "generic search translation"
  },
  suggestions: [
    "Show red cars in parking lot",
    "Find people with backpacks in lobby",
    "Yellow forklift near dock loading area"
  ],
  results: [
    {
      id: "res-default",
      camera_id: "Intersection (Day/Night)",
      timestamp_ms: 3200000,
      frame_number: 960,
      segment_id: "seg-intersection-001",
      object_classes: ["vehicle", "person"],
      score: 0.88,
      raw_labels: {
        detections: [
          { label: "vehicle", bbox: [0.15, 0.45, 0.25, 0.35] },
          { label: "person", bbox: [0.65, 0.5, 0.08, 0.25] }
        ],
        description: "Standard simulated camera detection event showing traffic flow",
        video_path: "/uploads/traffic-day-night.mp4"
      }
    }
  ]
};

export default function ChatInterface({ onAnalyseFrame }: ChatInterfaceProps) {
  const { data: session } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [sessionId] = useState(() => `sess_${Math.random().toString(36).substring(2, 11)}`);
  const [suggestions, setSuggestions] = useState<string[]>([
    "Show red cars in parking lot",
    "Find people with backpacks in lobby",
    "Yellow forklift near dock loading area",
  ]);
  const [isWsConnecting, setIsWsConnecting] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);
  const [alertSuccess, setAlertSuccess] = useState<string | null>(null);
  const [isMockMode, setIsMockMode] = useState(false);

  const [activeVideo, setActiveVideo] = useState<{ id: string; url: string; filename: string } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const currentChunkRef = useRef<string>("");

  // Initialize and maintain WebSocket connection
  useEffect(() => {
    connectWebSocket();
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const token = session?.accessToken || "mock-token";
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${env.NEXT_PUBLIC_API_URL}/api/v1/chat/upload-video?token=${token}`, {
        method: "POST",
        headers: {
          "X-Tenant-ID": "22222222-2222-2222-2222-222222222222",
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to upload video");
      }

      const data = await response.json();
      setActiveVideo({
        id: data.video_id,
        url: data.video_url,
        filename: data.filename,
      });
    } catch (err) {
      console.error("Error uploading video", err);
      alert("Failed to upload and process video. Make sure the backend server is running and CUDA is available.");
    } finally {
      setIsUploading(false);
    }
  };

  // Scroll to bottom of chat on message update
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const connectWebSocket = () => {
    setIsWsConnecting(true);
    setWsError(null);

    const apiUrl = env.NEXT_PUBLIC_API_URL;
    if (!apiUrl) {
      setIsMockMode(true);
      setWsError("API URL not configured. Running in local mock mode.");
      setIsWsConnecting(false);
      return;
    }

    const token = session?.accessToken || "mock-token";
    const sanitizedApiUrl = apiUrl.replace(/\/$/, "");
    const wsUrl = `${sanitizedApiUrl.replace("http", "ws")}/api/v1/chat/ws?token=${token}`;

    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected successfully");
      setIsWsConnecting(false);
      setIsMockMode(false);
    };

    ws.onmessage = (event) => {
      try {
        const data = jsonParse(event.data);
        if (!data) return;

        if (data.type === "search_results") {
          // 1. Update the last message or create an empty streaming message with the search results
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              return prev.map((msg, i) =>
                i === prev.length - 1
                  ? { ...msg, results: data.results, intent: data.intent }
                  : msg
              );
            } else {
              // Create an assistant message placeholder
              return [
                ...prev,
                {
                  id: `msg_${Math.random().toString(36).substring(2, 9)}`,
                  role: "assistant",
                  content: "Analyzing visual records...",
                  results: data.results,
                  intent: data.intent,
                  isStreaming: true,
                  timestamp: new Date(),
                },
              ];
            }
          });
        } else if (data.type === "content_chunk") {
          // 2. Stream chunked sentence data
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              const currentContent = lastMsg.isStreaming && lastMsg.content === "Analyzing visual records..."
                ? ""
                : lastMsg.content;
              return prev.map((msg, i) =>
                i === prev.length - 1
                  ? { ...msg, content: currentContent + data.text }
                  : msg
              );
            }
            return prev;
          });
        } else if (data.type === "suggestions") {
          // 3. Update suggested follow-up query pills
          setSuggestions(data.suggestions || []);
          // Stop streaming status on last message
          setMessages((prev) => {
            return prev.map((msg, i) =>
              i === prev.length - 1 ? { ...msg, isStreaming: false } : msg
            );
          });
        } else if (data.type === "error") {
          console.error("WS error returned", data.message);
          setMessages((prev) => {
            // Mark last message as failed and non-streaming
            return prev.map((msg, i) =>
              i === prev.length - 1
                ? { ...msg, content: `Error: ${data.message}`, isStreaming: false }
                : msg
            );
          });
        }
      } catch (err) {
        console.error("Error parsing WebSocket packet", err);
      }
    };

    ws.onclose = (event) => {
      console.log("WebSocket connection closed", event.code);
      setIsWsConnecting(false);
      if (event.code !== 1000 && event.code !== 1005) {
        setWsError("Connection to chat server lost. Running in local mock mode.");
        setIsMockMode(true);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket connection error", err);
      setWsError("Could not connect to chat server. Running in local mock mode.");
      setIsWsConnecting(false);
      setIsMockMode(true);
    };
  };

  const jsonParse = (str: string) => {
    try {
      return JSON.parse(str);
    } catch {
      return null;
    }
  };

  // Simulates WebSocket messages/responses locally inside the client when uvicorn is offline
  const sendMockMessage = (text: string) => {
    // 1. Add user message
    const userMsg: ChatMessage = {
      id: `msg_${Math.random().toString(36).substring(2, 9)}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setSuggestions([]); // Clear suggestions during streaming

    const normalizedText = text.toLowerCase().trim();
    const mockData = MOCK_ANSWERS[normalizedText] || {
      ...DEFAULT_MOCK_ANSWER,
      text: `I performed a natural language search for "${text}" across all camera feeds. No exact real-time matches were found, but here is a simulated reference from the camera feeds.`,
      intent: {
        ...DEFAULT_MOCK_ANSWER.intent,
        rewritten_query: `search for matches of: ${text}`
      }
    };

    // 2. Create assistant placeholder message
    const assistantMsgId = `msg_${Math.random().toString(36).substring(2, 9)}`;
    const placeholderMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "Analyzing visual records...",
      results: mockData.results,
      intent: mockData.intent,
      isStreaming: true,
      timestamp: new Date(),
    };

    setTimeout(() => {
      setMessages((prev) => [...prev, placeholderMsg]);

      const fullText = mockData.text;
      const words = fullText.split(" ");
      let currentWordIndex = 0;
      let currentContent = "";

      const streamInterval = setInterval(() => {
        if (currentWordIndex < words.length) {
          currentContent += (currentWordIndex === 0 ? "" : " ") + words[currentWordIndex];
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, content: currentContent }
                : msg
            )
          );
          currentWordIndex++;
        } else {
          clearInterval(streamInterval);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, isStreaming: false }
                : msg
            )
          );
          setSuggestions(mockData.suggestions);
        }
      }, 80);
    }, 600);
  };

  // Submits a message text to the server
  const sendMessage = (text: string) => {
    if (!text.trim()) return;

    if (isMockMode) {
      sendMockMessage(text);
      return;
    }

    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;

    // Add user message
    const userMsg: ChatMessage = {
      id: `msg_${Math.random().toString(36).substring(2, 9)}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setSuggestions([]); // Clear suggestions during streaming

    // Send JSON payload
    socketRef.current.send(
      JSON.stringify({
        text,
        session_id: sessionId,
        video_id: activeVideo ? activeVideo.id : undefined,
      })
    );
  };

  // Voice transcript callback
  const handleVoiceTranscript = (text: string) => {
    setInputText(text);
    sendMessage(text);
  };

  // Simulates alert creation based on current search intent
  const handleCreateAlert = (text: string) => {
    setAlertSuccess(`Alert rule registered: "Notify when ${text} is detected again"`);
    setTimeout(() => setAlertSuccess(null), 4000);
  };

  // Export conversation + results as a formatted PDF (client side generation)
  const handleExportPDF = () => {
    const printWindow = window.open("", "_blank");
    if (!printWindow) return;

    let contentHtml = `
      <html>
        <head>
          <title>VisionQuery Search Report</title>
          <style>
            body { font-family: 'Inter', sans-serif; background-color: #ffffff; color: #111111; padding: 30px; }
            h1 { color: #76b900; border-bottom: 2px solid #eaeaea; padding-bottom: 10px; font-size: 24px; }
            .meta { font-size: 11px; color: #666; margin-bottom: 30px; }
            .message { margin-bottom: 20px; padding: 15px; border-radius: 8px; }
            .user { background-color: #f7f7f7; border-left: 4px solid #999; }
            .assistant { background-color: #f0f7e6; border-left: 4px solid #76b900; }
            .role { font-weight: bold; font-size: 12px; margin-bottom: 5px; text-transform: uppercase; }
            .results-header { font-weight: bold; margin-top: 15px; font-size: 13px; color: #333; }
            .result-item { font-size: 12px; margin-left: 20px; margin-top: 5px; color: #555; }
          </style>
        </head>
        <body>
          <h1>VisionQuery Conversational Search Report</h1>
          <div class="meta">Generated on ${new Date().toLocaleString()} | Session ID: ${sessionId}</div>
    `;

    messages.forEach((msg) => {
      contentHtml += `
        <div class="message ${msg.role}">
          <div class="role">${msg.role === "user" ? "User Query" : "Assistant Response"}</div>
          <div class="content">${msg.content}</div>
      `;

      if (msg.results && msg.results.length > 0) {
        contentHtml += `<div class="results-header">Matching surveillance records (${msg.results.length}):</div>`;
        msg.results.forEach((r, idx) => {
          contentHtml += `
            <div class="result-item">
              [Match #${idx + 1}] Camera: ${r.camera_id} | Timestamp: ${Math.floor(r.timestamp_ms / 1000)}s | Relevance: ${(r.score * 100).toFixed(0)}%
              <br/>Description: "${r.raw_labels.description}"
            </div>
          `;
        });
      }
      contentHtml += `</div>`;
    });

    contentHtml += `
        </body>
      </html>
    `;

    printWindow.document.write(contentHtml);
    printWindow.document.close();
    printWindow.focus();
    // Trigger browser print to save as PDF
    printWindow.print();
  };

  // Clear session chat history
  const handleClearHistory = () => {
    setMessages([]);
    setSuggestions([
      "Show red cars in parking lot",
      "Find people with backpacks in lobby",
      "Yellow forklift near dock loading area",
    ]);
  };

  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);

  // Find active message (prioritizes assistant reply with results)
  const activeMsg = (() => {
    const active = messages.find((m) => m.id === activeMessageId);
    if (active) return active;
    // Fallback to the latest assistant message with results
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].results) {
        return messages[i];
      }
    }
    return messages[messages.length - 1];
  })();

  const handleSelectMessage = (msgId: string) => {
    const idx = messages.findIndex((m) => m.id === msgId);
    if (idx === -1) return;
    const msg = messages[idx];
    if (msg.role === "user") {
      // Find subsequent assistant message
      const nextMsg = messages[idx + 1];
      if (nextMsg && nextMsg.role === "assistant") {
        setActiveMessageId(nextMsg.id);
      } else {
        setActiveMessageId(msgId);
      }
    } else {
      setActiveMessageId(msgId);
    }
  };

  // Aggregate detected entities in search results
  const detectedEntities = React.useMemo(() => {
    if (!activeMsg?.results) return [];
    const counts: Record<string, number> = {};
    activeMsg.results.forEach((res) => {
      res.raw_labels.detections?.forEach((det) => {
        const lbl = det.label.toLowerCase();
        counts[lbl] = (counts[lbl] || 0) + 1;
      });
    });
    return Object.entries(counts).map(([label, count]) => ({ label, count }));
  }, [activeMsg]);

  // Aggregate confidence score stats
  const confidenceStats = React.useMemo(() => {
    if (!activeMsg?.results || activeMsg.results.length === 0) return { max: 0, avg: 0 };
    const scores = activeMsg.results.map((r) => r.score);
    const max = Math.max(...scores);
    const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
    return { max, avg };
  }, [activeMsg]);

  const formatVideoTime = (ms: number) => {
    const totalSecs = Math.floor(ms / 1000);
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="flex flex-col lg:flex-row gap-5 w-full h-[calc(100vh-140px)] min-h-[500px]">
      
      {/* COLUMN 1: LEFT - Conversation (32% width) */}
      <div className="w-full lg:w-[32%] shrink-0 flex flex-col border border-border/80 rounded-2xl overflow-hidden bg-card/25 backdrop-blur-sm relative h-full">
        {/* Chat Header */}
        <div className="px-4 py-3 border-b border-border bg-card/50 flex justify-between items-center shrink-0">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary animate-pulse" />
            <div>
              <span className="text-xs font-bold text-foreground flex items-center gap-1.5 uppercase tracking-wide">
                AI Investigator
                <span className="relative flex h-1.5 w-1.5 ml-1">
                  <span className={cn(
                    "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
                    isMockMode ? "bg-warning" : isWsConnecting ? "bg-blue-500" : "bg-success"
                  )} />
                  <span className={cn(
                    "relative inline-flex rounded-full h-1.5 w-1.5",
                    isMockMode ? "bg-warning" : isWsConnecting ? "bg-blue-500" : "bg-success"
                  )} />
                </span>
              </span>
              <span className="text-[9px] font-mono text-muted-foreground block">
                Session: {sessionId.slice(0, 12)}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {messages.length > 0 && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleExportPDF}
                  className="h-7 w-7 text-muted-foreground hover:text-foreground cursor-pointer"
                  title="PDF Report"
                >
                  <Download className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleClearHistory}
                  className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10 cursor-pointer"
                  title="Clear history"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </>
            )}
          </div>
        </div>



        {/* Alert Registration Notification toast */}
        {alertSuccess && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 bg-success text-black font-bold text-[10px] px-3 py-1.5 rounded-full shadow-lg z-50 flex items-center gap-1.5 animate-bounce uppercase tracking-wide">
            <Bell className="h-3.5 w-3.5" />
            <span>{alertSuccess}</span>
          </div>
        )}

        {/* Messages List Thread */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center max-w-[200px] mx-auto space-y-3">
              <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20">
                <Sparkles className="h-5 w-5 text-primary animate-pulse" />
              </div>
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider">Initiate Search</h3>
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                Describe target entities, colors, or locations. Results will populate center dashboard.
              </p>
            </div>
          ) : (
            messages.map((msg) => (
              <div 
                key={msg.id} 
                className={cn(
                  "rounded-xl p-3 border text-[11px] leading-relaxed transition-all duration-200 cursor-pointer",
                  msg.role === "user"
                    ? "bg-muted/30 border-border/80 text-foreground ml-6 hover:bg-muted/40"
                    : activeMsg?.id === msg.id
                    ? "bg-primary/[0.02] border-primary/30 text-foreground mr-6"
                    : "bg-card/40 border-border/60 text-foreground mr-6 hover:border-border"
                )}
                onClick={() => handleSelectMessage(msg.id)}
              >
                <div className="flex items-center gap-1.5 mb-1.5 border-b border-border/40 pb-1">
                  {msg.role === "user" ? (
                    <User className="h-3 w-3 text-accent" />
                  ) : (
                    <Bot className="h-3 w-3 text-primary" />
                  )}
                  <span className="font-mono text-[9px] uppercase font-bold tracking-wider text-muted-foreground">
                    {msg.role === "user" ? "USER QUERY" : "SYSTEM RESPONSE"}
                  </span>
                </div>
                <div className="whitespace-pre-wrap font-medium">{msg.content}</div>

                {/* Dynamic tag indicating query results */}
                {msg.results && msg.results.length > 0 && (
                  <div className="mt-2.5 flex items-center justify-between gap-2 bg-primary/5 border border-primary/20 rounded p-1.5">
                    <span className="font-mono text-[9px] font-bold text-primary uppercase tracking-wide">
                      {msg.results.length} Matches Found
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveMessageId(msg.id);
                      }}
                      className={cn(
                        "font-mono text-[8px] font-bold uppercase px-1.5 py-0.5 rounded cursor-pointer transition-colors",
                        activeMsg?.id === msg.id 
                          ? "bg-primary text-primary-foreground" 
                          : "bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {activeMsg?.id === msg.id ? "Inspecting" : "Inspect"}
                    </button>
                  </div>
                )}

                {msg.role === "assistant" && msg.isStreaming && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <Loader2 className="h-3 w-3 animate-spin text-primary" />
                    <span className="text-[9px] text-muted-foreground italic font-semibold">
                      Ingesting indices...
                    </span>
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Suggestion Pills */}
        {suggestions.length > 0 && (
          <div className="px-4 py-2.5 flex flex-wrap gap-1.5 text-[9px] border-t border-border/40 bg-card/15 shrink-0">
            {suggestions.map((sug, idx) => (
              <button
                key={idx}
                onClick={() => sendMessage(sug)}
                className="px-2 py-0.5 rounded bg-muted border border-border/80 hover:border-primary/40 text-muted-foreground hover:text-primary transition-all cursor-pointer font-medium"
              >
                {sug}
              </button>
            ))}
          </div>
        )}

        {/* Active video indicator */}
        {activeVideo && (
          <div className="px-4 py-2 bg-muted/50 border-t border-border flex items-center justify-between text-[10px] shrink-0 animate-fade-in">
            <div className="flex items-center gap-1.5 text-foreground font-semibold">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              <span>Active uploaded video: <span className="font-mono text-primary">{activeVideo.filename}</span></span>
            </div>
            <button
              onClick={() => setActiveVideo(null)}
              className="text-muted-foreground hover:text-destructive p-0.5 rounded cursor-pointer"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Input Controls Bar */}
        <div className="p-3 border-t border-border bg-card/60 flex items-center gap-2 shrink-0">
          <input
            type="file"
            accept="video/*"
            ref={fileInputRef}
            className="hidden"
            onChange={handleFileChange}
          />
          <Button
            variant="outline"
            size="icon"
            disabled={isUploading}
            onClick={() => fileInputRef.current?.click()}
            className="h-9 w-9 shrink-0 text-foreground cursor-pointer rounded-xl hover:border-primary/40 transition-all"
          >
            {isUploading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
          </Button>

          <VoiceInput
            onTranscript={handleVoiceTranscript}
            disabled={!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN)}
          />

          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage(inputText);
            }}
            className="flex-1 flex gap-1.5"
          >
            <input
              type="text"
              placeholder={
                isMockMode
                  ? "Chatting in local mock mode..."
                  : isWsConnecting
                  ? "Connecting to chat..."
                  : socketRef.current?.readyState !== WebSocket.OPEN
                  ? "Chat offline, reconnecting..."
                  : "Refine query: 'show red vehicles'..."
              }
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              disabled={!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN)}
              className="flex-1 h-9 bg-background border border-border hover:border-primary/40 focus:border-primary/80 focus:ring-1 focus:ring-primary rounded-xl px-3 text-[11px] font-semibold text-foreground transition-all placeholder:text-muted-foreground/60 disabled:opacity-50"
            />
            <Button
              type="submit"
              disabled={!inputText.trim() || (!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN))}
              size="icon"
              className="h-9 w-9 shrink-0 rounded-xl bg-primary hover:bg-primary/95 text-primary-foreground font-bold shadow-md cursor-pointer flex items-center justify-center"
              title="Send message"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </form>
        </div>
      </div>

      {/* COLUMN 2: CENTER - Results (Flexible width) */}
      <div className="w-full lg:flex-1 min-w-0 flex flex-col border border-border/80 rounded-2xl overflow-hidden bg-card/10 backdrop-blur-sm h-full">
        {/* Center Header */}
        <div className="px-5 py-3 border-b border-border bg-card/45 flex justify-between items-center shrink-0">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-accent animate-pulse" />
            <span className="font-mono text-xs font-bold text-foreground uppercase tracking-wider">
              Visual Search Index Matches
            </span>
          </div>
          {activeMsg?.results && activeMsg.results.length > 0 && (
            <Badge className="bg-accent/15 border-accent/30 text-accent text-[9px] font-bold py-0.5 px-2">
              {activeMsg.results.length} Matches
            </Badge>
          )}
        </div>

        {/* Results Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeMsg?.results && activeMsg.results.length > 0 ? (
            <div className="space-y-4">
              <SearchResults
                results={activeMsg.results}
                activeQuery={activeMsg.content}
                onAnalyse={onAnalyseFrame}
              />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center max-w-sm mx-auto space-y-4">
              <div className="h-12 w-12 rounded-2xl bg-accent/5 flex items-center justify-center border border-accent/10 cyber-grid relative">
                <span className="h-2 w-2 rounded-full bg-accent animate-ping absolute" />
                <span className="h-1.5 w-1.5 rounded-full bg-accent absolute" />
              </div>
              <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-foreground">Awaiting Query Execution</h3>
              <p className="text-[10px] text-muted-foreground/80 leading-relaxed">
                Submit a text query in the visual assistant panel to search indexing databases. Matching surveillance frames will display here.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* COLUMN 3: RIGHT - AI Reasoning (25% width) */}
      <div className="w-full lg:w-[25%] shrink-0 flex flex-col border border-border/80 rounded-2xl overflow-hidden bg-card/25 backdrop-blur-sm h-full">
        {/* Right Header */}
        <div className="px-5 py-3 border-b border-border bg-card/45 flex items-center gap-2 shrink-0">
          <Sparkles className="h-4 w-4 text-primary animate-pulse" />
          <span className="font-mono text-xs font-bold text-foreground uppercase tracking-wider">
            NLU Intent Deconstruction
          </span>
        </div>

        {/* Right Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {activeMsg?.intent ? (
            <div className="space-y-5">
              {/* Query Breakdown */}
              <div className="space-y-2.5">
                <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider">Query Scope</span>
                <div className="space-y-2 text-[10px]">
                  <div className="flex justify-between items-center gap-2 border-b border-border/40 pb-1.5">
                    <span className="text-muted-foreground">Intent Type</span>
                    <Badge variant="outline" className="text-[8px] border-primary/20 text-primary uppercase font-bold py-0">
                      {activeMsg.intent.intent_type || "N/A"}
                    </Badge>
                  </div>

                  <div className="flex justify-between items-center gap-2 border-b border-border/40 pb-1.5">
                    <span className="text-muted-foreground">Class Target</span>
                    <span className="font-mono bg-muted border border-border px-1.5 py-0.5 rounded text-[9px] text-foreground font-bold">
                      {activeMsg.intent.object_class || "N/A"}
                    </span>
                  </div>

                  <div className="flex justify-between items-center gap-2 border-b border-border/40 pb-1.5">
                    <span className="text-muted-foreground">Attribute Filter</span>
                    <span className="font-mono text-[9px] text-foreground font-bold">
                      {activeMsg.intent.color || activeMsg.intent.attributes?.clothing || activeMsg.intent.attributes?.carrying || "None"}
                    </span>
                  </div>

                  <div className="flex justify-between items-start gap-2 border-b border-border/40 pb-1.5">
                    <span className="text-muted-foreground">Locked Cameras</span>
                    <div className="flex flex-wrap gap-1 justify-end max-w-[120px]">
                      {activeMsg.intent.camera_ids && activeMsg.intent.camera_ids.length > 0 ? (
                        activeMsg.intent.camera_ids.map((cid: string) => (
                          <Badge key={cid} variant="secondary" className="text-[8px] px-1 py-0 border-border">
                            {cid.replace("cam-", "")}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-muted-foreground">All Feeds</span>
                      )}
                    </div>
                  </div>

                  <div className="flex justify-between items-start gap-2 border-b border-border/40 pb-1.5">
                    <span className="text-muted-foreground">Time Range</span>
                    <span className="text-right font-medium text-foreground">
                      {activeMsg.intent.time_range?.description || "All indices"}
                    </span>
                  </div>

                  <div className="flex flex-col gap-1 pt-1">
                    <span className="text-[8px] text-muted-foreground uppercase font-bold tracking-wider">
                      Translated Prompt Expansion
                    </span>
                    <div className="bg-background/95 border border-border rounded-lg p-2 font-mono text-[8px] text-foreground leading-relaxed break-all">
                      {activeMsg.intent.rewritten_query || activeMsg.intent.raw_query || "N/A"}
                    </div>
                  </div>
                </div>
              </div>

              {/* Detected Entities */}
              {detectedEntities.length > 0 && (
                <div className="space-y-2 border-t border-border/30 pt-4">
                  <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider">Detected Entities</span>
                  <div className="grid grid-cols-2 gap-2">
                    {detectedEntities.map((ent) => (
                      <div key={ent.label} className="bg-background/55 border border-border/40 rounded-lg p-2 flex items-center justify-between gap-2">
                        <span className="font-mono text-[9px] font-bold text-foreground capitalize truncate">{ent.label}</span>
                        <Badge variant="secondary" className="text-[8px] font-bold py-0 px-1 bg-accent/10 border-accent/20 text-accent">
                          {ent.count}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Confidence Score Indicators */}
              {activeMsg.results && activeMsg.results.length > 0 && (
                <div className="space-y-3 border-t border-border/30 pt-4">
                  <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider">AI Accuracy Metrics</span>
                  <div className="space-y-2 text-[10px]">
                    <div className="space-y-1">
                      <div className="flex justify-between font-semibold">
                        <span className="text-muted-foreground">Max Similarity Score</span>
                        <span className="text-primary font-bold">{(confidenceStats.max * 100).toFixed(0)}%</span>
                      </div>
                      <div className="h-1.5 w-full bg-border/40 rounded-full overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${confidenceStats.max * 100}%` }} />
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between font-semibold">
                        <span className="text-muted-foreground">Average Score</span>
                        <span className="text-accent font-bold">{(confidenceStats.avg * 100).toFixed(0)}%</span>
                      </div>
                      <div className="h-1.5 w-full bg-border/40 rounded-full overflow-hidden">
                        <div className="h-full bg-accent rounded-full" style={{ width: `${confidenceStats.avg * 100}%` }} />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Timeline Matches */}
              {activeMsg.results && activeMsg.results.length > 0 && (
                <div className="space-y-2 border-t border-border/30 pt-4">
                  <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider flex items-center gap-1">
                    <Clock className="h-3 w-3 text-accent" />
                    Timeline Matches
                  </span>
                  <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
                    {activeMsg.results.map((res) => (
                      <div 
                        key={res.id} 
                        onClick={() => onAnalyseFrame(res)}
                        className="flex items-center justify-between gap-2 border border-border/40 hover:border-accent/40 bg-background/40 hover:bg-accent/[0.02] p-2 rounded-lg cursor-pointer transition-all"
                      >
                        <div className="flex flex-col min-w-0">
                          <span className="text-[9px] font-bold text-foreground truncate">{res.camera_id}</span>
                          <span className="text-[8px] text-muted-foreground/60 font-mono">Frame #{res.frame_number}</span>
                        </div>
                        <Badge variant="outline" className="text-[8px] font-mono border-accent/25 text-accent font-bold py-0.5 px-1.5 shrink-0 bg-accent/[0.01]">
                          {formatVideoTime(res.timestamp_ms)}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12 text-xs text-muted-foreground flex flex-col items-center justify-center gap-2 h-full">
              <Clock className="h-6 w-6 text-muted-foreground/30" />
              <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground/50">Awaiting NLU extraction</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

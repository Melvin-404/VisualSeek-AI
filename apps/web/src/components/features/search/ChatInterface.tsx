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
  X
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-[75vh]">
      {/* Left Columns: Chat Threads & Input */}
      <div className="lg:col-span-3 flex flex-col glass rounded-2xl border border-border overflow-hidden h-[75vh] bg-card/40 relative">
        
        {/* Chat Header */}
        <div className="px-5 py-4 border-b border-border bg-card/60 flex justify-between items-center z-10">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <div>
              <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                VisionQuery AI Assistant
                <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
              </span>
              <span className="text-[10px] text-muted-foreground block">
                Session: {sessionId}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleExportPDF}
                  className="h-8 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <Download className="h-3.5 w-3.5 mr-1" />
                  PDF Report
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleClearHistory}
                  className="h-8 text-xs text-destructive hover:text-destructive hover:bg-destructive/10 cursor-pointer"
                >
                  <Trash2 className="h-3.5 w-3.5 mr-1" />
                  Clear
                </Button>
              </>
            )}
          </div>
        </div>

        {/* WebSocket Connection Error warnings */}
        {wsError && (
          <div className="bg-destructive/10 border-b border-destructive/20 px-4 py-2 flex items-center gap-2 text-xs text-destructive font-semibold">
            <AlertCircle className="h-4 w-4" />
            <span>{wsError}</span>
          </div>
        )}

        {/* Alert Registration Notification toast */}
        {alertSuccess && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 bg-success/90 backdrop-blur text-black font-bold text-xs px-4 py-2.5 rounded-full shadow-lg z-50 flex items-center gap-2 animate-bounce">
            <Bell className="h-4 w-4" />
            <span>{alertSuccess}</span>
          </div>
        )}

        {/* Messages List Thread */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center max-w-md mx-auto space-y-3">
              <div className="h-12 w-12 rounded-2xl bg-primary/10 flex items-center justify-center shadow-[0_0_15px_rgba(118,185,0,0.15)] border border-primary/20">
                <Sparkles className="h-6 w-6 text-primary animate-pulse" />
              </div>
              <h3 className="text-sm font-bold text-foreground">Initiate surveillance search thread</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                VisionQuery parses multi-turn queries. Describe what you're looking for, then refine the search, highlight detections, or create alerts.
              </p>
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} className="space-y-4">
                {/* Chat Bubble bubble */}
                <div
                  className={`flex gap-3 max-w-[85%] ${
                    msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                  }`}
                >
                  {/* Icon */}
                  <div
                    className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 border ${
                      msg.role === "user"
                        ? "bg-muted border-border text-foreground"
                        : "bg-primary/15 border-primary/20 text-primary"
                    }`}
                  >
                    {msg.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </div>

                  {/* Body Bubble */}
                  <div
                    className={`rounded-2xl p-4 text-xs leading-relaxed border shadow-sm ${
                      msg.role === "user"
                        ? "bg-muted/70 border-border text-foreground"
                        : "bg-card border-border text-foreground"
                    }`}
                  >
                    {/* Render Text Content */}
                    <div className="whitespace-pre-wrap font-medium">{msg.content}</div>

                    {/* Natural Language Alert Creation Pill */}
                    {msg.role === "user" && (
                      <div className="mt-3 flex justify-end">
                        <button
                          onClick={() => handleCreateAlert(msg.content)}
                          className="text-[9px] font-bold text-primary hover:underline flex items-center gap-1 bg-primary/5 border border-primary/20 px-2 py-0.5 rounded-full cursor-pointer uppercase tracking-wider"
                        >
                          <Bell className="h-2.5 w-2.5" />
                          Monitor Query Pattern
                        </button>
                      </div>
                    )}

                    {/* Loader during streaming */}
                    {msg.role === "assistant" && msg.isStreaming && (
                      <div className="flex items-center gap-1.5 mt-2">
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                        <span className="text-[10px] text-muted-foreground italic font-semibold">
                          Ingesting video feeds...
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Search Results Grid for this turn */}
                {msg.results && msg.results.length > 0 && (
                  <div className="pl-11 pr-4">
                    <div className="bg-card/30 border border-border rounded-xl p-4 space-y-3 shadow-inner">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold flex items-center gap-1">
                        <Maximize2 className="h-3 w-3 text-primary" />
                        Matched Video Indexes ({msg.results.length})
                      </div>
                      <SearchResults
                        results={msg.results}
                        activeQuery={msg.content}
                        onAnalyse={onAnalyseFrame}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Suggestion Pills */}
        {suggestions.length > 0 && (
          <div className="px-5 py-2 flex flex-wrap gap-2 text-[10px] border-t border-border/40 bg-card/10 z-10">
            <span className="text-muted-foreground flex items-center gap-0.5 font-bold">
              Follow-up: <ChevronRight className="h-3 w-3 text-primary" />
            </span>
            {suggestions.map((sug, idx) => (
              <button
                key={idx}
                onClick={() => sendMessage(sug)}
                className="px-2.5 py-1 rounded-full bg-muted border border-border hover:border-primary/40 text-muted-foreground hover:text-primary transition-all cursor-pointer font-medium"
              >
                {sug}
              </button>
            ))}
          </div>
        )}

        {/* Active video indicator */}
        {activeVideo && (
          <div className="px-5 py-2.5 bg-muted/40 border-t border-border flex items-center justify-between text-xs z-10 animate-fade-in">
            <div className="flex items-center gap-2 text-foreground font-semibold">
              <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
              <span>Active uploaded video: <span className="font-mono text-primary">{activeVideo.filename}</span></span>
            </div>
            <button
              onClick={() => setActiveVideo(null)}
              className="text-muted-foreground hover:text-destructive p-1 rounded hover:bg-muted cursor-pointer transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Input Controls Bar */}
        <div className="p-4 border-t border-border bg-card/50 flex items-center gap-2 z-10">
          {/* File Upload Input */}
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
            className="h-10 w-10 shrink-0 text-foreground cursor-pointer rounded-xl hover:border-primary/40 transition-all"
          >
            {isUploading ? (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
          </Button>

          {/* Voice input */}
          <VoiceInput
            onTranscript={handleVoiceTranscript}
            disabled={!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN)}
          />

          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage(inputText);
            }}
            className="flex-1 flex gap-2"
          >
            <input
              type="text"
              placeholder={
                isMockMode
                  ? "Chatting in local mock mode (API offline)..."
                  : isWsConnecting
                  ? "Connecting to chat..."
                  : socketRef.current?.readyState !== WebSocket.OPEN
                  ? "Chat offline, reconnecting..."
                  : "Refine query: 'now show only white ones', 'alert me if this happens'..."
              }
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              disabled={!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN)}
              className="flex-1 h-10 bg-background border border-border hover:border-primary/40 focus:border-primary/80 focus:ring-1 focus:ring-primary rounded-xl px-4 text-xs font-semibold text-foreground transition-all placeholder:text-muted-foreground disabled:opacity-50"
            />
            <Button
              type="submit"
              disabled={!inputText.trim() || (!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN))}
              className="h-10 px-4 rounded-xl bg-primary hover:bg-primary/95 text-primary-foreground font-bold shadow-md cursor-pointer flex items-center gap-1.5"
            >
              <Send className="h-3.5 w-3.5" />
              Send
            </Button>
          </form>
        </div>
      </div>

      {/* Right Column: NLU State Drawer */}
      <div className="space-y-6">
        <div className="glass rounded-xl p-5 border border-border shadow-lg space-y-4 h-[75vh] overflow-y-auto bg-card/20">
          <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 border-b border-border pb-3">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            NLU Intent Deconstruction
          </h2>

          {messages.length > 0 && messages[messages.length - 1]?.intent ? (
            <div className="space-y-4">
              {/* Intent Info list */}
              {(() => {
                const activeIntent = messages[messages.length - 1].intent;
                return (
                  <div className="space-y-3 text-xs">
                    <div className="flex justify-between items-center gap-2 border-b border-border/40 pb-2">
                      <span className="text-muted-foreground">Intent Type</span>
                      <Badge variant="outline" className="text-[9px] border-primary/20 text-primary uppercase font-bold py-0">
                        {activeIntent.intent_type || "N/A"}
                      </Badge>
                    </div>

                    <div className="flex justify-between items-center gap-2 border-b border-border/40 pb-2">
                      <span className="text-muted-foreground">Class Target</span>
                      <span className="font-mono bg-muted px-1.5 py-0.5 rounded text-[10px] text-foreground font-bold">
                        {activeIntent.object_class || "N/A"}
                      </span>
                    </div>

                    <div className="flex justify-between items-center gap-2 border-b border-border/40 pb-2">
                      <span className="text-muted-foreground">Color Hex</span>
                      {activeIntent.color ? (
                        <span className="flex items-center gap-1 font-semibold text-foreground">
                          <span
                            style={{
                              backgroundColor:
                                activeIntent.color === "white"
                                  ? "#ffffff"
                                  : activeIntent.color === "black"
                                  ? "#111111"
                                  : activeIntent.color === "red"
                                  ? "#ef4444"
                                  : activeIntent.color === "blue"
                                  ? "#3b82f6"
                                  : activeIntent.color === "yellow"
                                  ? "#eab308"
                                  : "#76b900",
                            }}
                            className="h-2.5 w-2.5 rounded-full border border-border"
                          />
                          {activeIntent.color}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">None</span>
                      )}
                    </div>

                    <div className="flex justify-between items-start gap-2 border-b border-border/40 pb-2">
                      <span className="text-muted-foreground">Locked Cameras</span>
                      <div className="flex flex-wrap gap-1 justify-end max-w-[150px]">
                        {activeIntent.camera_ids && activeIntent.camera_ids.length > 0 ? (
                          activeIntent.camera_ids.map((cid: string) => (
                            <Badge key={cid} variant="secondary" className="text-[9px] px-1.5 py-0 border-border">
                              {cid.replace("cam-", "")}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-muted-foreground">All Feeds</span>
                        )}
                      </div>
                    </div>

                    <div className="flex justify-between items-start gap-2 border-b border-border/40 pb-2">
                      <span className="text-muted-foreground">Time Scope</span>
                      <span className="text-right font-medium text-foreground">
                        {activeIntent.time_range?.description || "All indices"}
                      </span>
                    </div>

                    <div className="flex justify-between items-start gap-2 border-b border-border/40 pb-2">
                      <span className="text-muted-foreground text-destructive">Exclusions</span>
                      <span className="text-right font-mono text-destructive font-bold text-[10px]">
                        {activeIntent.negations && activeIntent.negations.length > 0
                          ? activeIntent.negations.join(", ")
                          : "None"}
                      </span>
                    </div>

                    <div className="flex flex-col gap-1.5 pt-1">
                      <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">
                        Prompt Expansion
                      </span>
                      <div className="bg-background border border-border rounded-lg p-2.5 font-mono text-[9px] text-foreground leading-relaxed break-all">
                        {activeIntent.rewritten_query || activeIntent.raw_query}
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          ) : (
            <div className="text-center py-12 text-xs text-muted-foreground flex flex-col items-center justify-center gap-2">
              <Clock className="h-6 w-6 text-muted-foreground/45" />
              <span>Pipeline outputs will display as you chat.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

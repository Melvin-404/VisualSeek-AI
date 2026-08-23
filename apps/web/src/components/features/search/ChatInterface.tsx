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
  Cpu,
  CheckCircle2,
  AlertTriangle
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import VoiceInput from "./VoiceInput";
import SearchResults from "./SearchResults";
import { useSearchHistoryContext } from "@/contexts/SearchHistoryContext";
import { formatTimestamp } from "@/utils/formatTimestamp";
import { Detection, SearchResult, ChatMessage, SearchHistoryItem } from "@/types/search";

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
  const { addSearch, selectedHistoryItem, setSelectedHistoryItem } = useSearchHistoryContext();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [sessionId, setSessionId] = useState(() => `sess_${Math.random().toString(36).substring(2, 11)}`);
  const [lastQuery, setLastQuery] = useState<string | null>(null);
  const [restoredLabel, setRestoredLabel] = useState<string | null>(null);
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
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "processing" | "ready" | "error">("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const [searchStage, setSearchStage] = useState(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const searchStageTimerRef = useRef<any>(null);

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

  // Run query from URL parameter if present on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const queryParam = params.get("q");
      if (queryParam) {
        const timer = setTimeout(() => {
          sendMessage(queryParam);
        }, 1200);
        return () => clearTimeout(timer);
      }
    }
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadStatus("uploading");
    setUploadProgress(0);

    const token = session?.accessToken || "mock-token";
    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${env.NEXT_PUBLIC_API_URL}/api/v1/chat/upload-video?token=${token}`, true);
    xhr.setRequestHeader("X-Tenant-ID", "22222222-2222-2222-2222-222222222222");

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
        if (percent === 100) {
          setUploadStatus("processing");
        }
      }
    };

    xhr.onload = () => {
      setIsUploading(false);
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          setActiveVideo({
            id: data.video_id,
            url: data.video_url,
            filename: data.filename,
          });
          setUploadStatus("ready");
          // Do NOT auto-dismiss — keep the video card visible
        } catch (err) {
          console.error("Error parsing upload response", err);
          setUploadStatus("error");
          alert("Failed to parse video upload response.");
        }
      } else {
        console.error("Upload failed with status", xhr.status);
        setUploadStatus("error");
        alert("Failed to upload and process video. Make sure the backend server is running and CUDA is available.");
      }
    };

    xhr.onerror = () => {
      console.error("Upload network error");
      setIsUploading(false);
      setUploadStatus("error");
      alert("Network error during upload.");
    };

    xhr.send(formData);
  };

  // Scroll to bottom of chat on message update
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Cycle through search stage labels while a real search is in-flight
  const SEARCH_STAGES = [
    "Analyzing query...",
    "Finding candidate frames...",
    "Analyzing video moments...",
    "Ranking results...",
    "Preparing results...",
  ];

  useEffect(() => {
    if (isSearching) {
      searchStageTimerRef.current = setInterval(() => {
        setSearchStage((s) => (s + 1) % SEARCH_STAGES.length);
      }, 1800);
    } else {
      clearInterval(searchStageTimerRef.current);
    }
    return () => clearInterval(searchStageTimerRef.current);
  }, [isSearching]);

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
          setIsSearching(false);
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
          setIsSearching(false);
          // Stop streaming status on last message
          setMessages((prev) => {

            return prev.map((msg, i) =>
              i === prev.length - 1 ? { ...msg, isStreaming: false } : msg
            );
          });
        } else if (data.type === "error") {
          console.error("WS error returned", data.message);
          setIsSearching(false);
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
    setIsSearching(true);
    setSearchStage(0);

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
          setIsSearching(false);
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
    if (isSearching) return; // prevent duplicate submissions

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
    setIsSearching(true);
    setSearchStage(0);

    // Send JSON payload
    socketRef.current.send(
      JSON.stringify({
        text,
        session_id: sessionId,
        video_id: activeVideo ? activeVideo.id : undefined,
      })
    );
  };

  const restoredTimerRef = useRef<any>(null);

  const handleHistorySelect = (item: SearchHistoryItem) => {
    if (!item.snapshot) {
      setInputText(item.query);
      sendMessage(item.query);
      return;
    }

    setInputText("");

    const restoredMessages = item.snapshot.messages.map((msg: any) => ({
      ...msg,
      timestamp: new Date(msg.timestamp),
    }));

    setMessages(restoredMessages);

    const assistantMsg = [...restoredMessages].reverse().find(
      (msg) => msg.role === "assistant" && msg.results !== undefined
    );
    if (assistantMsg) {
      setActiveMessageId(assistantMsg.id);
    } else {
      setActiveMessageId(null);
    }

    setSessionId(item.snapshot.sessionId);

    if (restoredTimerRef.current) {
      clearTimeout(restoredTimerRef.current);
    }
    setRestoredLabel(`Restored · ${formatTimestamp(item.timestamp)}`);
    restoredTimerRef.current = setTimeout(() => {
      setRestoredLabel(null);
    }, 3000);
  };

  useEffect(() => {
    if (selectedHistoryItem) {
      handleHistorySelect(selectedHistoryItem);
      setSelectedHistoryItem(null);
    }
  }, [selectedHistoryItem, setSelectedHistoryItem]);

  useEffect(() => {
    if (!lastQuery) return;

    let userMsgIdx = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (
        messages[i].role === "user" &&
        messages[i].content.toLowerCase() === lastQuery.toLowerCase()
      ) {
        userMsgIdx = i;
        break;
      }
    }

    if (userMsgIdx !== -1) {
      const assistantMsg = messages[userMsgIdx + 1];
      if (
        assistantMsg &&
        assistantMsg.role === "assistant" &&
        assistantMsg.results !== undefined &&
        !assistantMsg.isStreaming
      ) {
        addSearch(lastQuery, {
          messages: messages.slice(0, userMsgIdx + 2),
          visualMatches: assistantMsg.results || [],
          nluIntent: assistantMsg.intent || null,
          sessionId,
        });
        setLastQuery(null);
      }
    }
  }, [messages, lastQuery, sessionId, addSearch]);

  // Voice transcript callback
  const handleVoiceTranscript = (text: string) => {
    setInputText(text);
    sendMessage(text);
    setLastQuery(text);
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
          <title>VisualSeek AI Search Report</title>
          <style>
            body { font-family: 'Inter', sans-serif; background-color: #ffffff; color: #111111; padding: 30px; }
            h1 { color: #38bdf8; border-bottom: 2px solid #eaeaea; padding-bottom: 10px; font-size: 24px; }
            .meta { font-size: 11px; color: #666; margin-bottom: 30px; }
            .message { margin-bottom: 20px; padding: 15px; border-radius: 8px; }
            .user { background-color: #f7f7f7; border-left: 4px solid #999; }
            .assistant { background-color: #f0f9ff; border-left: 4px solid #38bdf8; }
            .role { font-weight: bold; font-size: 12px; margin-bottom: 5px; text-transform: uppercase; }
            .results-header { font-weight: bold; margin-top: 15px; font-size: 13px; color: #333; }
            .result-item { font-size: 12px; margin-left: 20px; margin-top: 5px; color: #555; }
          </style>
        </head>
        <body>
          <h1>VisualSeek AI Conversational Search Report</h1>
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
    <div className="flex flex-col gap-4 w-full h-[calc(100vh-140px)] min-h-[500px] max-w-5xl mx-auto">

      {/* ═══ PERSISTENT UPLOAD / VIDEO STATUS PANEL ═══ */}
      {(uploadStatus !== "idle" || activeVideo) && (
        <div className="w-full shrink-0 rounded-xl border border-border/70 bg-card/30 overflow-hidden">
          {/* Upload progress row — visible while uploading/processing */}
          {uploadStatus !== "idle" && uploadStatus !== "ready" && (
            <div className="px-4 py-2.5 bg-card/50 border-b border-border/50 flex items-center justify-between gap-4 text-xs font-mono">
              <div className="flex items-center gap-2.5">
                {uploadStatus === "uploading" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />}
                {uploadStatus === "processing" && (
                  <span className="relative flex h-3 w-3 shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-60" />
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-primary" />
                  </span>
                )}
                {uploadStatus === "error" && <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />}
                <span className={`font-bold uppercase tracking-widest text-[10px] ${
                  uploadStatus === "uploading" ? "text-foreground"
                  : uploadStatus === "processing" ? "text-primary"
                  : "text-destructive"
                }`}>
                  {uploadStatus === "uploading" && "Uploading video..."}
                  {uploadStatus === "processing" && "Processing video · Analyzing frames · Indexing..."}
                  {uploadStatus === "error" && "Upload Failed"}
                </span>
              </div>
              {uploadStatus === "uploading" && (
                <div className="flex items-center gap-2.5 w-40 shrink-0">
                  <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all duration-300 ease-out"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                  <span className="text-primary font-bold w-8 text-right">{uploadProgress}%</span>
                </div>
              )}
            </div>
          )}

          {/* Persistent video card — shown once upload completes */}
          {activeVideo && (
            <div className="px-4 py-3 flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-primary/10 border border-primary/25 flex items-center justify-center shrink-0">
                <Cpu className="h-4 w-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-0.5">Uploaded Video</div>
                <p className="text-xs font-semibold text-foreground truncate">{activeVideo.filename}</p>
              </div>
              <div className="shrink-0">
                {uploadStatus === "ready" && (
                  <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-400/10 border border-emerald-400/25 rounded-full px-2.5 py-1">
                    <CheckCircle2 className="h-3 w-3" />
                    Ready for Search
                  </span>
                )}
                {uploadStatus === "processing" && (
                  <span className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-primary bg-primary/10 border border-primary/25 rounded-full px-2.5 py-1">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Processing...
                  </span>
                )}
              </div>
              <button
                className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded cursor-pointer"
                onClick={() => { setActiveVideo(null); setUploadStatus("idle"); }}
                title="Remove video"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* ═══ HEADER: Search Input ═══ */}
      <div className="w-full flex flex-col border border-border/80 rounded-2xl overflow-hidden bg-card/25 backdrop-blur-sm shrink-0">
        <div className="p-4 bg-card/60 flex items-center gap-3">
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
            title="Upload video"
          >
            {isUploading ? (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            ) : (
              <Plus className="h-4 w-4" />
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
              setLastQuery(inputText);
            }}
            className="flex-1 flex gap-2"
          >
            <input
              type="text"
              placeholder={
                isSearching
                  ? SEARCH_STAGES[searchStage]
                  : isMockMode
                  ? "Chatting in local mock mode..."
                  : isWsConnecting
                  ? "Connecting to server..."
                  : socketRef.current?.readyState !== WebSocket.OPEN
                  ? "Server offline, reconnecting..."
                  : "Search visual index: 'yellow car reversing'..."
              }
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              disabled={isSearching || (!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN))}
              className="flex-1 h-10 bg-background border border-border hover:border-primary/40 focus:border-primary/80 focus:ring-1 focus:ring-primary rounded-xl px-4 text-sm font-semibold text-foreground transition-all placeholder:text-muted-foreground/60 disabled:opacity-60"
            />
            <Button
              type="submit"
              disabled={isSearching || !inputText.trim() || (!isMockMode && (isWsConnecting || socketRef.current?.readyState !== WebSocket.OPEN))}
              size="icon"
              className="h-10 w-10 shrink-0 rounded-xl bg-primary hover:bg-primary/95 text-primary-foreground font-bold shadow-md cursor-pointer flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
              title={isSearching ? "Searching..." : "Search"}
            >
              {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
        </div>

        {/* QUERY + INTERPRETED AS Panel */}
        {activeMsg?.intent && (
          <div className="border-t border-border/50 bg-card/40">
            <div className="px-5 py-3 flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-0.5">Query</div>
                <p className="text-xs text-foreground font-semibold truncate">
                  &ldquo;{activeMsg.content}&rdquo;
                </p>
              </div>

              <div className="hidden sm:block h-8 w-px bg-border/50" />

              <div className="flex flex-col gap-1">
                <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Interpreted As</div>
                <div className="flex flex-wrap gap-1.5">
                  {activeMsg.intent.object_class && (
                    <Badge variant="outline" className="text-[10px] border-primary/30 text-primary bg-primary/5 px-2">
                      Object: {[activeMsg.intent.color, activeMsg.intent.object_class].filter(Boolean).join(" ")}
                    </Badge>
                  )}
                  {activeMsg.intent.action && (
                    <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-400 bg-amber-500/5 px-2">
                      Action: {activeMsg.intent.action}
                    </Badge>
                  )}
                  {activeMsg.intent.camera_ids && activeMsg.intent.camera_ids.length > 0 && (
                    <Badge variant="outline" className="text-[10px] border-border text-muted-foreground px-2">
                      Camera: Filtered
                    </Badge>
                  )}
                  {!activeMsg.intent.object_class && !activeMsg.intent.action && (
                    <Badge variant="outline" className="text-[10px] border-border text-muted-foreground px-2">
                      General query
                    </Badge>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ═══ BODY: Search Processing OR Results ═══ */}
      <div className="w-full flex-1 flex flex-col min-h-0">
        {isSearching ? (
          /* Search Processing Overlay — tied to real API request */
          <div className="flex flex-col items-center justify-center h-full gap-6">
            <div className="relative">
              <div className="h-16 w-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-[0_0_20px_rgba(56,189,248,0.15)]">
                <Loader2 className="h-7 w-7 text-primary animate-spin" />
              </div>
            </div>
            <div className="text-center space-y-2">
              <h3 className="font-mono text-sm font-bold uppercase tracking-widest text-foreground">
                Searching Visual Index
              </h3>
              <p className="text-xs text-primary font-semibold tracking-wide animate-pulse">
                {SEARCH_STAGES[searchStage]}
              </p>
              {activeVideo && (
                <p className="text-[10px] text-muted-foreground">
                  Source: {activeVideo.filename}
                </p>
              )}
            </div>
            <div className="flex gap-1.5">
              {SEARCH_STAGES.map((_, i) => (
                <div
                  key={i}
                  className={`h-1 rounded-full transition-all duration-500 ${
                    i === searchStage % SEARCH_STAGES.length
                      ? "w-6 bg-primary"
                      : "w-1.5 bg-border"
                  }`}
                />
              ))}
            </div>
          </div>
        ) : activeMsg?.results ? (
          <div className="h-full overflow-y-auto pr-2 pb-20">
            <SearchResults
              results={activeMsg.results}
              activeQuery={activeMsg.content}
              intent={activeMsg.intent}
              onAnalyse={onAnalyseFrame}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-4 opacity-70">
            <div className="h-16 w-16 rounded-3xl bg-primary/10 flex items-center justify-center border border-primary/20 shadow-[0_0_15px_rgba(56,189,248,0.2)]">
              <Sparkles className="h-8 w-8 text-primary animate-pulse" />
            </div>
            <h3 className="font-mono text-sm font-bold uppercase tracking-wider text-foreground">Visual Search Ready</h3>
            <p className="text-xs text-muted-foreground max-w-md leading-relaxed">
              {activeVideo
                ? <>Video loaded. Search the visual index using natural language.<br/><span className="text-primary mt-2 inline-block">&ldquo;Show me the frames where the yellow car is reversing&rdquo;</span></>
                : <>Upload a video or query the visual index. For example: <br/><span className="text-primary mt-2 inline-block">&ldquo;Show me the frames where the yellow car is reversing&rdquo;</span></>
              }
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

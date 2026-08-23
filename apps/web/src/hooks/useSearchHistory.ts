"use client";

import { useState, useCallback, useEffect } from "react";
import { SearchHistoryItem, SearchSnapshot } from "@/types/search";

const STORAGE_KEY = "visualseek_recent_searches";
const MAX_HISTORY = 10;

function sanitizeSnapshot(snapshot: SearchSnapshot): SearchSnapshot {
  // Limit 6.1: Cap visual matches to 20
  const visualMatches = (snapshot.visualMatches || []).slice(0, 20);

  // Limit 6.2 & 6.3: Strip binary/base64 data and truncate message content to 2000 chars
  const messages = (snapshot.messages || []).map((msg) => {
    let content = msg.content;
    if (content && content.length > 2000) {
      content = content.slice(0, 2000) + "... [truncated]";
    }

    const stripBinary = (val: any): any => {
      if (!val) return val;
      if (val instanceof Date) return val;
      if (typeof val === "string") {
        if (val.startsWith("data:") || val.startsWith("blob:") || val.length > 10000) {
          return "[binary data stripped]";
        }
        return val;
      }
      if (Array.isArray(val)) {
        return val.map(stripBinary);
      }
      if (typeof val === "object") {
        const res: Record<string, any> = {};
        for (const k in val) {
          res[k] = stripBinary(val[k]);
        }
        return res;
      }
      return val;
    };

    return {
      ...stripBinary(msg),
      content,
    };
  });

  return {
    ...snapshot,
    visualMatches,
    messages,
  };
}

export function useSearchHistory() {
  const [history, setHistory] = useState<SearchHistoryItem[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as SearchHistoryItem[];
        if (Array.isArray(parsed)) {
          setHistory(parsed);
        }
      }
    } catch {
      setHistory([]);
    }
  }, []);

  const addSearch = useCallback((query: string, snapshot: SearchSnapshot) => {
    const trimmed = query.trim();
    if (!trimmed || trimmed.length < 2) return;

    const sanitized = sanitizeSnapshot(snapshot);

    setHistory((prev) => {
      const deduped = prev.filter(
        (item) => item.query.toLowerCase() !== trimmed.toLowerCase()
      );
      const next: SearchHistoryItem[] = [
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          query: trimmed,
          timestamp: Date.now(),
          snapshot: sanitized,
        },
        ...deduped,
      ].slice(0, MAX_HISTORY);

      // Limit 6.4: Graceful QuotaExceededError handling
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch (e) {
        if (e instanceof DOMException && e.name === "QuotaExceededError") {
          const trimmedNext = next.slice(0, next.length - 1);
          try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmedNext));
          } catch {
            // Storage completely full - fail silently
          }
        }
      }

      return next;
    });
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
  }, []);

  return { history, addSearch, clearHistory };
}

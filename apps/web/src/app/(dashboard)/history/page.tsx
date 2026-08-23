"use client";

import React from "react";
import { History, Search, Trash2, Clock, Play } from "lucide-react";
import { useSearchHistoryContext } from "@/contexts/SearchHistoryContext";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";

export default function HistoryPage() {
  const router = useRouter();
  const { history, clearHistory } = useSearchHistoryContext();

  const handleSelectQuery = (query: string) => {
    router.push(`/search?q=${encodeURIComponent(query)}`);
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <History className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground font-sans">Search History Logs</h1>
            <p className="text-xs text-muted-foreground">
              Review and re-run your natural-language surveillance search prompts.
            </p>
          </div>
        </div>

        {history.length > 0 && (
          <Button
            variant="destructive"
            size="sm"
            onClick={clearHistory}
            className="gap-1.5 text-xs font-semibold rounded-lg"
          >
            <Trash2 className="h-4 w-4" /> Clear All History
          </Button>
        )}
      </div>

      {/* History List */}
      {history.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-12 text-center flex flex-col items-center justify-center space-y-3">
          <Clock className="h-10 w-10 text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">No recent searches found</h3>
          <p className="text-xs text-muted-foreground max-w-xs">
            Start describing security events in natural language from the central dashboard search panel to log history.
          </p>
          <Button onClick={() => router.push("/dashboard")} className="mt-2 text-xs font-semibold">
            Go to Dashboard
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {history.map((item) => (
            <div
              key={item.id}
              onClick={() => handleSelectQuery(item.query)}
              className="flex items-center justify-between rounded-xl border border-border bg-card p-4 hover:border-primary/30 transition-all cursor-pointer group"
            >
              <div className="flex items-center gap-3">
                <Search className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                <div>
                  <p className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">{item.query}</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Logged: {new Date(item.timestamp).toLocaleString()}
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground group-hover:text-foreground"
              >
                <Play className="h-4 w-4 text-primary fill-primary/10" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

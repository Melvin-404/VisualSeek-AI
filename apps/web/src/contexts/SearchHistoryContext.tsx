"use client";

import {
  createContext,
  useContext,
  ReactNode,
  useState,
} from "react";
import { useSearchHistory } from "@/hooks/useSearchHistory";
import { SearchHistoryItem, SearchSnapshot } from "@/types/search";

interface SearchHistoryContextValue {
  history: SearchHistoryItem[];
  addSearch: (query: string, snapshot: SearchSnapshot) => void;
  clearHistory: () => void;
  selectedHistoryItem: SearchHistoryItem | null;
  setSelectedHistoryItem: (item: SearchHistoryItem | null) => void;
}

const SearchHistoryContext =
  createContext<SearchHistoryContextValue | null>(null);

export function SearchHistoryProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { history, addSearch, clearHistory } = useSearchHistory();
  const [selectedHistoryItem, setSelectedHistoryItem] = useState<SearchHistoryItem | null>(null);

  return (
    <SearchHistoryContext.Provider
      value={{ history, addSearch, clearHistory, selectedHistoryItem, setSelectedHistoryItem }}
    >
      {children}
    </SearchHistoryContext.Provider>
  );
}

export function useSearchHistoryContext() {
  const ctx = useContext(SearchHistoryContext);
  if (!ctx) {
    throw new Error(
      "useSearchHistoryContext must be used inside SearchHistoryProvider"
    );
  }
  return ctx;
}

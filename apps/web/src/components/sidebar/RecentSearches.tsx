"use client";

import { SearchHistoryItem } from "@/types/search";
import { formatTimestamp } from "@/utils/formatTimestamp";
import styles from "./RecentSearches.module.css";

interface RecentSearchesProps {
  history: SearchHistoryItem[];
  onSelect: (item: SearchHistoryItem) => void;
  onClear: () => void;
}

export function RecentSearches({
  history,
  onSelect,
  onClear,
}: RecentSearchesProps) {
  if (history.length === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.emptyState}>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={styles.emptyIcon}
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <span className={styles.emptyText}>No recent searches</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.label}>Recent searches</span>
        <button
          className={styles.clearBtn}
          onClick={onClear}
          aria-label="Clear search history"
        >
          Clear
        </button>
      </div>
      <ul className={styles.list} role="list">
        {history.map((item) => {
          const hasSnapshot = item.snapshot !== null;
          return (
            <li
              key={item.id}
              className={styles.item}
              onClick={() => onSelect(item)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(item);
                }
              }}
              title={hasSnapshot ? "Click to restore previous results" : "Click to re-run this search"}
              aria-label={
                hasSnapshot
                  ? `Restore previous search: ${item.query}`
                  : `Re-run search: ${item.query}`
              }
            >
              <div className={styles.iconWrap} aria-hidden="true">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#00ff66"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
              </div>
              <div className={styles.textBlock}>
                <span className={styles.query}>{item.query}</span>
                <div className="flex items-center gap-1.5">
                  {hasSnapshot && (
                    <span className={styles.dotIndicator} aria-hidden="true" />
                  )}
                  <span className={styles.time}>
                    {formatTimestamp(item.timestamp)}
                  </span>
                </div>
              </div>
              <div className={styles.replay} aria-hidden="true">
                {hasSnapshot ? (
                  /* Replay Icon (Return arrow) */
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#00ff66"
                    strokeOpacity={0.7}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="9 10 4 15 9 20" />
                    <path d="M20 4v7a4 4 0 0 1-4 4H4" />
                  </svg>
                ) : (
                  /* Refresh/Reload Icon */
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#00ff66"
                    strokeOpacity={0.7}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                    <path d="M3 3v5h5" />
                    <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                    <path d="M16 16h5v5" />
                  </svg>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

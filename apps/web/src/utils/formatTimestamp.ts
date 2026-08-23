export function formatTimestamp(timestamp: number): string {
  const now = Date.now();
  const diffMs = now - timestamp;
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffMs / 60000);

  if (diffSecs < 60) return "Just now";
  if (diffMins < 60) return `${diffMins} min ago`;

  const date = new Date(timestamp);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  const timeStr = date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

  if (date.toDateString() === today.toDateString()) {
    return `Today ${timeStr}`;
  }
  if (date.toDateString() === yesterday.toDateString()) {
    return `Yesterday ${timeStr}`;
  }

  return date.toLocaleDateString([], { day: "numeric", month: "short" });
}

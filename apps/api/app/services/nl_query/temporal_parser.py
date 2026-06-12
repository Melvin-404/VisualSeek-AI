"""Temporal parser for natural-language time expressions.

Resolves relative and absolute temporal references (e.g. 'yesterday afternoon',
'last 2 hours', 'between 9am and 5pm') into millisecond-epoch start/end ranges.
"""

from __future__ import annotations

import re
import time
import datetime
from dataclasses import dataclass
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger("nl_query.temporal_parser")

# Try to import dateparser for advanced NL date parsing
try:
    import dateparser  # type: ignore[import-untyped]

    _DATEPARSER_AVAILABLE = True
except ImportError:
    _DATEPARSER_AVAILABLE = False
    logger.warning("dateparser not installed — falling back to regex-only temporal parsing.")


@dataclass
class TimeRange:
    """Parsed time range in millisecond-epoch timestamps."""

    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    raw_expression: str = ""


# Common named period mappings (hours of day)
_PERIOD_HOURS: dict[str, Tuple[int, int]] = {
    "morning": (6, 12),
    "afternoon": (12, 17),
    "evening": (17, 21),
    "night": (21, 6),  # wraps to next day for end
    "dawn": (4, 7),
    "dusk": (17, 20),
    "midnight": (0, 1),
    "noon": (11, 13),
    "lunchtime": (11, 14),
    "lunch": (11, 14),
}


class TemporalParser:
    """Parses natural-language temporal expressions into epoch-ms time ranges."""

    def __init__(self, timezone: str = "UTC"):
        self.timezone = timezone

    def parse(self, text: str) -> TimeRange:
        """Extract a time range from the given text.

        Attempts multiple strategies in order:
        1. Regex patterns for common forms ('last N hours', 'today', 'yesterday', etc.)
        2. dateparser library for free-form expressions
        3. Returns empty TimeRange if nothing matched
        """
        if not text:
            return TimeRange()

        text_lower = text.strip().lower()

        # --- Strategy 1: Regex-based fast patterns ---
        result = self._parse_regex(text_lower)
        if result.start_ms is not None:
            return result

        # --- Strategy 2: dateparser (handles 'yesterday afternoon', etc.) ---
        if _DATEPARSER_AVAILABLE:
            result = self._parse_dateparser(text_lower)
            if result.start_ms is not None:
                return result

        return TimeRange(raw_expression=text)

    def _parse_regex(self, text: str) -> TimeRange:
        """Fast regex patterns for common surveillance temporal phrases."""
        now = datetime.datetime.now(datetime.timezone.utc)
        now_ms = int(now.timestamp() * 1000)

        # "last N hours/minutes/seconds/days"
        m = re.search(
            r"\blast\s+(\d+)\s*(hours?|h|minutes?|mins?|m|seconds?|secs?|s|days?|d)\b",
            text,
        )
        if m:
            amount = int(m.group(1))
            unit = m.group(2)[0].lower()
            delta_map = {"h": 3600, "m": 60, "s": 1, "d": 86400}
            delta_sec = amount * delta_map.get(unit, 3600)
            return TimeRange(
                start_ms=now_ms - delta_sec * 1000,
                end_ms=now_ms,
                raw_expression=m.group(0),
            )

        # "between Xam/pm and Yam/pm" (same day)
        m = re.search(
            r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+and\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
            text,
        )
        if m:
            sh, sm, sp = int(m.group(1)), int(m.group(2) or 0), m.group(3)
            eh, em, ep = int(m.group(4)), int(m.group(5) or 0), m.group(6)
            if sp == "pm" and sh != 12:
                sh += 12
            if sp == "am" and sh == 12:
                sh = 0
            if ep == "pm" and eh != 12:
                eh += 12
            if ep == "am" and eh == 12:
                eh = 0
            today = now.date()
            start_dt = datetime.datetime.combine(
                today, datetime.time(sh, sm), tzinfo=datetime.timezone.utc
            )
            end_dt = datetime.datetime.combine(
                today, datetime.time(eh, em), tzinfo=datetime.timezone.utc
            )
            return TimeRange(
                start_ms=int(start_dt.timestamp() * 1000),
                end_ms=int(end_dt.timestamp() * 1000),
                raw_expression=m.group(0),
            )

        # "today [morning/afternoon/evening/night]"
        m = re.search(r"\btoday(?:\s+(morning|afternoon|evening|night))?\b", text)
        if m:
            period = m.group(1)
            today = now.date()
            if period and period in _PERIOD_HOURS:
                sh, eh = _PERIOD_HOURS[period]
                start_dt = datetime.datetime.combine(
                    today, datetime.time(sh, 0), tzinfo=datetime.timezone.utc
                )
                if eh <= sh:  # wraps (e.g. night 21->6)
                    end_dt = datetime.datetime.combine(
                        today + datetime.timedelta(days=1),
                        datetime.time(eh, 0),
                        tzinfo=datetime.timezone.utc,
                    )
                else:
                    end_dt = datetime.datetime.combine(
                        today, datetime.time(eh, 0), tzinfo=datetime.timezone.utc
                    )
            else:
                start_dt = datetime.datetime.combine(
                    today, datetime.time.min, tzinfo=datetime.timezone.utc
                )
                end_dt = now
            return TimeRange(
                start_ms=int(start_dt.timestamp() * 1000),
                end_ms=int(end_dt.timestamp() * 1000),
                raw_expression=m.group(0),
            )

        # "yesterday [morning/afternoon/evening/night]"
        m = re.search(r"\byesterday(?:\s+(morning|afternoon|evening|night))?\b", text)
        if m:
            period = m.group(1)
            yesterday = now.date() - datetime.timedelta(days=1)
            if period and period in _PERIOD_HOURS:
                sh, eh = _PERIOD_HOURS[period]
                start_dt = datetime.datetime.combine(
                    yesterday, datetime.time(sh, 0), tzinfo=datetime.timezone.utc
                )
                if eh <= sh:
                    end_dt = datetime.datetime.combine(
                        yesterday + datetime.timedelta(days=1),
                        datetime.time(eh, 0),
                        tzinfo=datetime.timezone.utc,
                    )
                else:
                    end_dt = datetime.datetime.combine(
                        yesterday, datetime.time(eh, 0), tzinfo=datetime.timezone.utc
                    )
            else:
                start_dt = datetime.datetime.combine(
                    yesterday, datetime.time.min, tzinfo=datetime.timezone.utc
                )
                end_dt = datetime.datetime.combine(
                    yesterday, datetime.time.max, tzinfo=datetime.timezone.utc
                )
            return TimeRange(
                start_ms=int(start_dt.timestamp() * 1000),
                end_ms=int(end_dt.timestamp() * 1000),
                raw_expression=m.group(0),
            )

        # "this week"
        if re.search(r"\bthis\s+week\b", text):
            week_start = now - datetime.timedelta(days=now.weekday())
            start_dt = datetime.datetime.combine(
                week_start.date(), datetime.time.min, tzinfo=datetime.timezone.utc
            )
            return TimeRange(
                start_ms=int(start_dt.timestamp() * 1000),
                end_ms=now_ms,
                raw_expression="this week",
            )

        return TimeRange()

    def _parse_dateparser(self, text: str) -> TimeRange:
        """Use the dateparser library for advanced NL date resolution."""
        settings = {
            "TIMEZONE": self.timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "past",
        }

        # Try to find a range with "from ... to ..." or "... to ..."
        range_match = re.search(
            r"(?:from\s+)?(.+?)\s+(?:to|until|till)\s+(.+)", text
        )
        if range_match:
            start_text, end_text = range_match.group(1), range_match.group(2)
            start_dt = dateparser.parse(start_text, settings=settings)
            end_dt = dateparser.parse(end_text, settings=settings)
            if start_dt and end_dt:
                return TimeRange(
                    start_ms=int(start_dt.timestamp() * 1000),
                    end_ms=int(end_dt.timestamp() * 1000),
                    raw_expression=range_match.group(0),
                )

        # Single date/time expression
        parsed = dateparser.parse(text, settings=settings)
        if parsed:
            # For a single date, create a 1-hour window around it
            start_ms = int(parsed.timestamp() * 1000)
            end_ms = start_ms + 3600 * 1000  # +1h
            return TimeRange(
                start_ms=start_ms,
                end_ms=end_ms,
                raw_expression=text,
            )

        return TimeRange()

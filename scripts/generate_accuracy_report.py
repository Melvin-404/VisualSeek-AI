#!/usr/bin/env python3
"""Accuracy comparison report generator for VisionQuery benchmarks.

Reads ``scripts/benchmark_results.json`` (produced by benchmark_search_after.py)
and generates a formatted Markdown report at ``scripts/accuracy_report.md`` with
per-query metrics, overall summary, and a pass/fail verdict based on a
configurable precision threshold (default: 80%).

Usage:
    python scripts/generate_accuracy_report.py
    python scripts/generate_accuracy_report.py --input results.json --threshold 0.75
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger("report.accuracy")

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def load_results(path: Path) -> Dict[str, Any]:
    """Load and validate the benchmark results JSON."""
    if not path.exists():
        logger.error("Results file not found", path=str(path))
        print(
            f"\n  ERROR: {path} does not exist.\n"
            f"  Run `python scripts/benchmark_search_after.py` first.\n"
        )
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "queries" not in data:
        logger.error("Invalid results format – missing 'queries' key")
        sys.exit(1)

    return data


def generate_markdown(
    data: Dict[str, Any],
    threshold: float,
) -> str:
    """Build the Markdown report string."""
    lines: List[str] = []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# VisionQuery Search Accuracy Report")
    lines.append("")
    lines.append(f"> Generated on **{now}**")
    lines.append("")

    # ── Overall summary ───────────────────────────────────────────────
    overall = data.get("overall", {})
    avg_p = overall.get("avg_precision", 0)
    avg_r = overall.get("avg_recall", 0)
    avg_f1 = overall.get("avg_f1", 0)
    avg_lat = overall.get("avg_latency_ms", 0)
    error_count = overall.get("error_count", 0)
    total_queries = data.get("total_queries", 0)

    verdict = "✅ PASS" if avg_p >= threshold else "❌ FAIL"

    lines.append("## Overall Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Total Queries | {total_queries} |")
    lines.append(f"| Avg Precision | {avg_p:.4f} ({avg_p * 100:.1f}%) |")
    lines.append(f"| Avg Recall | {avg_r:.4f} ({avg_r * 100:.1f}%) |")
    lines.append(f"| Avg F1 Score | {avg_f1:.4f} ({avg_f1 * 100:.1f}%) |")
    lines.append(f"| Avg Latency | {avg_lat:.1f} ms |")
    lines.append(f"| Errors | {error_count} |")
    lines.append(f"| Threshold | {threshold:.0%} avg precision |")
    lines.append(f"| **Verdict** | **{verdict}** |")
    lines.append("")

    # ── Per-category breakdown ────────────────────────────────────────
    by_cat = data.get("by_category", {})
    if by_cat:
        lines.append("## Per-Category Breakdown")
        lines.append("")
        lines.append("| Category | Queries | Avg Precision | Avg Recall | Avg F1 |")
        lines.append("|---|---|---|---|---|")
        for cat, m in sorted(by_cat.items()):
            lines.append(
                f"| {cat} | {m['count']} | "
                f"{m['avg_precision']:.4f} | "
                f"{m['avg_recall']:.4f} | "
                f"{m['avg_f1']:.4f} |"
            )
        lines.append("")

    # ── Per-query detail table ────────────────────────────────────────
    queries = data.get("queries", [])
    if queries:
        lines.append("## Per-Query Detail")
        lines.append("")
        lines.append(
            "| # | Category | Query | Precision | Recall | F1 | Hits | TP | Latency (ms) | Status |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for idx, q in enumerate(queries, 1):
            error = q.get("error")
            status = "❌ Error" if error else "✅"
            prec = f"{q.get('precision', 0):.2f}" if not error else "—"
            rec = f"{q.get('recall', 0):.2f}" if not error else "—"
            f1 = f"{q.get('f1', 0):.2f}" if not error else "—"
            hits = str(q.get("returned", "—"))
            tp = str(q.get("true_positives", "—"))
            lat = f"{q.get('latency_ms', 0):.1f}"
            lines.append(
                f"| {idx} | {q.get('category', '')} | {q.get('query', '')} | "
                f"{prec} | {rec} | {f1} | {hits} | {tp} | {lat} | {status} |"
            )
        lines.append("")

    # ── Error details ─────────────────────────────────────────────────
    error_queries = [q for q in queries if q.get("error")]
    if error_queries:
        lines.append("## Error Details")
        lines.append("")
        for q in error_queries:
            lines.append(f"- **{q['query']}**: `{q['error']}`")
        lines.append("")

    # ── Verdict section ───────────────────────────────────────────────
    lines.append("## Verdict")
    lines.append("")
    if avg_p >= threshold:
        lines.append(
            f"The average precision of **{avg_p:.1%}** meets or exceeds the "
            f"**{threshold:.0%}** threshold. The search pipeline **passes** "
            f"the post-upgrade accuracy benchmark."
        )
    else:
        lines.append(
            f"The average precision of **{avg_p:.1%}** is below the "
            f"**{threshold:.0%}** threshold. The search pipeline **fails** "
            f"the post-upgrade accuracy benchmark. Review the per-query "
            f"breakdown above for specific areas of regression."
        )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown accuracy report from benchmark results.",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=str(ROOT / "scripts" / "benchmark_results.json"),
        help="Path to benchmark_results.json (default: scripts/benchmark_results.json).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "scripts" / "accuracy_report.md"),
        help="Output path for the Markdown report (default: scripts/accuracy_report.md).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.80,
        help="Average precision threshold for pass/fail verdict (default: 0.80).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    data = load_results(input_path)
    markdown = generate_markdown(data, threshold=args.threshold)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    logger.info("Report generated", path=str(output_path))
    print(f"\n  Report written to: {output_path}\n")

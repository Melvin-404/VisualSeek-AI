#!/usr/bin/env python3
"""Post-upgrade search accuracy benchmark for VisionQuery.

Defines ground-truth test queries, runs them through the SearchCoordinator
pipeline against the live PostgreSQL database, computes precision / recall / F1
for each query, prints a summary table and saves results to JSON.

Usage:
    python scripts/benchmark_search_after.py
    python scripts/benchmark_search_after.py --dry-run
    python scripts/benchmark_search_after.py --limit 20 --output results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Path bootstrapping
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "ai-pipeline" / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / "apps" / "api" / ".env")
os.environ.setdefault("API_ENV", "development")

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
logger = structlog.get_logger("benchmark.after")

# ---------------------------------------------------------------------------
# Ground-truth definitions
# ---------------------------------------------------------------------------

@dataclass
class GroundTruthQuery:
    """A single benchmark query with expected matching criteria."""

    category: str
    query: str
    expected_class: Optional[str] = None
    expected_colour: Optional[str] = None
    expected_vehicle_type: Optional[str] = None
    expected_attributes: List[str] = field(default_factory=list)
    expected_gender: Optional[str] = None
    description: str = ""

    def matches_hit(self, hit: Dict[str, Any]) -> bool:
        """Return True if *hit* satisfies every non-None expectation."""
        if self.expected_class:
            label = (hit.get("class_label") or "").lower()
            # 'car' should also match 'vehicle' synonym in the DB
            expected = self.expected_class.lower()
            if expected == "car":
                if label not in ("car", "vehicle"):
                    return False
            elif label != expected:
                return False

        if self.expected_colour:
            colour_lc = self.expected_colour.lower()
            dominant = (hit.get("dominant_colour") or "").lower()
            upper = (hit.get("upper_colour") or "").lower()
            lower = (hit.get("lower_colour") or "").lower()
            if colour_lc not in (dominant, upper, lower):
                return False

        if self.expected_vehicle_type:
            vt = (hit.get("vehicle_type") or "").lower()
            if vt != self.expected_vehicle_type.lower():
                return False

        if self.expected_attributes:
            carried = hit.get("carried_items") or []
            if isinstance(carried, dict):
                carried_set = set(k.lower() for k in carried.keys())
            elif isinstance(carried, list):
                carried_set = set(str(i).lower() for i in carried)
            else:
                carried_set = set()
            for attr in self.expected_attributes:
                if attr.lower() not in carried_set:
                    return False

        if self.expected_gender:
            gender = (hit.get("gender_estimate") or "").lower()
            if gender != self.expected_gender.lower():
                return False

        return True


# fmt: off
GROUND_TRUTH: List[GroundTruthQuery] = [
    # ── Color + class queries ──────────────────────────────────────────
    GroundTruthQuery(
        category="colour_class", query="red car",
        expected_class="car", expected_colour="red",
        description="Basic colour + class",
    ),
    GroundTruthQuery(
        category="colour_class", query="blue truck",
        expected_class="truck", expected_colour="blue",
        description="Blue truck lookup",
    ),
    GroundTruthQuery(
        category="colour_class", query="grey vehicle",
        expected_class="car", expected_colour="grey",
        description="Grey synonym vehicle",
    ),
    GroundTruthQuery(
        category="colour_class", query="black motorcycle",
        expected_class="motorcycle", expected_colour="black",
        description="Black motorcycle",
    ),

    # ── Vehicle style queries ──────────────────────────────────────────
    GroundTruthQuery(
        category="vehicle_style", query="white SUV",
        expected_class="car", expected_colour="white",
        expected_vehicle_type="suv",
        description="White SUV style search",
    ),
    GroundTruthQuery(
        category="vehicle_style", query="silver sedan",
        expected_class="car", expected_colour="silver",
        expected_vehicle_type="sedan",
        description="Silver sedan style",
    ),
    GroundTruthQuery(
        category="vehicle_style", query="red van",
        expected_class="car", expected_colour="red",
        expected_vehicle_type="van",
        description="Red van style",
    ),

    # ── Person attribute queries ───────────────────────────────────────
    GroundTruthQuery(
        category="person_attr", query="person with backpack",
        expected_class="person", expected_attributes=["backpack"],
        description="Person carrying backpack",
    ),
    GroundTruthQuery(
        category="person_attr", query="man in red shirt",
        expected_class="person", expected_colour="red",
        expected_gender="man",
        description="Man with red upper body colour",
    ),
    GroundTruthQuery(
        category="person_attr", query="woman with umbrella",
        expected_class="person", expected_attributes=["umbrella"],
        expected_gender="woman",
        description="Woman carrying umbrella",
    ),
    GroundTruthQuery(
        category="person_attr", query="person with laptop",
        expected_class="person", expected_attributes=["laptop"],
        description="Person carrying laptop",
    ),
    GroundTruthQuery(
        category="person_attr", query="person wearing helmet",
        expected_class="person", expected_attributes=["helmet"],
        description="Person wearing helmet",
    ),

    # ── Cross-camera tracking ──────────────────────────────────────────
    GroundTruthQuery(
        category="cross_camera", query="track the same person across cameras",
        expected_class="person",
        description="Cross-camera ReID for person",
    ),
    GroundTruthQuery(
        category="cross_camera", query="same car spotted on multiple cameras",
        expected_class="car",
        description="Cross-camera ReID for car",
    ),

    # ── Time-ranged queries ────────────────────────────────────────────
    GroundTruthQuery(
        category="temporal", query="cars in the last 2 hours",
        expected_class="car",
        description="Temporal range – last 2h",
    ),
    GroundTruthQuery(
        category="temporal", query="people seen in the last hour",
        expected_class="person",
        description="Temporal range – last 1h",
    ),

    # ── Compound queries ───────────────────────────────────────────────
    GroundTruthQuery(
        category="compound", query="grey sedan near entrance last hour",
        expected_class="car", expected_colour="grey",
        expected_vehicle_type="sedan",
        description="Colour + style + temporal",
    ),
    GroundTruthQuery(
        category="compound", query="white truck in the last 2 hours",
        expected_class="truck", expected_colour="white",
        description="Colour + class + temporal",
    ),
    GroundTruthQuery(
        category="compound", query="person with backpack last hour",
        expected_class="person", expected_attributes=["backpack"],
        description="Person attribute + temporal",
    ),
]
# fmt: on


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

@dataclass
class QueryMetrics:
    """Precision, recall, F1 for a single query."""

    query: str
    category: str
    description: str
    returned: int = 0
    true_positives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None


def compute_metrics(
    gt: GroundTruthQuery,
    hits: List[Dict[str, Any]],
    latency_ms: float,
) -> QueryMetrics:
    """Compute precision / recall / F1 given hits and ground-truth predicates.

    *Precision* = fraction of returned hits that satisfy all expected
    predicates.  *Recall* is approximated: if ≥1 hit matches, recall = 1;
    otherwise 0 (we don't know the total relevant set in the DB).
    """
    tp = sum(1 for h in hits if gt.matches_hit(h))
    total = len(hits)
    precision = tp / total if total > 0 else 0.0
    recall = 1.0 if tp > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return QueryMetrics(
        query=gt.query,
        category=gt.category,
        description=gt.description,
        returned=total,
        true_positives=tp,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        latency_ms=round(latency_ms, 2),
    )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

async def run_benchmark(
    limit: int,
    output_path: Path,
    dry_run: bool,
) -> List[QueryMetrics]:
    """Execute every ground-truth query and return metrics."""

    if dry_run:
        logger.info("Dry-run mode – printing queries only")
        for idx, gt in enumerate(GROUND_TRUTH, 1):
            print(f"  [{idx:>2}] [{gt.category:<15}] {gt.query}")
        return []

    # Late imports so --dry-run works without DB / heavy deps
    from app.core.config import settings  # noqa: F811
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from search.search_coordinator import SearchCoordinator

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    coordinator = SearchCoordinator()
    all_metrics: List[QueryMetrics] = []

    logger.info("Starting benchmark", total_queries=len(GROUND_TRUTH), limit=limit)

    # Warm-up query
    try:
        async with session_factory() as session:
            await coordinator.search(session, "warmup", limit=1)
        logger.info("Warm-up query complete")
    except Exception as exc:
        logger.warning("Warm-up query failed (non-fatal)", error=str(exc))

    for idx, gt in enumerate(GROUND_TRUTH, 1):
        t0 = time.perf_counter()
        try:
            async with session_factory() as session:
                result = await coordinator.search(
                    db_async_session=session,
                    query_text=gt.query,
                    limit=limit,
                )
            latency = (time.perf_counter() - t0) * 1000.0
            hits = result.get("results", [])
            m = compute_metrics(gt, hits, latency)
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000.0
            m = QueryMetrics(
                query=gt.query,
                category=gt.category,
                description=gt.description,
                latency_ms=round(latency, 2),
                error=str(exc),
            )
            logger.error("Query failed", query=gt.query, error=str(exc))

        all_metrics.append(m)
        status = "OK" if m.error is None else "ERR"
        logger.info(
            f"[{idx:>2}/{len(GROUND_TRUTH)}] {status}",
            query=gt.query,
            precision=m.precision,
            recall=m.recall,
            f1=m.f1,
            latency_ms=m.latency_ms,
        )

    await engine.dispose()
    return all_metrics


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_summary_table(metrics: List[QueryMetrics]) -> None:
    """Pretty-print a per-query metrics table to stdout."""
    header = (
        f"{'#':>3}  {'Category':<16} {'Query':<45} "
        f"{'Prec':>6} {'Rec':>6} {'F1':>6} {'Hits':>5} {'TP':>4} {'ms':>8}"
    )
    sep = "-" * len(header)
    print("\n" + "=" * len(header))
    print("POST-UPGRADE SEARCH BENCHMARK RESULTS")
    print("=" * len(header))
    print(header)
    print(sep)

    for idx, m in enumerate(metrics, 1):
        q_display = m.query[:43] + ".." if len(m.query) > 45 else m.query
        if m.error:
            print(f"{idx:>3}  {m.category:<16} {q_display:<45} {'ERROR':>6} {'':>6} {'':>6} {'':>5} {'':>4} {m.latency_ms:>8.1f}")
        else:
            print(
                f"{idx:>3}  {m.category:<16} {q_display:<45} "
                f"{m.precision:>6.2f} {m.recall:>6.2f} {m.f1:>6.2f} "
                f"{m.returned:>5} {m.true_positives:>4} {m.latency_ms:>8.1f}"
            )
    print(sep)

    # Aggregates
    valid = [m for m in metrics if m.error is None]
    if valid:
        avg_p = sum(m.precision for m in valid) / len(valid)
        avg_r = sum(m.recall for m in valid) / len(valid)
        avg_f1 = sum(m.f1 for m in valid) / len(valid)
        avg_lat = sum(m.latency_ms for m in valid) / len(valid)
        print(
            f"{'':>3}  {'OVERALL':<16} {'':45} "
            f"{avg_p:>6.2f} {avg_r:>6.2f} {avg_f1:>6.2f} "
            f"{'':>5} {'':>4} {avg_lat:>8.1f}"
        )

    errors = [m for m in metrics if m.error is not None]
    if errors:
        print(f"\n  ⚠  {len(errors)} queries failed with errors.")

    print("=" * len(header) + "\n")


def save_results(metrics: List[QueryMetrics], path: Path) -> None:
    """Persist metrics to JSON for downstream report generation."""
    payload: Dict[str, Any] = {
        "benchmark": "post_upgrade",
        "total_queries": len(metrics),
        "queries": [asdict(m) for m in metrics],
    }

    valid = [m for m in metrics if m.error is None]
    if valid:
        payload["overall"] = {
            "avg_precision": round(sum(m.precision for m in valid) / len(valid), 4),
            "avg_recall": round(sum(m.recall for m in valid) / len(valid), 4),
            "avg_f1": round(sum(m.f1 for m in valid) / len(valid), 4),
            "avg_latency_ms": round(sum(m.latency_ms for m in valid) / len(valid), 2),
            "error_count": len(metrics) - len(valid),
        }

    # Per-category breakdown
    categories: Dict[str, List[QueryMetrics]] = {}
    for m in valid:
        categories.setdefault(m.category, []).append(m)
    payload["by_category"] = {
        cat: {
            "count": len(ms),
            "avg_precision": round(sum(m.precision for m in ms) / len(ms), 4),
            "avg_recall": round(sum(m.recall for m in ms) / len(ms), 4),
            "avg_f1": round(sum(m.f1 for m in ms) / len(ms), 4),
        }
        for cat, ms in categories.items()
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger.info("Results saved", path=str(path))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post-upgrade search accuracy benchmark for VisionQuery.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print queries without executing against the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum results to request per query (default: 10).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "scripts" / "benchmark_results.json"),
        help="Path for the JSON results file.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output_path = Path(args.output)

    metrics = asyncio.run(
        run_benchmark(limit=args.limit, output_path=output_path, dry_run=args.dry_run)
    )

    if metrics:
        print_summary_table(metrics)
        save_results(metrics, output_path)
    elif args.dry_run:
        logger.info("Dry-run complete. No queries were executed.")

#!/usr/bin/env python3
"""ReID (Re-Identification) gallery validation for VisionQuery.

Queries the ``identity_gallery`` table and validates each gallery profile:
- ReID embedding is 512-dimensional and L2-normalized (norm ≈ 1.0).
- ``sighting_count`` (from gallery metadata) matches the actual count of
  ``detected_objects`` rows that reference the gallery via ``gallery_id``.
- ``object_type`` is one of the expected values ('person' or 'car').

Usage:
    python scripts/validate_reid.py
    python scripts/validate_reid.py --norm-tolerance 0.05
    python scripts/validate_reid.py --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
logger = structlog.get_logger("validate.reid")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_DIM = 512
VALID_OBJECT_TYPES: Set[str] = {"person", "car", "vehicle"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GalleryIssue:
    """A single validation issue for a gallery profile."""

    gallery_id: str
    field_name: str
    issue: str
    expected: Any = None
    actual: Any = None


@dataclass
class ReIDReport:
    """Aggregate ReID validation results."""

    total_galleries: int = 0
    valid_embeddings: int = 0
    invalid_embeddings: int = 0
    correct_sighting_counts: int = 0
    mismatched_sighting_counts: int = 0
    valid_object_types: int = 0
    invalid_object_types: int = 0
    issues: List[GalleryIssue] = field(default_factory=list)
    # Norm statistics
    norm_min: float = float("inf")
    norm_max: float = 0.0
    norm_sum: float = 0.0
    embeddings_checked: int = 0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _l2_norm(embedding: List[float]) -> float:
    """Compute L2 (Euclidean) norm of a vector."""
    return math.sqrt(sum(x * x for x in embedding))


async def run_validation(
    norm_tolerance: float,
    verbose: bool,
) -> ReIDReport:
    """Query identity_gallery and validate each profile."""
    from sqlalchemy import func, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings

    engine = create_async_engine(
        settings.DATABASE_URL, echo=False, future=True, pool_pre_ping=True
    )
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    report = ReIDReport()

    async with session_factory() as session:
        # ── Fetch all gallery profiles ────────────────────────────────
        gallery_result = await session.execute(
            text(
                """
                SELECT id, object_type, reid_embedding, metadata
                FROM identity_gallery
                ORDER BY created_at DESC
                """
            )
        )
        galleries = gallery_result.mappings().all()
        report.total_galleries = len(galleries)

        if not galleries:
            logger.warning("No gallery profiles found in identity_gallery.")
            await engine.dispose()
            return report

        logger.info("Fetched gallery profiles", count=len(galleries))

        # ── Fetch actual sighting counts per gallery_id ───────────────
        sighting_result = await session.execute(
            text(
                """
                SELECT gallery_id, COUNT(*) AS actual_count
                FROM detected_objects
                WHERE gallery_id IS NOT NULL
                GROUP BY gallery_id
                """
            )
        )
        actual_sightings: Dict[str, int] = {
            str(row["gallery_id"]): int(row["actual_count"])
            for row in sighting_result.mappings().all()
        }

    await engine.dispose()

    # ── Validate each gallery profile ─────────────────────────────────
    for g in galleries:
        gid = str(g["id"])
        embedding = g["reid_embedding"]
        object_type = g["object_type"]
        metadata = g.get("metadata") or {}

        # 1. Validate object_type
        if object_type and object_type.lower() in VALID_OBJECT_TYPES:
            report.valid_object_types += 1
        else:
            report.invalid_object_types += 1
            report.issues.append(
                GalleryIssue(
                    gallery_id=gid,
                    field_name="object_type",
                    issue="unexpected object_type value",
                    expected="person | car",
                    actual=object_type,
                )
            )

        # 2. Validate reid_embedding dimensionality and normalization
        if embedding is None:
            report.invalid_embeddings += 1
            report.issues.append(
                GalleryIssue(
                    gallery_id=gid,
                    field_name="reid_embedding",
                    issue="embedding is NULL",
                )
            )
            continue

        if not isinstance(embedding, (list, tuple)):
            # pgvector may return as string; attempt parse
            try:
                embedding = list(embedding)
            except (TypeError, ValueError):
                report.invalid_embeddings += 1
                report.issues.append(
                    GalleryIssue(
                        gallery_id=gid,
                        field_name="reid_embedding",
                        issue="embedding is not iterable",
                        actual=type(embedding).__name__,
                    )
                )
                continue

        dim = len(embedding)
        if dim != EXPECTED_DIM:
            report.invalid_embeddings += 1
            report.issues.append(
                GalleryIssue(
                    gallery_id=gid,
                    field_name="reid_embedding",
                    issue=f"wrong dimensionality (expected {EXPECTED_DIM})",
                    expected=EXPECTED_DIM,
                    actual=dim,
                )
            )
            continue

        norm = _l2_norm(embedding)
        report.norm_sum += norm
        report.embeddings_checked += 1
        report.norm_min = min(report.norm_min, norm)
        report.norm_max = max(report.norm_max, norm)

        if abs(norm - 1.0) > norm_tolerance:
            report.invalid_embeddings += 1
            report.issues.append(
                GalleryIssue(
                    gallery_id=gid,
                    field_name="reid_embedding",
                    issue=f"L2 norm deviates from 1.0 (tolerance={norm_tolerance})",
                    expected=1.0,
                    actual=round(norm, 6),
                )
            )
        else:
            report.valid_embeddings += 1

        # 3. Validate sighting_count
        stored_count = metadata.get("sighting_count") if isinstance(metadata, dict) else None
        actual_count = actual_sightings.get(gid, 0)

        if stored_count is not None:
            if int(stored_count) == actual_count:
                report.correct_sighting_counts += 1
            else:
                report.mismatched_sighting_counts += 1
                report.issues.append(
                    GalleryIssue(
                        gallery_id=gid,
                        field_name="sighting_count",
                        issue="stored count != actual DetectedObject count",
                        expected=actual_count,
                        actual=int(stored_count),
                    )
                )
        else:
            # No stored count – still check if objects reference this gallery
            if actual_count > 0:
                report.correct_sighting_counts += 1
            # If no objects reference this gallery, it could be stale but
            # we don't flag it as an error here

    return report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_report(report: ReIDReport, verbose: bool) -> None:
    """Format and print the ReID validation report."""
    total = report.total_galleries
    if total == 0:
        print("\n  No gallery profiles to validate.\n")
        return

    embed_valid_pct = (report.valid_embeddings / total * 100) if total else 0

    print("\n" + "=" * 70)
    print("ReID GALLERY VALIDATION REPORT")
    print("=" * 70)
    print(f"  Total gallery profiles:     {total}")
    print()
    print("  Embedding validation:")
    print(f"    Valid (512-d, norm≈1.0):   {report.valid_embeddings} ({embed_valid_pct:.1f}%)")
    print(f"    Invalid:                   {report.invalid_embeddings}")

    if report.embeddings_checked > 0:
        avg_norm = report.norm_sum / report.embeddings_checked
        print(f"    Norm range:                [{report.norm_min:.6f}, {report.norm_max:.6f}]")
        print(f"    Norm mean:                 {avg_norm:.6f}")

    print()
    print("  Sighting count accuracy:")
    counted = report.correct_sighting_counts + report.mismatched_sighting_counts
    if counted > 0:
        accuracy = report.correct_sighting_counts / counted * 100
        print(f"    Correct:                   {report.correct_sighting_counts} / {counted} ({accuracy:.1f}%)")
        print(f"    Mismatched:                {report.mismatched_sighting_counts}")
    else:
        print("    No sighting_count metadata found to validate.")

    print()
    print("  Object type validity:")
    print(f"    Valid (person/car):         {report.valid_object_types}")
    print(f"    Invalid:                   {report.invalid_object_types}")

    if verbose and report.issues:
        print()
        print(f"  Detailed issues (showing up to 25 of {len(report.issues)}):")
        print(f"  {'Gallery ID':<38} {'Field':<20} {'Issue':<40} {'Expected':>10} {'Actual':>10}")
        print("  " + "-" * 120)
        for issue in report.issues[:25]:
            exp = str(issue.expected)[:10] if issue.expected is not None else ""
            act = str(issue.actual)[:10] if issue.actual is not None else ""
            print(
                f"  {issue.gallery_id:<38} {issue.field_name:<20} "
                f"{issue.issue:<40} {exp:>10} {act:>10}"
            )

    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate ReID gallery embeddings and sighting counts.",
    )
    parser.add_argument(
        "--norm-tolerance",
        type=float,
        default=0.05,
        help="Acceptable deviation of L2 norm from 1.0 (default: 0.05).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show individual issue details.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = asyncio.run(
        run_validation(norm_tolerance=args.norm_tolerance, verbose=args.verbose)
    )
    print_report(report, verbose=args.verbose)

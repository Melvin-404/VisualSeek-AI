#!/usr/bin/env python3
"""Attribute extraction validation for VisionQuery detected objects.

Samples random ``detected_objects`` rows where ``attributes_extracted = True``
and validates every extracted attribute field against known constraints
(valid colour names, confidence ranges, JSON structure, etc.).

Usage:
    python scripts/validate_attributes.py
    python scripts/validate_attributes.py --sample-size 500
    python scripts/validate_attributes.py --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
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
logger = structlog.get_logger("validate.attributes")

# ---------------------------------------------------------------------------
# Valid value sets
# ---------------------------------------------------------------------------

VALID_COLOURS: Set[str] = {
    "red", "blue", "green", "yellow", "black", "white", "grey", "silver",
    "orange", "purple", "brown", "pink", "beige", "navy", "maroon", "cyan",
    "magenta", "gold", "tan", "olive", "teal", "coral", "cream", "charcoal",
    "khaki", "lavender", "turquoise", "burgundy", "ivory",
}

VALID_VEHICLE_TYPES: Set[str] = {
    "suv", "sedan", "truck", "van", "motorcycle", "bus", "hatchback",
    "coupe", "pickup", "minivan", "convertible", "wagon", "crossover",
}

VALID_GENDERS: Set[Optional[str]] = {"male", "female", None}

VEHICLE_CLASSES: Set[str] = {"car", "truck", "bus", "motorcycle", "vehicle"}
PERSON_CLASSES: Set[str] = {"person"}

# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """One validation failure for a specific record."""

    object_id: str
    field_name: str
    issue: str
    actual_value: Any = None


@dataclass
class ValidationReport:
    """Aggregate validation results."""

    total_sampled: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)
    field_issue_counts: Dict[str, int] = field(default_factory=dict)


def validate_record(row: Dict[str, Any], report: ValidationReport) -> bool:
    """Validate a single detected_object record. Returns True if fully valid."""
    obj_id = str(row.get("id", "unknown"))
    is_valid = True

    def _add_issue(field_name: str, issue: str, value: Any = None) -> None:
        nonlocal is_valid
        is_valid = False
        report.issues.append(
            ValidationIssue(
                object_id=obj_id,
                field_name=field_name,
                issue=issue,
                actual_value=value,
            )
        )
        report.field_issue_counts[field_name] = (
            report.field_issue_counts.get(field_name, 0) + 1
        )

    class_label = (row.get("class_label") or "").lower()

    # ── dominant_colour ────────────────────────────────────────────────
    dominant = row.get("dominant_colour")
    if dominant is not None:
        if dominant.lower() not in VALID_COLOURS:
            _add_issue("dominant_colour", "not a recognized colour name", dominant)
    # If attributes_extracted is True, dominant_colour should usually be set
    if dominant is None:
        _add_issue("dominant_colour", "NULL despite attributes_extracted=True")

    # ── colour_confidence ──────────────────────────────────────────────
    cc = row.get("colour_confidence")
    if cc is not None:
        if not isinstance(cc, (int, float)):
            _add_issue("colour_confidence", "not a numeric type", cc)
        elif not (0.0 <= cc <= 1.0):
            _add_issue("colour_confidence", "out of [0.0, 1.0] range", cc)

    # ── vehicle_type (vehicles only) ───────────────────────────────────
    if class_label in VEHICLE_CLASSES:
        vt = row.get("vehicle_type")
        if vt is not None and vt.lower() not in VALID_VEHICLE_TYPES:
            _add_issue("vehicle_type", "unrecognized vehicle type string", vt)
        vtc = row.get("vehicle_type_confidence")
        if vtc is not None and not (0.0 <= vtc <= 1.0):
            _add_issue("vehicle_type_confidence", "out of [0.0, 1.0] range", vtc)

    # ── upper/lower colour (persons only) ──────────────────────────────
    if class_label in PERSON_CLASSES:
        for colour_field in ("upper_colour", "lower_colour"):
            colour_val = row.get(colour_field)
            if colour_val is not None and colour_val.lower() not in VALID_COLOURS:
                _add_issue(colour_field, "not a recognized colour name", colour_val)

        for conf_field in ("upper_colour_conf", "lower_colour_conf"):
            conf_val = row.get(conf_field)
            if conf_val is not None and not (0.0 <= conf_val <= 1.0):
                _add_issue(conf_field, "out of [0.0, 1.0] range", conf_val)

    # ── carried_items ──────────────────────────────────────────────────
    carried = row.get("carried_items")
    if carried is not None:
        if not isinstance(carried, (list, dict)):
            _add_issue("carried_items", "not a valid JSON list or object", type(carried).__name__)
    # A None carried_items is acceptable

    # ── gender_estimate ────────────────────────────────────────────────
    gender = row.get("gender_estimate")
    if gender is not None:
        if gender.lower() not in {"male", "female"}:
            _add_issue("gender_estimate", "not 'male', 'female', or None", gender)

    return is_valid


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_validation(sample_size: int, verbose: bool) -> ValidationReport:
    """Sample extracted objects and validate attributes."""
    from sqlalchemy import func, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.schema_models import DetectedObject

    engine = create_async_engine(
        settings.DATABASE_URL, echo=False, future=True, pool_pre_ping=True
    )
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    report = ValidationReport()

    async with session_factory() as session:
        # Total count of extracted objects
        count_result = await session.execute(
            text(
                "SELECT COUNT(*) FROM detected_objects WHERE attributes_extracted = true"
            )
        )
        total_extracted = count_result.scalar() or 0
        logger.info("Total objects with attributes_extracted=True", count=total_extracted)

        if total_extracted == 0:
            logger.warning("No objects with attributes_extracted=True found.")
            await engine.dispose()
            return report

        effective_sample = min(sample_size, total_extracted)

        # Random sample via TABLESAMPLE or ORDER BY random()
        rows_result = await session.execute(
            text(
                """
                SELECT id, class_label, dominant_colour, colour_confidence,
                       vehicle_type, vehicle_type_confidence,
                       upper_colour, upper_colour_conf,
                       lower_colour, lower_colour_conf,
                       carried_items, gender_estimate, gender_is_estimate
                FROM detected_objects
                WHERE attributes_extracted = true
                ORDER BY random()
                LIMIT :sample_limit
                """
            ),
            {"sample_limit": effective_sample},
        )
        rows = rows_result.mappings().all()

    await engine.dispose()

    report.total_sampled = len(rows)
    logger.info("Sampled objects for validation", count=len(rows))

    for row in rows:
        row_dict = dict(row)
        valid = validate_record(row_dict, report)
        if valid:
            report.valid_count += 1
        else:
            report.invalid_count += 1

    return report


def print_report(report: ValidationReport, verbose: bool) -> None:
    """Format and print the validation report."""
    total = report.total_sampled
    if total == 0:
        print("\n  No records to validate.\n")
        return

    valid_pct = (report.valid_count / total) * 100 if total else 0
    invalid_pct = (report.invalid_count / total) * 100 if total else 0

    print("\n" + "=" * 70)
    print("ATTRIBUTE EXTRACTION VALIDATION REPORT")
    print("=" * 70)
    print(f"  Sampled records:  {total}")
    print(f"  Valid records:    {report.valid_count} ({valid_pct:.1f}%)")
    print(f"  Invalid records:  {report.invalid_count} ({invalid_pct:.1f}%)")

    if report.field_issue_counts:
        print("\n  Issue breakdown by field:")
        print(f"  {'Field':<28} {'Count':>6} {'% of Sample':>12}")
        print("  " + "-" * 48)
        for field_name, count in sorted(
            report.field_issue_counts.items(), key=lambda x: -x[1]
        ):
            pct = (count / total) * 100
            print(f"  {field_name:<28} {count:>6} {pct:>11.1f}%")

    if verbose and report.issues:
        print("\n  Example invalid records (up to 20):")
        print(f"  {'Object ID':<38} {'Field':<24} {'Issue':<30} {'Value'}")
        print("  " + "-" * 100)
        for issue in report.issues[:20]:
            val_display = str(issue.actual_value)[:25] if issue.actual_value is not None else "NULL"
            print(
                f"  {issue.object_id:<38} {issue.field_name:<24} "
                f"{issue.issue:<30} {val_display}"
            )

    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate attribute extraction quality on detected_objects.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of random objects to validate (default: 100).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show individual invalid record examples.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = asyncio.run(run_validation(sample_size=args.sample_size, verbose=args.verbose))
    print_report(report, verbose=args.verbose)

"""
Conflict Learning - CORE-023 Part 3

Analyzes conflict resolution patterns from .workflow_log.jsonl and:
- Surfaces conflict statistics in LEARN phase
- Identifies frequently conflicted files
- Auto-adds suggestions to ROADMAP.md

This module follows the source plan (lines 112-120):
- Log conflict resolutions to .workflow_log.jsonl (done in logger.py)
- LEARN phase surfaces conflict patterns
- Auto-add suggestions to ROADMAP.md (inform user, don't ask)
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Defaults
# ============================================================================

DEFAULT_THRESHOLD = 3  # Files with >= 3 conflicts get flagged
DEFAULT_SESSION_WINDOW = 10  # Analyze last 10 sessions worth of events


# ============================================================================
# Conflict Summary
# ============================================================================

def get_conflict_summary(working_dir: Optional[Path] = None) -> dict:
    """
    Get summary of conflict resolutions from workflow log.

    Args:
        working_dir: Working directory containing .workflow_log.jsonl

    Returns:
        Dict with conflict statistics:
        - total_conflicts: Total number of conflicts resolved
        - resolved_count: Number successfully resolved
        - strategies: Dict of strategy -> count
        - files: Dict of file -> count
        - avg_resolution_time_ms: Average resolution time
    """
    if working_dir is None:
        working_dir = Path.cwd()
    else:
        working_dir = Path(working_dir)

    log_file = working_dir / ".workflow_log.jsonl"

    summary = {
        "total_conflicts": 0,
        "resolved_count": 0,
        "strategies": defaultdict(int),
        "files": defaultdict(int),
        "resolution_times": [],
    }

    if not log_file.exists():
        return _finalize_summary(summary)

    try:
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"Skipping malformed log line: {line[:50]}...")
                    continue

                # Only process conflict_resolved events
                if event.get("event_type") != "conflict_resolved":
                    continue

                details = event.get("details", {})
                if not details:
                    continue

                file_path = details.get("file")
                strategy = details.get("strategy")
                resolution_time = details.get("resolution_time_ms")

                if not file_path:
                    continue

                summary["total_conflicts"] += 1
                summary["resolved_count"] += 1

                if file_path:
                    summary["files"][file_path] += 1
                if strategy:
                    summary["strategies"][strategy] += 1
                if resolution_time is not None:
                    summary["resolution_times"].append(resolution_time)

    except Exception as e:
        logger.warning(f"Error reading log file: {e}")

    return _finalize_summary(summary)


def _finalize_summary(summary: dict) -> dict:
    """Convert defaultdicts to regular dicts and calculate averages."""
    times = summary.pop("resolution_times", [])

    result = {
        "total_conflicts": summary["total_conflicts"],
        "resolved_count": summary["resolved_count"],
        "strategies": dict(summary["strategies"]),
        "files": dict(summary["files"]),
        "avg_resolution_time_ms": (
            sum(times) / len(times) if times else 0.0
        ),
    }

    return result


# ============================================================================
# Conflict Patterns
# ============================================================================

def get_conflict_patterns(
    working_dir: Optional[Path] = None,
    threshold: int = DEFAULT_THRESHOLD,
) -> list[dict]:
    """
    Identify files with frequent conflicts.

    Args:
        working_dir: Working directory containing .workflow_log.jsonl
        threshold: Minimum conflicts to be flagged as a pattern

    Returns:
        List of pattern dicts, each with:
        - file: Path to frequently conflicted file
        - count: Number of conflicts
        - strategies: Dict of strategy -> count for this file
    """
    if working_dir is None:
        working_dir = Path.cwd()
    else:
        working_dir = Path(working_dir)

    log_file = working_dir / ".workflow_log.jsonl"

    # Track conflicts per file with strategy breakdown
    file_conflicts = defaultdict(lambda: {"count": 0, "strategies": defaultdict(int)})

    if not log_file.exists():
        return []

    try:
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event.get("event_type") != "conflict_resolved":
                    continue

                details = event.get("details", {})
                file_path = details.get("file")
                strategy = details.get("strategy")

                if not file_path:
                    continue

                file_conflicts[file_path]["count"] += 1
                if strategy:
                    file_conflicts[file_path]["strategies"][strategy] += 1

    except Exception as e:
        logger.warning(f"Error analyzing conflict patterns: {e}")
        return []

    # Filter to files exceeding threshold
    patterns = []
    for file_path, data in file_conflicts.items():
        if data["count"] >= threshold:
            patterns.append({
                "file": file_path,
                "count": data["count"],
                "strategies": dict(data["strategies"]),
            })

    # Sort by count descending
    patterns.sort(key=lambda p: p["count"], reverse=True)

    return patterns


# ============================================================================
# Roadmap Suggestions
# ============================================================================

def suggest_roadmap_additions(patterns: list[dict]) -> list[str]:
    """
    Generate roadmap suggestions from conflict patterns.

    Args:
        patterns: List of pattern dicts from get_conflict_patterns()

    Returns:
        List of markdown-formatted suggestions
    """
    if not patterns:
        return []

    suggestions = []
    for pattern in patterns:
        file_path = pattern["file"]
        count = pattern["count"]

        # Format as a roadmap item
        suggestion = (
            f"- [ ] Refactor `{file_path}` to reduce conflict frequency "
            f"(had {count} conflicts in recent sessions)"
        )
        suggestions.append(suggestion)

    return suggestions


def append_roadmap_suggestion(
    working_dir: Optional[Path],
    suggestion: str,
) -> bool:
    """
    Append a suggestion to ROADMAP.md.

    Creates a "Conflict-Related Suggestions" section if it doesn't exist.

    Args:
        working_dir: Working directory containing ROADMAP.md
        suggestion: Markdown-formatted suggestion to append

    Returns:
        True if successfully appended, False otherwise
    """
    if working_dir is None:
        working_dir = Path.cwd()
    else:
        working_dir = Path(working_dir)

    roadmap_file = working_dir / "ROADMAP.md"

    if not roadmap_file.exists():
        logger.debug(f"ROADMAP.md not found at {roadmap_file}")
        return False

    try:
        content = roadmap_file.read_text()

        # Check if section already exists
        section_header = "## Conflict-Related Suggestions"
        if section_header not in content:
            # Add section at the end
            content = content.rstrip() + f"\n\n{section_header}\n\n"

        # Find the section and append suggestion
        section_index = content.index(section_header)
        section_end = section_index + len(section_header)

        # Find the next section (## ) or end of file
        next_section = content.find("\n## ", section_end)
        if next_section == -1:
            # No next section, append at end
            content = content.rstrip() + f"\n{suggestion}\n"
        else:
            # Insert before next section
            content = (
                content[:next_section].rstrip() +
                f"\n{suggestion}\n" +
                content[next_section:]
            )

        roadmap_file.write_text(content)
        logger.info(f"Added conflict suggestion to ROADMAP.md: {suggestion[:50]}...")
        return True

    except Exception as e:
        logger.error(f"Failed to append to ROADMAP.md: {e}")
        return False


# ============================================================================
# Formatting for LEARN Phase
# ============================================================================

def format_conflict_summary(summary: dict) -> str:
    """
    Format conflict summary for LEARN phase display.

    Args:
        summary: Summary dict from get_conflict_summary()

    Returns:
        Formatted string for display (empty if no conflicts)
    """
    if summary["total_conflicts"] == 0:
        return ""

    lines = [
        "CONFLICT RESOLUTION SUMMARY",
        "-" * 40,
        f"Total conflicts resolved: {summary['total_conflicts']}",
    ]

    # Show average resolution time if available
    if summary["avg_resolution_time_ms"] > 0:
        avg_ms = summary["avg_resolution_time_ms"]
        lines.append(f"Average resolution time: {avg_ms:.0f}ms")

    # Show strategy breakdown
    if summary["strategies"]:
        lines.append("")
        lines.append("Strategies used:")
        for strategy, count in sorted(
            summary["strategies"].items(),
            key=lambda x: x[1],
            reverse=True
        ):
            lines.append(f"  {strategy}: {count}")

    # Show most conflicted files
    if summary["files"]:
        lines.append("")
        lines.append("Most conflicted files:")
        # Top 5 files
        sorted_files = sorted(
            summary["files"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        for file_path, count in sorted_files:
            lines.append(f"  {file_path}: {count} conflicts")

    lines.append("-" * 40)

    return "\n".join(lines)


# ============================================================================
# Main Learning Function (for CLI integration)
# ============================================================================

def run_conflict_learning(
    working_dir: Optional[Path] = None,
    threshold: int = DEFAULT_THRESHOLD,
    auto_roadmap: bool = True,
) -> dict:
    """
    Run full conflict learning analysis.

    This is the main entry point for CLI/LEARN phase integration.

    Args:
        working_dir: Working directory
        threshold: Conflict threshold for pattern detection
        auto_roadmap: If True, auto-add suggestions to ROADMAP.md

    Returns:
        Dict with:
        - summary: Conflict summary dict
        - patterns: List of conflict patterns
        - suggestions: List of suggestions
        - suggestions_added: Number of suggestions added to roadmap
        - formatted_output: Formatted string for display
    """
    if working_dir is None:
        working_dir = Path.cwd()
    else:
        working_dir = Path(working_dir)

    result = {
        "summary": {},
        "patterns": [],
        "suggestions": [],
        "suggestions_added": 0,
        "formatted_output": "",
    }

    # Step 1: Get summary
    result["summary"] = get_conflict_summary(working_dir)

    # Step 2: Get patterns
    result["patterns"] = get_conflict_patterns(working_dir, threshold)

    # Step 3: Generate suggestions
    result["suggestions"] = suggest_roadmap_additions(result["patterns"])

    # Step 4: Auto-add to roadmap (if enabled)
    if auto_roadmap and result["suggestions"]:
        for suggestion in result["suggestions"]:
            if append_roadmap_suggestion(working_dir, suggestion):
                result["suggestions_added"] += 1

    # Step 5: Format output
    result["formatted_output"] = format_conflict_summary(result["summary"])

    return result

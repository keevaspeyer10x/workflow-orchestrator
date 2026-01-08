#!/usr/bin/env python3
"""
Multi-Agent Coordinator CLI

Entry point for running the coordinator from GitHub Actions or command line.

Usage:
    python -m src.coordinator --mode=event --output=github
    python -m src.coordinator --mode=scheduled --dry-run=true
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .discovery import AgentDiscovery, DiscoveredBranch
from .fast_path import FastPathMerger, MergeResult
from ..conflict.detector import ConflictDetector, ConflictInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# ============================================================================
# Output Formatters
# ============================================================================

class OutputFormatter:
    """Base class for output formatting."""

    def start_run(self, mode: str, trigger_branch: Optional[str] = None):
        pass

    def log_discovery(self, branches: list[DiscoveredBranch]):
        pass

    def log_conflict_check(self, branch: str, info: ConflictInfo):
        pass

    def log_pr_created(self, result: MergeResult):
        pass

    def log_error(self, message: str):
        pass

    def end_run(self, summary: dict):
        pass


class ConsoleFormatter(OutputFormatter):
    """Plain console output."""

    def start_run(self, mode: str, trigger_branch: Optional[str] = None):
        print(f"\n{'='*60}")
        print(f"Multi-Agent Coordinator - Mode: {mode}")
        if trigger_branch:
            print(f"Trigger Branch: {trigger_branch}")
        print(f"{'='*60}\n")

    def log_discovery(self, branches: list[DiscoveredBranch]):
        print(f"Discovered {len(branches)} agent branch(es):")
        for b in branches:
            print(f"  - {b.branch_name} ({b.commit_count} commits)")

    def log_conflict_check(self, branch: str, info: ConflictInfo):
        status = "clean" if info.is_fast_path else f"conflicts ({info.file_count} files)"
        print(f"  {branch}: {status}")

    def log_pr_created(self, result: MergeResult):
        if result.success and result.pr_info:
            print(f"  Created PR #{result.pr_info.number}: {result.pr_info.url}")
        else:
            print(f"  Failed to create PR: {result.error}")

    def log_error(self, message: str):
        print(f"ERROR: {message}", file=sys.stderr)

    def end_run(self, summary: dict):
        print(f"\n{'='*60}")
        print("Summary:")
        print(f"  Branches processed: {summary.get('branches_processed', 0)}")
        print(f"  PRs created: {summary.get('prs_created', 0)}")
        print(f"  Conflicts found: {summary.get('conflicts_found', 0)}")
        print(f"  Errors: {summary.get('errors', 0)}")
        print(f"{'='*60}\n")


class GitHubActionsFormatter(OutputFormatter):
    """GitHub Actions specific output with step outputs and annotations."""

    def __init__(self):
        self.github_output_file = os.environ.get("GITHUB_OUTPUT")
        self.github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY")

    def start_run(self, mode: str, trigger_branch: Optional[str] = None):
        print(f"::group::Coordinator Start")
        print(f"Mode: {mode}")
        if trigger_branch:
            print(f"Trigger Branch: {trigger_branch}")
        print("::endgroup::")

    def log_discovery(self, branches: list[DiscoveredBranch]):
        print(f"::group::Branch Discovery")
        print(f"Found {len(branches)} agent branch(es)")
        for b in branches:
            print(f"  - {b.branch_name}")
        print("::endgroup::")

        # Set output
        self._set_output("branch_count", str(len(branches)))
        self._set_output("branches", ",".join(b.branch_name for b in branches))

    def log_conflict_check(self, branch: str, info: ConflictInfo):
        if info.is_fast_path:
            print(f"::notice title=Clean Branch::{branch} has no conflicts")
        else:
            print(f"::warning title=Conflicts Found::{branch} has {info.file_count} conflicting file(s)")

    def log_pr_created(self, result: MergeResult):
        if result.success and result.pr_info:
            print(f"::notice title=PR Created::#{result.pr_info.number} - {result.pr_info.url}")
        else:
            print(f"::error title=PR Creation Failed::{result.error}")

    def log_error(self, message: str):
        print(f"::error::{message}")

    def end_run(self, summary: dict):
        # Set summary outputs
        self._set_output("branches_processed", str(summary.get('branches_processed', 0)))
        self._set_output("prs_created", str(summary.get('prs_created', 0)))
        self._set_output("conflicts_found", str(summary.get('conflicts_found', 0)))
        self._set_output("success", "true" if summary.get('errors', 0) == 0 else "false")

    def _set_output(self, name: str, value: str):
        """Set a GitHub Actions output variable."""
        if self.github_output_file:
            with open(self.github_output_file, "a") as f:
                f.write(f"{name}={value}\n")


# ============================================================================
# Coordinator
# ============================================================================

class Coordinator:
    """
    Main coordinator that orchestrates agent branch processing.

    Phase 1 (MVP): Fast-path only - merge non-conflicting branches
    Phase 2+: Conflict resolution, escalation
    """

    def __init__(
        self,
        base_branch: str = "main",
        dry_run: bool = False,
        formatter: Optional[OutputFormatter] = None,
    ):
        self.base_branch = base_branch
        self.dry_run = dry_run
        self.formatter = formatter or ConsoleFormatter()

        self.discovery = AgentDiscovery(base_branch=base_branch)
        self.detector = ConflictDetector(base_branch=base_branch)
        self.merger = FastPathMerger(base_branch=base_branch)

        # Ensure log directory exists
        self.log_dir = Path(".claude/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        mode: str = "scheduled",
        trigger_branch: Optional[str] = None,
        target_branch: Optional[str] = None,
        force_resolve: bool = False,
    ) -> dict:
        """
        Run the coordination cycle.

        Args:
            mode: Run mode (event, scheduled, manual)
            trigger_branch: Branch that triggered the run (for event mode)
            target_branch: Specific branch to process (optional)
            force_resolve: Force conflict resolution attempt

        Returns:
            Summary dict with results
        """
        summary = {
            "branches_processed": 0,
            "prs_created": 0,
            "conflicts_found": 0,
            "errors": 0,
            "start_time": datetime.now(timezone.utc).isoformat(),
        }

        self.formatter.start_run(mode, trigger_branch)

        try:
            # Step 1: Discover branches
            branches = self.discovery.discover_branches(include_remote=True)

            # Filter to target branch if specified
            if target_branch:
                branches = [b for b in branches if b.branch_name == target_branch]

            self.formatter.log_discovery(branches)

            if not branches:
                logger.info("No agent branches found")
                summary["end_time"] = datetime.now(timezone.utc).isoformat()
                self.formatter.end_run(summary)
                self._write_summary(summary)
                return summary

            # Step 2: Check each branch for conflicts
            fast_path_branches: list[DiscoveredBranch] = []
            conflict_branches: list[tuple[DiscoveredBranch, ConflictInfo]] = []

            for branch in branches:
                try:
                    info = self.detector.detect([branch.branch_name])
                    self.formatter.log_conflict_check(branch.branch_name, info)

                    if info.is_fast_path:
                        fast_path_branches.append(branch)
                    else:
                        conflict_branches.append((branch, info))
                        summary["conflicts_found"] += 1

                except Exception as e:
                    logger.error(f"Error checking {branch.branch_name}: {e}")
                    self.formatter.log_error(f"Error checking {branch.branch_name}: {e}")
                    summary["errors"] += 1

                summary["branches_processed"] += 1

            # Step 3: Create PRs for non-conflicting branches
            if fast_path_branches:
                logger.info(f"Creating PRs for {len(fast_path_branches)} clean branch(es)")

                if self.dry_run:
                    logger.info("DRY RUN: Would create PRs for:")
                    for b in fast_path_branches:
                        logger.info(f"  - {b.branch_name}")
                else:
                    # Try to create a combined PR if multiple branches
                    if len(fast_path_branches) > 1:
                        result = self.merger.create_combined_pr(
                            fast_path_branches,
                            draft=False,
                        )
                        self.formatter.log_pr_created(result)
                        if result.success:
                            summary["prs_created"] += 1
                        else:
                            summary["errors"] += 1
                    else:
                        # Single branch - create individual PR
                        for branch in fast_path_branches:
                            result = self.merger.create_pr(branch, draft=False)
                            self.formatter.log_pr_created(result)
                            if result.success:
                                summary["prs_created"] += 1
                            else:
                                summary["errors"] += 1

            # Step 4: Handle conflicts (Phase 2+)
            if conflict_branches:
                logger.info(f"Found {len(conflict_branches)} branch(es) with conflicts")
                # TODO: Phase 2+ - escalation, resolution
                for branch, info in conflict_branches:
                    logger.warning(
                        f"Branch {branch.branch_name} has conflicts "
                        f"({info.file_count} files) - resolution not yet implemented"
                    )

        except Exception as e:
            logger.error(f"Coordinator error: {e}")
            self.formatter.log_error(str(e))
            summary["errors"] += 1

        summary["end_time"] = datetime.now(timezone.utc).isoformat()
        self.formatter.end_run(summary)
        self._write_summary(summary)

        return summary

    def _write_summary(self, summary: dict):
        """Write summary to log file for GitHub Actions."""
        summary_file = self.log_dir / "coordinator-summary.md"

        lines = [
            "### Coordinator Results",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Branches Processed | {summary.get('branches_processed', 0)} |",
            f"| PRs Created | {summary.get('prs_created', 0)} |",
            f"| Conflicts Found | {summary.get('conflicts_found', 0)} |",
            f"| Errors | {summary.get('errors', 0)} |",
            "",
        ]

        summary_file.write_text("\n".join(lines))

        # Also write JSON for programmatic access
        json_file = self.log_dir / "coordinator-summary.json"
        json_file.write_text(json.dumps(summary, indent=2))


# ============================================================================
# CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-Agent Coordinator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["event", "scheduled", "manual"],
        default="manual",
        help="Run mode (default: manual)"
    )

    parser.add_argument(
        "--force",
        type=str,
        default="false",
        help="Force resolution attempt (true/false)"
    )

    parser.add_argument(
        "--dry-run",
        type=str,
        default="false",
        help="Dry run - don't create PRs (true/false)"
    )

    parser.add_argument(
        "--branch",
        type=str,
        default="",
        help="Specific branch to process"
    )

    parser.add_argument(
        "--base",
        type=str,
        default="main",
        help="Base branch (default: main)"
    )

    parser.add_argument(
        "--output",
        choices=["console", "github"],
        default="console",
        help="Output format (default: console)"
    )

    return parser.parse_args()


def str_to_bool(value: str) -> bool:
    """Convert string to boolean."""
    return value.lower() in ("true", "1", "yes")


def main():
    args = parse_args()

    # Get environment variables for event mode
    trigger_branch = os.environ.get("TRIGGER_BRANCH", "")
    trigger_sha = os.environ.get("TRIGGER_SHA", "")

    # Select formatter
    if args.output == "github":
        formatter = GitHubActionsFormatter()
    else:
        formatter = ConsoleFormatter()

    # Create and run coordinator
    coordinator = Coordinator(
        base_branch=args.base,
        dry_run=str_to_bool(args.dry_run),
        formatter=formatter,
    )

    summary = coordinator.run(
        mode=args.mode,
        trigger_branch=trigger_branch or None,
        target_branch=args.branch or None,
        force_resolve=str_to_bool(args.force),
    )

    # Exit with error code if there were errors
    if summary.get("errors", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

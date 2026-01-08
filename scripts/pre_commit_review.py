#!/usr/bin/env python3
"""
Pre-Commit Review Enforcement Script

This script runs the ReviewOrchestrator on staged changes before commits.
It blocks commits that have blocking issues (critical issues or high-severity
consensus issues).

Usage:
    python scripts/pre_commit_review.py

Exit codes:
    0 - Review passed, commit allowed
    1 - Review found blocking issues, commit blocked
    2 - Review system error

Integration:
    Can be used as a git pre-commit hook by adding to .git/hooks/pre-commit:
        #!/bin/sh
        python scripts/pre_commit_review.py || exit 1
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.review.orchestrator import ReviewOrchestrator
from src.review.schema import ChangeContext, IssueSeverity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Review history directory
REVIEW_HISTORY_DIR = Path(__file__).parent.parent / ".review_history"


# ============================================================================
# Static Workflow Audit (runs before external model reviews)
# ============================================================================

def audit_github_workflows(files: list[str], diff_content: str) -> list[dict]:
    """
    Audit GitHub Actions workflow files for dangerous patterns.

    This is a static check that runs locally without external models.
    It catches common issues like:
    - High-frequency schedules (cost/compute concern)
    - Overly permissive permissions
    - Missing concurrency controls
    - Secrets exposure risks

    Returns list of blocking issues found.
    """
    issues = []

    workflow_files = [f for f in files if f.startswith('.github/workflows/') and f.endswith('.yml')]

    if not workflow_files:
        return issues

    logger.info(f"Auditing {len(workflow_files)} GitHub Actions workflow file(s)")

    for filepath in workflow_files:
        try:
            # Read the staged version of the file
            result = subprocess.run(
                ["git", "show", f":{filepath}"],
                capture_output=True,
                text=True,
                check=True,
            )
            content = result.stdout
        except subprocess.CalledProcessError:
            # File might be deleted or not staged properly
            continue

        file_issues = _audit_single_workflow(filepath, content)
        issues.extend(file_issues)

    return issues


def _audit_single_workflow(filepath: str, content: str) -> list[dict]:
    """Audit a single workflow file for dangerous patterns."""
    issues = []

    # Check 1: High-frequency cron schedules
    cron_matches = re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", content)
    for cron in cron_matches:
        runs_per_day = _estimate_cron_frequency(cron)
        if runs_per_day > 24:  # More than hourly
            issues.append({
                "severity": "critical",
                "category": "cost",
                "title": f"High-frequency workflow schedule: {runs_per_day} runs/day",
                "description": (
                    f"Workflow '{filepath}' has cron schedule '{cron}' which runs ~{runs_per_day} times/day. "
                    f"This could consume {runs_per_day * 30} minutes/month of GitHub Actions compute. "
                    "Consider reducing frequency or using event-driven triggers instead."
                ),
                "file_path": filepath,
                "recommendation": "Use event-driven triggers (push, pull_request, repository_dispatch) or reduce to hourly/daily.",
            })
        elif runs_per_day > 4:  # More than every 6 hours
            issues.append({
                "severity": "high",
                "category": "cost",
                "title": f"Frequent workflow schedule: {runs_per_day} runs/day",
                "description": (
                    f"Workflow '{filepath}' has cron schedule '{cron}' which runs ~{runs_per_day} times/day. "
                    "Verify this frequency is necessary."
                ),
                "file_path": filepath,
                "recommendation": "Consider if this frequency is needed or if event-driven triggers would suffice.",
            })

    # Check 2: Overly permissive permissions
    if "permissions:" not in content:
        # No permissions block = defaults to read-all for most triggers
        pass  # This is actually fine for most cases
    else:
        if "permissions: write-all" in content or "permissions:\n  contents: write" in content:
            if "pull_request:" in content and "pull_request_target:" not in content:
                issues.append({
                    "severity": "high",
                    "category": "security",
                    "title": "Write permissions on pull_request trigger",
                    "description": (
                        f"Workflow '{filepath}' has write permissions with pull_request trigger. "
                        "This could allow PRs from forks to modify repository contents."
                    ),
                    "file_path": filepath,
                    "recommendation": "Use pull_request_target for write operations or reduce permissions.",
                })

    # Check 3: Running on untrusted input without checkout protection
    if "pull_request:" in content or "pull_request_target:" in content:
        if "actions/checkout@" in content:
            # Check if it's checking out the PR head (potentially untrusted)
            if "ref: ${{ github.event.pull_request.head.sha }}" in content:
                if "permissions:" in content and "write" in content.lower():
                    issues.append({
                        "severity": "critical",
                        "category": "security",
                        "title": "Checkout of untrusted PR code with write permissions",
                        "description": (
                            f"Workflow '{filepath}' checks out PR head code and has write permissions. "
                            "This is a known security anti-pattern that can lead to repository compromise."
                        ),
                        "file_path": filepath,
                        "recommendation": "Separate trusted and untrusted workflows, or use read-only permissions.",
                    })

    # Check 4: Secrets in workflow outputs/logs
    dangerous_patterns = [
        (r'\$\{\{\s*secrets\.[^}]+\s*\}\}.*>>', "Secret value redirected to file"),
        (r'echo.*\$\{\{\s*secrets\.[^}]+\s*\}\}', "Secret value echoed (may appear in logs)"),
    ]
    for pattern, desc in dangerous_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            issues.append({
                "severity": "high",
                "category": "security",
                "title": f"Potential secret exposure: {desc}",
                "description": f"Workflow '{filepath}' may expose secrets in logs or files.",
                "file_path": filepath,
                "recommendation": "Use secrets only in env vars or action inputs, never echo or redirect.",
            })

    return issues


def _estimate_cron_frequency(cron: str) -> int:
    """Estimate how many times per day a cron expression runs."""
    parts = cron.strip().split()
    if len(parts) != 5:
        return 0  # Invalid cron

    minute, hour, day, month, dow = parts

    # Simple estimation
    runs_per_hour = 1
    if minute.startswith('*/'):
        interval = int(minute[2:])
        runs_per_hour = 60 // interval
    elif minute == '*':
        runs_per_hour = 60
    elif ',' in minute:
        runs_per_hour = len(minute.split(','))

    hours_per_day = 1
    if hour.startswith('*/'):
        interval = int(hour[2:])
        hours_per_day = 24 // interval
    elif hour == '*':
        hours_per_day = 24
    elif ',' in hour:
        hours_per_day = len(hour.split(','))

    return runs_per_hour * hours_per_day


def print_workflow_audit_results(issues: list[dict]) -> bool:
    """Print workflow audit results. Returns True if blocking issues found."""
    if not issues:
        return False

    print("\n" + "=" * 70)
    print("GITHUB ACTIONS WORKFLOW AUDIT")
    print("=" * 70)

    critical_count = sum(1 for i in issues if i['severity'] == 'critical')
    high_count = sum(1 for i in issues if i['severity'] == 'high')

    print(f"\nFound {len(issues)} issue(s): {critical_count} critical, {high_count} high")
    print("-" * 40)

    for issue in issues:
        severity_icon = {
            "critical": "[CRITICAL]",
            "high": "[HIGH]    ",
            "medium": "[MEDIUM]  ",
            "low": "[LOW]     ",
        }.get(issue['severity'], "[INFO]    ")

        print(f"\n  {severity_icon} {issue['title']}")
        print(f"              File: {issue['file_path']}")
        print(f"              {issue['description'][:200]}")
        if issue.get('recommendation'):
            print(f"              Fix: {issue['recommendation']}")

    if critical_count > 0:
        print("\n" + "!" * 70)
        print("BLOCKING: Critical workflow issues must be fixed before commit")
        print("!" * 70)
        return True

    return False


def get_staged_files() -> tuple[list[str], list[str], list[str]]:
    """
    Get lists of staged files by status.

    Returns:
        Tuple of (modified, added, deleted) file lists
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get staged files: {e}")
        return [], [], []

    modified = []
    added = []
    deleted = []

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            status, filepath = parts[0], parts[1]
            if status == "A":
                added.append(filepath)
            elif status == "D":
                deleted.append(filepath)
            elif status.startswith("M") or status.startswith("R"):
                modified.append(filepath)

    return modified, added, deleted


def get_staged_diff() -> str:
    """Get the full diff of staged changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get staged diff: {e}")
        return ""


def get_current_branch() -> str:
    """Get the current branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def save_review_result(result, context: ChangeContext) -> None:
    """Save review result to history for audit trail."""
    REVIEW_HISTORY_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = REVIEW_HISTORY_DIR / f"review_{timestamp}.json"

    record = {
        "timestamp": datetime.now().isoformat(),
        "branch": context.branch_name,
        "files_changed": context.files_changed,
        "files_added": context.files_added,
        "files_deleted": context.files_deleted,
        "tier_used": result.tier_used.value,
        "models_used": result.models_used,
        "issues_count": len(result.issues),
        "blocking_issues_count": len(result.blocking_issues),
        "consensus_issues_count": len(result.consensus_issues),
        "overall_confidence": result.overall_confidence,
        "proceed_recommended": result.proceed_recommended,
        "summary": result.summary,
        "issues": [
            {
                "id": issue.id,
                "severity": issue.severity.value,
                "category": issue.category.value,
                "title": issue.title,
                "description": issue.description,
                "file_path": issue.file_path,
                "consensus_count": issue.consensus_count,
            }
            for issue in result.issues
        ],
    }

    with open(filename, "w") as f:
        json.dump(record, f, indent=2)

    logger.info(f"Review result saved to {filename}")


def print_review_summary(result) -> None:
    """Print a formatted summary of the review."""
    print("\n" + "=" * 70)
    print("EXTERNAL MODEL CODE REVIEW RESULTS")
    print("=" * 70)

    print(f"\nTier: {result.tier_used.value.upper()}")
    print(f"Models: {', '.join(result.models_used)}")
    print(f"Confidence: {result.overall_confidence:.0%}")

    if result.issues:
        print(f"\nIssues Found: {len(result.issues)}")
        print("-" * 40)

        for issue in result.issues:
            severity_icon = {
                IssueSeverity.CRITICAL: "[CRITICAL]",
                IssueSeverity.HIGH: "[HIGH]    ",
                IssueSeverity.MEDIUM: "[MEDIUM]  ",
                IssueSeverity.LOW: "[LOW]     ",
                IssueSeverity.INFO: "[INFO]    ",
            }

            consensus = f"({issue.consensus_count} reviewers)" if issue.consensus_count > 1 else ""
            print(f"  {severity_icon[issue.severity]} {issue.title} {consensus}")
            if issue.file_path:
                print(f"              File: {issue.file_path}")
    else:
        print("\nNo issues found.")

    if result.blocking_issues:
        print("\n" + "!" * 70)
        print(f"BLOCKING: {len(result.blocking_issues)} issues must be addressed before commit")
        print("!" * 70)
        for issue in result.blocking_issues:
            print(f"  - {issue.title}")
            print(f"    {issue.description[:100]}...")

    print("\n" + "-" * 70)
    if result.proceed_recommended:
        print("Recommendation: PROCEED WITH COMMIT")
    else:
        print("Recommendation: FIX ISSUES BEFORE COMMIT")
    print("-" * 70 + "\n")


async def run_review() -> int:
    """
    Run the pre-commit review.

    Returns:
        Exit code (0 = success, 1 = blocked, 2 = error)
    """
    # Get staged changes
    modified, added, deleted = get_staged_files()

    if not modified and not added and not deleted:
        print("No staged changes to review.")
        return 0

    total_files = len(modified) + len(added) + len(deleted)
    print(f"\nPre-commit review: {total_files} files staged")
    print(f"  Modified: {len(modified)}, Added: {len(added)}, Deleted: {len(deleted)}")

    # Get diff content
    diff = get_staged_diff()

    all_files = modified + added

    # =========================================================================
    # Phase 1: Static workflow audit (fast, local, no API calls)
    # =========================================================================
    workflow_issues = audit_github_workflows(all_files, diff)
    if print_workflow_audit_results(workflow_issues):
        print("\nCOMMIT BLOCKED: Fix workflow issues before committing.")
        return 1

    # =========================================================================
    # Phase 2: External model reviews (slower, requires API keys)
    # =========================================================================

    # Create change context
    context = ChangeContext(
        files_changed=modified,
        files_added=added,
        files_deleted=deleted,
        diff_content=diff,
        branch_name=get_current_branch(),
    )

    # Check if any security-related files
    if context.is_security_related:
        print("  Security-related files detected - using CRITICAL tier")

    # Run review
    print("\nRunning external model reviews...")
    print("  (GPT-4o, Gemini 1.5 Pro, Codex)")
    print("  This may take a moment...\n")

    try:
        orchestrator = ReviewOrchestrator()
        result = await orchestrator.review(context)
    except Exception as e:
        logger.error(f"Review system error: {e}")
        print(f"\nReview system error: {e}")
        print("Commit allowed (review system unavailable)")
        return 2

    # Print results
    print_review_summary(result)

    # Save to history
    save_review_result(result, context)

    # Determine exit code
    if result.blocking_issues:
        print("COMMIT BLOCKED: Fix the blocking issues above before committing.")
        print("After fixes, run: git add . && python scripts/pre_commit_review.py")
        return 1
    elif not result.proceed_recommended:
        print("WARNING: Review did not recommend proceeding, but no blocking issues.")
        print("Consider addressing the issues above.")
        # Still allow commit but warn
        return 0
    else:
        print("Review passed. Commit allowed.")
        return 0


def main():
    """Main entry point."""
    try:
        exit_code = asyncio.run(run_review())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nReview cancelled.")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\nUnexpected error: {e}")
        print("Commit allowed (review system error)")
        sys.exit(2)


if __name__ == "__main__":
    main()

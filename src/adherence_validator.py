"""
Adherence Validator Module for WF-034 Phase 2

Validates workflow adherence using session transcripts and workflow logs.
Detects patterns like parallel execution, third-party reviews, agent verification, etc.
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class CheckResult:
    """Result of a single adherence check."""
    name: str
    passed: bool
    confidence: str  # high, medium, low
    explanation: str
    evidence: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class AdherenceReport:
    """Complete adherence validation report."""
    workflow_id: str
    task: str
    timestamp: datetime
    score: float  # 0.0-1.0
    checks: Dict[str, CheckResult] = field(default_factory=dict)
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def add_check(self, check: CheckResult):
        """Add a check result to the report."""
        self.checks[check.name] = check
        if not check.passed and check.confidence == "high":
            self.critical_issues.append(f"{check.name}: {check.explanation}")
        elif not check.passed and check.confidence == "medium":
            self.warnings.append(f"{check.name}: {check.explanation}")


class AdherenceValidator:
    """
    Validates workflow adherence using session transcripts and workflow logs.

    Checks 7 criteria:
    1. Plan agent usage
    2. Parallel execution (single message with multiple Task calls)
    3. Third-party model reviews
    4. Agent output verification (Read tool after Task completion)
    5. Status check frequency
    6. Required items completion
    7. Learnings detail

    Usage:
        validator = AdherenceValidator(
            session_log_path=Path(".orchestrator/sessions/session.jsonl"),
            workflow_log_path=Path(".workflow_log.jsonl")
        )
        report = validator.validate(workflow_id="wf_123")
        print(format_adherence_report(report))
    """

    def __init__(
        self,
        session_log_path: Optional[Path] = None,
        workflow_log_path: Optional[Path] = None
    ):
        """
        Initialize AdherenceValidator.

        Args:
            session_log_path: Path to session transcript (JSONL)
            workflow_log_path: Path to workflow event log (JSONL)
        """
        self.session_log_path = session_log_path
        self.workflow_log_path = workflow_log_path or Path(".workflow_log.jsonl")

        self.session_events = []
        self.workflow_events = []

    def load_logs(self):
        """Load session and workflow logs."""
        # Load session log if available
        if self.session_log_path and self.session_log_path.exists():
            with open(self.session_log_path, 'r') as f:
                for line in f:
                    if line.strip():
                        self.session_events.append(json.loads(line))

        # Load workflow log
        if self.workflow_log_path.exists():
            with open(self.workflow_log_path, 'r') as f:
                for line in f:
                    if line.strip():
                        self.workflow_events.append(json.loads(line))

    def validate(self, workflow_id: str, task: str = "") -> AdherenceReport:
        """
        Validate workflow adherence.

        Args:
            workflow_id: Workflow ID to validate
            task: Task description

        Returns:
            AdherenceReport with validation results
        """
        self.load_logs()

        report = AdherenceReport(
            workflow_id=workflow_id,
            task=task,
            timestamp=datetime.now()
        )

        # Run all checks
        report.add_check(self.check_plan_agent_usage())
        report.add_check(self.check_parallel_execution())
        report.add_check(self.check_reviews())
        report.add_check(self.check_agent_verification())
        report.add_check(self.check_status_frequency())
        report.add_check(self.check_required_items())
        report.add_check(self.check_learnings_detail())

        # Calculate score
        passed_checks = sum(1 for c in report.checks.values() if c.passed)
        total_checks = len(report.checks)
        report.score = passed_checks / total_checks if total_checks > 0 else 0.0

        # Generate recommendations
        for check in report.checks.values():
            if not check.passed:
                report.recommendations.extend(check.recommendations)

        return report

    def check_plan_agent_usage(self) -> CheckResult:
        """Check if Plan agent was used before implementation."""
        # Look for Task tool calls with subagent_type="Plan"
        plan_agent_used = False
        evidence = []

        for event in self.session_events:
            if event.get("type") == "tool_use":
                data = event.get("data", {})
                if data.get("tool") == "Task" and data.get("params", {}).get("subagent_type") == "Plan":
                    plan_agent_used = True
                    evidence.append(f"Plan agent used: {data.get('params', {}).get('description', 'N/A')}")

        if plan_agent_used:
            return CheckResult(
                name="plan_agent_usage",
                passed=True,
                confidence="high",
                explanation="Plan agent was used before implementation",
                evidence=evidence
            )
        else:
            return CheckResult(
                name="plan_agent_usage",
                passed=False,
                confidence="medium",
                explanation="No Plan agent usage detected",
                recommendations=[
                    "Use Plan agent (subagent_type='Plan') for complex implementations",
                    "Plan agent helps break down tasks before implementation"
                ]
            )

    def check_parallel_execution(self) -> CheckResult:
        """Check if parallel agents were launched correctly (single message with multiple Task calls)."""
        # Look for multiple Task tool calls in the same message/timestamp
        task_groups = defaultdict(list)

        for event in self.session_events:
            if event.get("type") == "tool_use":
                data = event.get("data", {})
                if data.get("tool") == "Task":
                    timestamp = event.get("timestamp", "")
                    task_groups[timestamp].append(data.get("params", {}).get("description", ""))

        # Check for parallel execution (multiple tasks in same message)
        parallel_count = sum(1 for tasks in task_groups.values() if len(tasks) > 1)
        sequential_count = sum(1 for tasks in task_groups.values() if len(tasks) == 1)

        if parallel_count > 0:
            evidence = []
            for timestamp, tasks in task_groups.items():
                if len(tasks) > 1:
                    evidence.append(f"{len(tasks)} tasks launched in parallel at {timestamp}")

            return CheckResult(
                name="parallel_execution",
                passed=True,
                confidence="high",
                explanation=f"Parallel execution detected: {parallel_count} parallel launches",
                evidence=evidence
            )
        elif sequential_count > 0:
            return CheckResult(
                name="parallel_execution",
                passed=False,
                confidence="high",
                explanation=f"Sequential execution detected: {sequential_count} separate Task launches",
                evidence=[f"{sequential_count} Task calls in separate messages"],
                recommendations=[
                    "Launch parallel agents in SINGLE message with MULTIPLE Task tool calls",
                    "Example: Send one message with Task(...) + Task(...) + Task(...)",
                    "Avoid sending Task calls in separate sequential messages"
                ]
            )
        else:
            return CheckResult(
                name="parallel_execution",
                passed=True,
                confidence="low",
                explanation="No Task tool calls detected (may not be applicable)",
                evidence=[]
            )

    def check_reviews(self) -> CheckResult:
        """Check if third-party model reviews were performed."""
        reviews = []

        for event in self.workflow_events:
            if event.get("type") == "review_completed":
                model = event.get("model", "unknown")
                result = event.get("result", "unknown")
                reviews.append(f"{model}: {result}")

        if len(reviews) >= 3:  # At least 3 reviews
            return CheckResult(
                name="third_party_reviews",
                passed=True,
                confidence="high",
                explanation=f"{len(reviews)} third-party model reviews performed",
                evidence=reviews
            )
        elif len(reviews) > 0:
            return CheckResult(
                name="third_party_reviews",
                passed=False,
                confidence="medium",
                explanation=f"Only {len(reviews)} reviews performed (recommended: 5)",
                evidence=reviews,
                recommendations=[
                    "Run all 5 third-party model reviews for comprehensive coverage",
                    "Use 'orchestrator review' command or /review skill"
                ]
            )
        else:
            return CheckResult(
                name="third_party_reviews",
                passed=False,
                confidence="high",
                explanation="No third-party model reviews detected",
                recommendations=[
                    "Run third-party model reviews for code quality validation",
                    "Reviews provide external perspectives and catch issues"
                ]
            )

    def check_agent_verification(self) -> CheckResult:
        """Check if agent output was verified by reading files."""
        # Look for Read tool calls after Task completions
        verifications = 0
        evidence = []

        # Track Task completions
        for i, event in enumerate(self.session_events):
            if event.get("type") == "tool_result" and event.get("data", {}).get("tool") == "Task":
                # Look for Read tool calls in next few events
                for j in range(i + 1, min(i + 5, len(self.session_events))):
                    next_event = self.session_events[j]
                    if next_event.get("type") == "tool_use" and next_event.get("data", {}).get("tool") == "Read":
                        verifications += 1
                        file_path = next_event.get("data", {}).get("params", {}).get("file_path", "")
                        evidence.append(f"Verified: {file_path}")
                        break

        if verifications > 0:
            return CheckResult(
                name="agent_verification",
                passed=True,
                confidence="high",
                explanation=f"{verifications} agent output verifications detected",
                evidence=evidence[:5]  # Limit evidence to first 5
            )
        else:
            return CheckResult(
                name="agent_verification",
                passed=False,
                confidence="medium",
                explanation="No agent output verification detected",
                recommendations=[
                    "Always read files after agent completions to verify output",
                    "Don't trust agent summaries - verify by reading actual files"
                ]
            )

    def check_status_frequency(self) -> CheckResult:
        """Check if 'orchestrator status' was called frequently."""
        status_calls = 0

        for event in self.session_events:
            if event.get("type") == "command":
                command = event.get("data", {}).get("command", "")
                if "orchestrator status" in command:
                    status_calls += 1

        if status_calls >= 5:
            return CheckResult(
                name="status_checks",
                passed=True,
                confidence="high",
                explanation=f"Frequent status checks: {status_calls} calls",
                evidence=[f"{status_calls} 'orchestrator status' calls"]
            )
        elif status_calls > 0:
            return CheckResult(
                name="status_checks",
                passed=False,
                confidence="low",
                explanation=f"Infrequent status checks: only {status_calls} calls",
                recommendations=[
                    "Run 'orchestrator status' before each action",
                    "Regular status checks prevent workflow drift"
                ]
            )
        else:
            return CheckResult(
                name="status_checks",
                passed=True,
                confidence="low",
                explanation="No status checks detected (session log may be incomplete)",
                evidence=[]
            )

    def check_required_items(self) -> CheckResult:
        """Check if all required items were completed (not skipped without justification)."""
        skipped_items = []

        for event in self.workflow_events:
            if event.get("type") == "item_skipped":
                item_id = event.get("item_id", "unknown")
                reason = event.get("reason", "")
                if not reason or len(reason) < 10:  # No justification
                    skipped_items.append(item_id)

        if len(skipped_items) == 0:
            return CheckResult(
                name="required_items",
                passed=True,
                confidence="high",
                explanation="All required items completed (no unjustified skips)",
                evidence=[]
            )
        else:
            return CheckResult(
                name="required_items",
                passed=False,
                confidence="high",
                explanation=f"{len(skipped_items)} required items skipped without justification",
                evidence=[f"Skipped: {item}" for item in skipped_items],
                recommendations=[
                    "Complete all required items or provide detailed justification for skips",
                    "Required items are essential for workflow quality"
                ]
            )

    def check_learnings_detail(self) -> CheckResult:
        """Check if learnings were documented with sufficient detail."""
        learning_events = []

        for event in self.workflow_events:
            if event.get("type") == "item_completed" and "learning" in event.get("item_id", "").lower():
                notes = event.get("notes", "")
                learning_events.append(notes)

        if not learning_events:
            return CheckResult(
                name="learnings_detail",
                passed=False,
                confidence="medium",
                explanation="No learnings documented",
                recommendations=[
                    "Document learnings in LEARN phase",
                    "Capture what went well, challenges, and improvements"
                ]
            )

        # Check detail level (simple heuristic: length of notes)
        total_length = sum(len(notes) for notes in learning_events)
        avg_length = total_length / len(learning_events) if learning_events else 0

        if avg_length > 100:  # Detailed (>100 chars per learning)
            return CheckResult(
                name="learnings_detail",
                passed=True,
                confidence="high",
                explanation=f"Detailed learnings documented ({len(learning_events)} learnings, avg {int(avg_length)} chars)",
                evidence=[f"{len(learning_events)} learning entries"]
            )
        else:
            return CheckResult(
                name="learnings_detail",
                passed=False,
                confidence="medium",
                explanation=f"Brief learnings documented (avg {int(avg_length)} chars per learning)",
                recommendations=[
                    "Provide more detailed learnings (aim for 100+ chars per learning)",
                    "Include specific examples, challenges, and insights"
                ]
            )


def format_adherence_report(report: AdherenceReport) -> str:
    """
    Format adherence report for display.

    Args:
        report: AdherenceReport to format

    Returns:
        Formatted report string
    """
    output = []
    output.append("=" * 60)
    output.append("Workflow Adherence Validation")
    output.append("=" * 60)
    output.append(f"Workflow: {report.workflow_id}")
    if report.task:
        output.append(f"Task: {report.task}")
    output.append(f"Timestamp: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    output.append("")

    # Check results
    for check_name, check in report.checks.items():
        symbol = "✓" if check.passed else "✗"
        output.append(f"{symbol} {check.name}: {'PASS' if check.passed else 'FAIL'}")
        output.append(f"  {check.explanation}")
        if check.evidence:
            output.append(f"  Evidence: {', '.join(check.evidence[:3])}")
        if not check.passed and check.recommendations:
            output.append(f"  Recommendation: {check.recommendations[0]}")
        output.append("")

    # Score
    output.append(f"ADHERENCE SCORE: {report.score * 100:.0f}% ({sum(1 for c in report.checks.values() if c.passed)}/{len(report.checks)} criteria met)")
    output.append("")

    # Critical issues
    if report.critical_issues:
        output.append("CRITICAL ISSUES:")
        for issue in report.critical_issues:
            output.append(f"  - {issue}")
        output.append("")

    # Recommendations
    if report.recommendations:
        output.append("RECOMMENDATIONS:")
        for i, rec in enumerate(report.recommendations[:5], 1):  # Limit to top 5
            output.append(f"  {i}. {rec}")
        output.append("")

    output.append("=" * 60)
    return "\n".join(output)


def find_session_log_for_workflow(workflow_id: str, sessions_dir: Path = None) -> Optional[Path]:
    """
    Find session log file for a given workflow ID.

    Args:
        workflow_id: Workflow ID
        sessions_dir: Directory containing session logs

    Returns:
        Path to session log file, or None if not found
    """
    if sessions_dir is None:
        sessions_dir = Path(".orchestrator/sessions")

    if not sessions_dir.exists():
        return None

    # Search for workflow_id in session log files
    for log_file in sessions_dir.glob("*.jsonl"):
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    event = json.loads(line)
                    if event.get("data", {}).get("workflow_id") == workflow_id:
                        return log_file

    return None

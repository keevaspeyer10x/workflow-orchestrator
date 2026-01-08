"""
GitHub Issue Creator for Escalations

Creates user-friendly GitHub issues with:
- Plain-English explanation of the conflict
- Clear options with tradeoffs
- Recommendation with reasoning
- Simple response format (A, B, C, explain, custom)
"""

import logging
import os
import subprocess
from typing import Optional

from .schema import (
    Escalation,
    EscalationOption,
    EscalationPriority,
    TechnicalDetails,
)

logger = logging.getLogger(__name__)


class IssueCreator:
    """
    Creates GitHub issues for escalations.

    Uses plain English to make decisions easy for users.
    """

    def __init__(
        self,
        repo: Optional[str] = None,
        use_gh_cli: bool = True,
    ):
        """
        Initialize issue creator.

        Args:
            repo: Repository in owner/repo format (auto-detected if not provided)
            use_gh_cli: Use GitHub CLI (gh) for issue creation
        """
        self.repo = repo or self._detect_repo()
        self.use_gh_cli = use_gh_cli

    def create_issue(self, escalation: Escalation) -> tuple[int, str]:
        """
        Create a GitHub issue for the escalation.

        Args:
            escalation: The escalation to create an issue for

        Returns:
            Tuple of (issue_number, issue_url)
        """
        logger.info(f"Creating escalation issue for {escalation.escalation_id}")

        # Generate issue content
        title = self._generate_title(escalation)
        body = self._generate_body(escalation)
        labels = self._generate_labels(escalation)

        # Create issue
        if self.use_gh_cli:
            issue_number, issue_url = self._create_via_gh_cli(title, body, labels)
        else:
            # Fallback to API (would need GitHub token)
            raise NotImplementedError("GitHub API creation not yet implemented")

        # Update escalation
        escalation.issue_number = issue_number
        escalation.issue_url = issue_url

        logger.info(f"Created issue #{issue_number}: {issue_url}")
        return issue_number, issue_url

    def _detect_repo(self) -> str:
        """Detect repository from git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Parse git@github.com:owner/repo.git or https://github.com/owner/repo.git
                if "github.com" in url:
                    # Remove protocol and .git suffix
                    url = url.replace("git@github.com:", "")
                    url = url.replace("https://github.com/", "")
                    url = url.replace(".git", "")
                    return url
        except Exception as e:
            logger.warning(f"Could not detect repo: {e}")

        return os.environ.get("GITHUB_REPOSITORY", "")

    def _generate_title(self, escalation: Escalation) -> str:
        """Generate issue title."""
        # Priority emoji
        emoji = {
            EscalationPriority.CRITICAL: "🚨",
            EscalationPriority.HIGH: "⚠️",
            EscalationPriority.STANDARD: "🤔",
            EscalationPriority.LOW: "💭",
        }.get(escalation.priority, "🤔")

        # Short description from trigger
        if escalation.triggers:
            trigger = escalation.triggers[0].value.replace("_", " ").title()
        else:
            trigger = "Decision Needed"

        return f"{emoji} {trigger}: Need Your Input"

    def _generate_body(self, escalation: Escalation) -> str:
        """Generate issue body with plain-English options."""
        lines = []

        # Header
        lines.append("## 🤔 Need Your Input")
        lines.append("")
        lines.append(self._estimate_time(escalation))
        lines.append("")

        # What happened
        lines.append("While combining work from your Claude agents, I found a decision that needs your judgment.")
        lines.append("")
        lines.append("---")
        lines.append("")

        # What happened section
        lines.append("### What Happened")
        lines.append("")
        lines.append(escalation.trigger_reason or self._describe_conflict(escalation))
        lines.append("")
        lines.append("---")
        lines.append("")

        # Options
        lines.append("### Your Options")
        lines.append("")

        for option in escalation.options:
            lines.extend(self._format_option(option))
            lines.append("---")
            lines.append("")

        # Recommendation
        if escalation.recommendation:
            lines.append("### My Recommendation")
            lines.append("")
            rec_option = next(
                (o for o in escalation.options if o.option_id == escalation.recommendation),
                None
            )
            if rec_option:
                lines.append(f"Based on your codebase, **Option {escalation.recommendation}** ({rec_option.title}) "
                           f"is recommended.")
            lines.append("")
            if escalation.recommendation_reason:
                lines.append(escalation.recommendation_reason)
                lines.append("")
            lines.append(f"**Confidence:** {int(escalation.confidence * 100)}%")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Response instructions
        lines.append("### Your Response")
        lines.append("")
        lines.append("Reply with one of:")
        lines.append("")

        for option in escalation.options:
            rec = " (recommended)" if option.is_recommended else ""
            lines.append(f"- `{option.option_id}` - {option.title}{rec}")

        lines.append("- `explain` - Show me more technical details")
        lines.append("- `custom: <your preference>` - Tell me what you want instead")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Technical details (collapsed)
        lines.append("<details>")
        lines.append("<summary>📋 Technical Details (click to expand)</summary>")
        lines.append("")
        lines.extend(self._format_technical_details(escalation))
        lines.append("")
        lines.append("</details>")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Escalation ID: `{escalation.escalation_id}`*")

        return "\n".join(lines)

    def _estimate_time(self, escalation: Escalation) -> str:
        """Estimate time needed based on options."""
        if len(escalation.options) <= 2:
            return "**Time needed:** ~30 seconds"
        elif len(escalation.options) <= 4:
            return "**Time needed:** ~1 minute"
        else:
            return "**Time needed:** ~2 minutes"

    def _describe_conflict(self, escalation: Escalation) -> str:
        """Generate plain-English description of the conflict."""
        if escalation.intent_analysis and len(escalation.intent_analysis.intents) >= 2:
            intent1 = escalation.intent_analysis.intents[0]
            intent2 = escalation.intent_analysis.intents[1]
            return (f"Two features were built with different approaches:\n\n"
                   f"| Feature | Agent |\n"
                   f"|---------|-------|\n"
                   f"| {intent1.primary_intent} | {intent1.agent_id} |\n"
                   f"| {intent2.primary_intent} | {intent2.agent_id} |")

        if escalation.triggers:
            trigger = escalation.triggers[0].value.replace("_", " ")
            return f"A conflict was detected involving: {trigger}"

        return "Multiple agents made changes that need to be reconciled."

    def _format_option(self, option: EscalationOption) -> list[str]:
        """Format a single option."""
        lines = []

        # Header with recommendation marker
        rec = " ✓ Recommended" if option.is_recommended else ""
        lines.append(f"#### [{option.option_id}] {option.title}{rec}")
        lines.append("")

        # Description
        lines.append("**What it means:**")
        lines.append(option.description)
        lines.append("")

        # Tradeoffs
        if option.tradeoffs:
            lines.append("**Tradeoffs:**")
            for tradeoff in option.tradeoffs:
                lines.append(f"- {tradeoff}")
            lines.append("")

        # Risk level
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(option.risk_level, "🟡")
        lines.append(f"**Risk level:** {risk_emoji} {option.risk_level.title()}")
        lines.append("")

        return lines

    def _format_technical_details(self, escalation: Escalation) -> list[str]:
        """Format technical details section."""
        lines = []

        details = escalation.technical_details

        if details and details.files_involved:
            lines.append("### Files Involved")
            lines.append("")
            for f in details.files_involved[:20]:  # Limit to 20 files
                lines.append(f"- `{f}`")
            if len(details.files_involved) > 20:
                lines.append(f"- ... and {len(details.files_involved) - 20} more")
            lines.append("")

        if details and details.architectural_impact:
            lines.append("### Architectural Impact")
            lines.append("")
            lines.append(details.architectural_impact)
            lines.append("")

        if details and details.code_diff:
            lines.append("### Code Changes")
            lines.append("")
            lines.append("```diff")
            # Limit diff to first 100 lines
            diff_lines = details.code_diff.split("\n")[:100]
            lines.extend(diff_lines)
            if len(details.code_diff.split("\n")) > 100:
                lines.append("... (diff truncated)")
            lines.append("```")
            lines.append("")

        # Agent info from candidates
        if escalation.candidates:
            lines.append("### Resolution Candidates")
            lines.append("")
            for candidate in escalation.candidates:
                lines.append(f"- **{candidate.candidate_id}**: {candidate.strategy}")
                lines.append(f"  - Score: {candidate.total_score:.2f}")
                lines.append(f"  - Build: {'✓' if candidate.build_passed else '✗'}")
                lines.append(f"  - Tests: {candidate.tests_passed}P/{candidate.tests_failed}F")
            lines.append("")

        return lines

    def _generate_labels(self, escalation: Escalation) -> list[str]:
        """Generate issue labels."""
        labels = ["claude-escalation"]

        # Priority
        labels.append(f"priority:{escalation.priority.value}")

        # Triggers
        for trigger in escalation.triggers[:3]:  # Limit labels
            labels.append(f"trigger:{trigger.value}")

        return labels

    def _create_via_gh_cli(
        self,
        title: str,
        body: str,
        labels: list[str],
    ) -> tuple[int, str]:
        """Create issue using GitHub CLI."""
        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
        ]

        if self.repo:
            cmd.extend(["--repo", self.repo])

        for label in labels:
            cmd.extend(["--label", label])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse issue URL from output
            issue_url = result.stdout.strip()

            # Extract issue number from URL
            # URL format: https://github.com/owner/repo/issues/123
            issue_number = int(issue_url.split("/")[-1])

            return issue_number, issue_url

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create issue: {e.stderr}")
            raise RuntimeError(f"Failed to create GitHub issue: {e.stderr}")

    def add_comment(self, issue_number: int, comment: str) -> bool:
        """Add a comment to an existing issue."""
        cmd = [
            "gh", "issue", "comment",
            str(issue_number),
            "--body", comment,
        ]

        if self.repo:
            cmd.extend(["--repo", self.repo])

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add comment: {e.stderr}")
            return False

    def close_issue(self, issue_number: int, reason: str = "completed") -> bool:
        """Close an escalation issue."""
        cmd = [
            "gh", "issue", "close",
            str(issue_number),
            "--reason", reason,
        ]

        if self.repo:
            cmd.extend(["--repo", self.repo])

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to close issue: {e.stderr}")
            return False

"""
Escalation Response Handler

Processes user responses to escalations:
- Option selection (A, B, C, D)
- Explain request
- Custom preference
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from .schema import (
    Escalation,
    EscalationOption,
    EscalationResult,
    EscalationStatus,
)
from .issue_creator import IssueCreator

logger = logging.getLogger(__name__)


class ResponseHandler:
    """
    Handles user responses to escalations.

    Supports:
    - "A", "B", "C", "D" - Select that option
    - "explain" - Post detailed technical explanation
    - "custom: ..." - Parse custom preference
    """

    def __init__(self, issue_creator: Optional[IssueCreator] = None):
        self.issue_creator = issue_creator or IssueCreator()

    def process_response(
        self,
        escalation: Escalation,
        response: str,
    ) -> EscalationResult:
        """
        Process a user's response to an escalation.

        Args:
            escalation: The escalation being responded to
            response: The user's response text

        Returns:
            EscalationResult with outcome
        """
        logger.info(f"Processing response for {escalation.escalation_id}: {response[:50]}")

        # Normalize response
        response = response.strip()

        # Record response
        escalation.response = response
        escalation.response_at = datetime.now(timezone.utc)

        # Parse response type
        if self._is_option_selection(response, escalation):
            return self._handle_option_selection(response, escalation)

        elif response.lower() == "explain":
            return self._handle_explain_request(escalation)

        elif response.lower().startswith("custom:"):
            custom_pref = response[7:].strip()
            return self._handle_custom_preference(escalation, custom_pref)

        else:
            return self._handle_unknown_response(escalation, response)

    def _is_option_selection(self, response: str, escalation: Escalation) -> bool:
        """Check if response is an option selection."""
        response_upper = response.upper().strip()

        # Check if it matches any option ID
        option_ids = [o.option_id.upper() for o in escalation.options]
        return response_upper in option_ids

    def _handle_option_selection(
        self,
        response: str,
        escalation: Escalation,
    ) -> EscalationResult:
        """Handle option selection (A, B, C, D)."""
        option_id = response.upper().strip()

        # Find selected option
        winner = next(
            (o for o in escalation.options if o.option_id.upper() == option_id),
            None
        )

        if not winner:
            logger.error(f"Option {option_id} not found in escalation")
            return EscalationResult(resolved=False, awaiting_response=True)

        # Get losing options for feature porting
        losers = [o for o in escalation.options if o.option_id.upper() != option_id]

        # Update escalation status
        escalation.status = EscalationStatus.RESOLVED
        escalation.resolved_at = datetime.now(timezone.utc)

        # Post confirmation comment
        self._post_selection_confirmation(escalation, winner, losers)

        logger.info(f"Escalation {escalation.escalation_id} resolved with option {option_id}")

        return EscalationResult(
            resolved=True,
            awaiting_response=False,
            winner=winner,
            winning_candidate=winner.candidate,
            ported_features=[o.title for o in losers],
        )

    def _handle_explain_request(self, escalation: Escalation) -> EscalationResult:
        """Handle explain request - post technical details."""
        logger.info(f"Posting technical details for {escalation.escalation_id}")

        # Update status
        escalation.status = EscalationStatus.AWAITING_INFO

        # Post detailed comment
        if escalation.issue_number:
            comment = self._generate_technical_explanation(escalation)
            self.issue_creator.add_comment(escalation.issue_number, comment)

        return EscalationResult(
            resolved=False,
            awaiting_response=True,
        )

    def _handle_custom_preference(
        self,
        escalation: Escalation,
        custom_pref: str,
    ) -> EscalationResult:
        """Handle custom preference from user."""
        logger.info(f"Processing custom preference: {custom_pref[:50]}")

        # For now, we note the preference and mark as needing follow-up
        # Full implementation would generate a new candidate based on the preference

        escalation.status = EscalationStatus.AWAITING_INFO

        # Post acknowledgment
        if escalation.issue_number:
            comment = self._generate_custom_acknowledgment(custom_pref)
            self.issue_creator.add_comment(escalation.issue_number, comment)

        return EscalationResult(
            resolved=False,
            awaiting_response=True,
            custom=True,
            custom_preference=custom_pref,
        )

    def _handle_unknown_response(
        self,
        escalation: Escalation,
        response: str,
    ) -> EscalationResult:
        """Handle unknown/unclear response."""
        logger.warning(f"Unknown response: {response[:50]}")

        # Try to parse it anyway
        # Check for partial matches
        for option in escalation.options:
            if option.option_id.lower() in response.lower():
                return self._handle_option_selection(option.option_id, escalation)
            if option.title.lower() in response.lower():
                return self._handle_option_selection(option.option_id, escalation)

        # Post clarification request
        if escalation.issue_number:
            comment = self._generate_clarification_request(escalation)
            self.issue_creator.add_comment(escalation.issue_number, comment)

        return EscalationResult(
            resolved=False,
            awaiting_response=True,
        )

    def _post_selection_confirmation(
        self,
        escalation: Escalation,
        winner: EscalationOption,
        losers: list[EscalationOption],
    ):
        """Post confirmation comment for selection."""
        if not escalation.issue_number:
            return

        lines = []
        lines.append(f"## ✅ Selection Confirmed: Option {winner.option_id}")
        lines.append("")
        lines.append(f"You selected **{winner.title}**.")
        lines.append("")

        if losers:
            lines.append("I'll now:")
            lines.append(f"1. Apply the {winner.title} approach")
            lines.append("2. Port any features from the other options that are still needed:")
            for loser in losers:
                lines.append(f"   - {loser.title}")
            lines.append("3. Create a PR for your review")
        else:
            lines.append("I'll create a PR with this approach for your review.")

        lines.append("")
        lines.append("---")
        lines.append("*Processing... I'll update this issue when the PR is ready.*")

        self.issue_creator.add_comment(escalation.issue_number, "\n".join(lines))

    def _generate_technical_explanation(self, escalation: Escalation) -> str:
        """Generate detailed technical explanation."""
        lines = []
        lines.append("## 📋 Technical Details")
        lines.append("")

        # Intent analysis
        if escalation.intent_analysis:
            lines.append("### Agent Intents")
            lines.append("")
            for intent in escalation.intent_analysis.intents:
                lines.append(f"**{intent.agent_id}:**")
                lines.append(f"- Primary: {intent.primary_intent}")
                if intent.hard_constraints:
                    lines.append(f"- Constraints: {len(intent.hard_constraints)} hard requirements")
                lines.append(f"- Confidence: {intent.confidence}")
                lines.append("")

        # Candidates
        if escalation.candidates:
            lines.append("### Resolution Candidates")
            lines.append("")
            for candidate in escalation.candidates:
                lines.append(f"**{candidate.candidate_id}** ({candidate.strategy})")
                lines.append("")
                lines.append(f"| Metric | Value |")
                lines.append(f"|--------|-------|")
                lines.append(f"| Build | {'✓ Passed' if candidate.build_passed else '✗ Failed'} |")
                lines.append(f"| Tests | {candidate.tests_passed} passed, {candidate.tests_failed} failed |")
                lines.append(f"| Lint Score | {candidate.lint_score:.2f} |")
                lines.append(f"| Total Score | {candidate.total_score:.2f} |")
                lines.append("")
                if candidate.files_modified:
                    lines.append(f"Files modified: {len(candidate.files_modified)}")
                    for f in candidate.files_modified[:10]:
                        lines.append(f"- `{f}`")
                    if len(candidate.files_modified) > 10:
                        lines.append(f"- ... and {len(candidate.files_modified) - 10} more")
                lines.append("")
                lines.append("---")
                lines.append("")

        # Technical details
        if escalation.technical_details:
            details = escalation.technical_details

            if details.architectural_impact:
                lines.append("### Architectural Impact")
                lines.append("")
                lines.append(details.architectural_impact)
                lines.append("")

            if details.code_diff:
                lines.append("### Code Diff")
                lines.append("")
                lines.append("```diff")
                # Limit to 200 lines
                diff_lines = details.code_diff.split("\n")[:200]
                lines.extend(diff_lines)
                if len(details.code_diff.split("\n")) > 200:
                    lines.append("... (diff truncated)")
                lines.append("```")
                lines.append("")

        lines.append("---")
        lines.append("*Reply with your selection (A, B, C, etc.) or `custom: <preference>`*")

        return "\n".join(lines)

    def _generate_custom_acknowledgment(self, custom_pref: str) -> str:
        """Generate acknowledgment for custom preference."""
        lines = []
        lines.append("## 🔧 Custom Preference Received")
        lines.append("")
        lines.append(f"I understand you'd prefer: **{custom_pref}**")
        lines.append("")
        lines.append("I'll generate a new resolution based on your preference.")
        lines.append("")
        lines.append("---")
        lines.append("*Processing... I'll update this issue with the new approach.*")

        return "\n".join(lines)

    def _generate_clarification_request(self, escalation: Escalation) -> str:
        """Generate clarification request for unclear response."""
        lines = []
        lines.append("## ❓ Could You Clarify?")
        lines.append("")
        lines.append("I didn't quite understand your response. Please reply with one of:")
        lines.append("")

        for option in escalation.options:
            rec = " (recommended)" if option.is_recommended else ""
            lines.append(f"- `{option.option_id}` - {option.title}{rec}")

        lines.append("- `explain` - Show me more technical details")
        lines.append("- `custom: <your preference>` - Tell me what you want instead")

        return "\n".join(lines)


def parse_github_comment(comment_body: str) -> str:
    """
    Parse a GitHub comment to extract the response.

    Handles:
    - Direct option (just "A")
    - Option in sentence ("I'll go with A")
    - Code blocks with option
    - Custom preferences
    """
    body = comment_body.strip()

    # Direct option selection
    if re.match(r'^[A-Da-d]$', body):
        return body.upper()

    # "explain" command
    if body.lower() == "explain":
        return "explain"

    # Custom preference
    if body.lower().startswith("custom:"):
        return body

    # Try to extract option from sentence
    # "I'll go with A" or "Option B please" or "Let's do C"
    match = re.search(r'\b(?:option\s+)?([A-Da-d])\b', body, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    # If no clear option, return as-is for further processing
    return body

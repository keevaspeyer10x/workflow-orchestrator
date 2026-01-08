"""
Escalation Timeout Handler

Handles timeouts and reminders for escalations:
- Policy-based SLAs (critical, high, standard, low)
- Reminder notifications
- Auto-selection (when allowed)
- Urgent escalation (when auto-select not allowed)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .schema import (
    Escalation,
    EscalationPriority,
    EscalationStatus,
    EscalationResult,
    TimeoutPolicy,
    TIMEOUT_POLICIES,
)
from .issue_creator import IssueCreator

logger = logging.getLogger(__name__)


class TimeoutHandler:
    """
    Handles escalation timeouts with policy-based SLAs.

    Different priorities have different timeout behaviors:
    - Critical: Never auto-select, escalate to team
    - High: Never auto-select, remind frequently
    - Standard: Auto-select after timeout
    - Low: Auto-select after long timeout
    """

    def __init__(
        self,
        issue_creator: Optional[IssueCreator] = None,
        slack_webhook: Optional[str] = None,
        email_handler: Optional[object] = None,
    ):
        self.issue_creator = issue_creator or IssueCreator()
        self.slack_webhook = slack_webhook
        self.email_handler = email_handler

    def check_timeout(self, escalation: Escalation) -> Optional[EscalationResult]:
        """
        Check if an escalation has timed out or needs a reminder.

        Args:
            escalation: The escalation to check

        Returns:
            EscalationResult if auto-selected, None if still pending
        """
        if escalation.status != EscalationStatus.PENDING:
            return None

        policy = escalation.timeout_policy
        age_hours = escalation.age_in_hours

        # Check for reminder
        if age_hours >= policy.reminder_hours and not self._reminder_sent_recently(escalation):
            self._send_reminder(escalation, policy)

        # Check for timeout
        if age_hours >= policy.timeout_hours:
            return self._handle_timeout(escalation, policy)

        return None

    def check_all_timeouts(self, escalations: list[Escalation]) -> list[EscalationResult]:
        """
        Check timeouts for all pending escalations.

        Args:
            escalations: List of escalations to check

        Returns:
            List of EscalationResults for auto-selected escalations
        """
        results = []

        for escalation in escalations:
            result = self.check_timeout(escalation)
            if result:
                results.append(result)

        return results

    def _reminder_sent_recently(self, escalation: Escalation) -> bool:
        """Check if a reminder was sent recently."""
        if not escalation.reminder_sent_at:
            return False

        # Don't send more than one reminder per policy interval
        policy = escalation.timeout_policy
        hours_since_reminder = (
            datetime.now(timezone.utc) - escalation.reminder_sent_at
        ).total_seconds() / 3600

        # At least half the reminder interval between reminders
        return hours_since_reminder < policy.reminder_hours / 2

    def _send_reminder(self, escalation: Escalation, policy: TimeoutPolicy):
        """Send reminder through configured channels."""
        logger.info(f"Sending reminder for escalation {escalation.escalation_id}")

        escalation.reminder_count += 1
        escalation.reminder_sent_at = datetime.now(timezone.utc)

        # Calculate time remaining
        time_remaining = policy.timeout_hours - escalation.age_in_hours

        for channel in policy.notify_channels:
            if channel == "github":
                self._send_github_reminder(escalation, time_remaining, policy)
            elif channel == "slack" and self.slack_webhook:
                self._send_slack_reminder(escalation, time_remaining)
            elif channel == "email" and self.email_handler:
                self._send_email_reminder(escalation, time_remaining)

    def _send_github_reminder(
        self,
        escalation: Escalation,
        time_remaining: float,
        policy: TimeoutPolicy,
    ):
        """Send reminder as GitHub comment."""
        if not escalation.issue_number:
            return

        lines = []
        lines.append("## ⏰ Reminder: Decision Needed")
        lines.append("")

        if time_remaining > 0:
            if time_remaining >= 24:
                time_str = f"{time_remaining / 24:.0f} days"
            else:
                time_str = f"{time_remaining:.0f} hours"
            lines.append(f"This escalation will timeout in **{time_str}**.")
        else:
            lines.append("This escalation is overdue.")

        lines.append("")

        if policy.auto_select:
            rec = escalation.recommendation or "the recommended option"
            lines.append(f"If no response is received, I'll automatically proceed with **{rec}**.")
        else:
            lines.append("This requires your decision - I cannot auto-select due to the nature of this change.")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**Quick response options:**")

        for option in escalation.options:
            rec = " ✓ recommended" if option.is_recommended else ""
            lines.append(f"- Reply `{option.option_id}` for {option.title}{rec}")

        lines.append("")
        lines.append(f"*Reminder #{escalation.reminder_count}*")

        self.issue_creator.add_comment(escalation.issue_number, "\n".join(lines))

    def _send_slack_reminder(self, escalation: Escalation, time_remaining: float):
        """Send reminder to Slack webhook."""
        if not self.slack_webhook:
            return

        import urllib.request
        import json

        message = {
            "text": f"⏰ Escalation needs attention: {escalation.issue_url}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Escalation needs your decision*\n\n"
                               f"<{escalation.issue_url}|View on GitHub>\n\n"
                               f"Time remaining: {time_remaining:.0f} hours"
                    }
                }
            ]
        }

        try:
            req = urllib.request.Request(
                self.slack_webhook,
                data=json.dumps(message).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req)
        except Exception as e:
            logger.error(f"Failed to send Slack reminder: {e}")

    def _send_email_reminder(self, escalation: Escalation, time_remaining: float):
        """Send email reminder (placeholder for email integration)."""
        # Would integrate with email service
        logger.info(f"Would send email reminder for {escalation.escalation_id}")

    def _handle_timeout(
        self,
        escalation: Escalation,
        policy: TimeoutPolicy,
    ) -> Optional[EscalationResult]:
        """Handle a timed-out escalation."""
        logger.warning(f"Escalation {escalation.escalation_id} has timed out")

        if policy.auto_select:
            return self._auto_select(escalation)
        else:
            return self._send_urgent_escalation(escalation)

    def _auto_select(self, escalation: Escalation) -> EscalationResult:
        """
        Auto-select the recommended option.

        Safeguards:
        - Create PR as DRAFT
        - Add "auto-selected" label
        - Include revert instructions
        - Notify user
        """
        logger.info(f"Auto-selecting recommendation for {escalation.escalation_id}")

        # Find recommended option
        winner = None
        if escalation.recommendation:
            winner = next(
                (o for o in escalation.options if o.option_id == escalation.recommendation),
                None
            )

        if not winner and escalation.options:
            # Fall back to first option with highest score
            winner = escalation.options[0]

        if not winner:
            logger.error("No option available for auto-selection")
            escalation.status = EscalationStatus.TIMEOUT
            return EscalationResult(resolved=False)

        # Update escalation
        escalation.status = EscalationStatus.AUTO_SELECTED
        escalation.resolved_at = datetime.now(timezone.utc)
        escalation.response = f"AUTO_SELECT:{winner.option_id}"

        # Post notification
        self._post_auto_select_notification(escalation, winner)

        return EscalationResult(
            resolved=True,
            winner=winner,
            winning_candidate=winner.candidate,
            auto_selected=True,
            auto_select_reason=f"Timeout after {escalation.age_in_hours:.0f} hours",
        )

    def _post_auto_select_notification(
        self,
        escalation: Escalation,
        winner,
    ):
        """Post notification about auto-selection."""
        if not escalation.issue_number:
            return

        lines = []
        lines.append("## ⏰ Auto-Selected Due to Timeout")
        lines.append("")
        lines.append(f"No response was received within the timeout period "
                    f"({escalation.timeout_policy.timeout_hours} hours).")
        lines.append("")
        lines.append(f"I've automatically selected **Option {winner.option_id}: {winner.title}** "
                    "based on my recommendation.")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("### What's Next")
        lines.append("")
        lines.append("1. A **DRAFT PR** will be created with this approach")
        lines.append("2. You can review and either approve or request changes")
        lines.append("3. If this was the wrong choice, you can close the PR and reopen this issue")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**To override this decision:**")
        lines.append("1. Close the draft PR")
        lines.append("2. Reply here with your actual preference")
        lines.append("3. I'll create a new PR with your choice")

        self.issue_creator.add_comment(escalation.issue_number, "\n".join(lines))

    def _send_urgent_escalation(self, escalation: Escalation) -> EscalationResult:
        """
        Send urgent escalation when auto-select is not allowed.

        For critical/high priority items that cannot be auto-selected.
        """
        logger.warning(f"Urgent escalation for {escalation.escalation_id}")

        escalation.status = EscalationStatus.TIMEOUT

        # Notify through all available channels urgently
        self._send_urgent_github_notice(escalation)

        if self.slack_webhook:
            self._send_urgent_slack_notice(escalation)

        if self.email_handler:
            self._send_urgent_email_notice(escalation)

        return EscalationResult(
            resolved=False,
            awaiting_response=True,
        )

    def _send_urgent_github_notice(self, escalation: Escalation):
        """Post urgent notice on GitHub issue."""
        if not escalation.issue_number:
            return

        lines = []
        lines.append("## 🚨 URGENT: Decision Required")
        lines.append("")
        lines.append("This escalation has **timed out** and requires immediate attention.")
        lines.append("")
        lines.append(f"Due to the nature of this change ({escalation.priority.value} priority), "
                    "I cannot auto-select an option.")
        lines.append("")
        lines.append("**Please respond as soon as possible.**")
        lines.append("")

        if escalation.triggers:
            lines.append("### Why This Needs Your Decision")
            lines.append("")
            for trigger in escalation.triggers:
                lines.append(f"- {trigger.value.replace('_', ' ').title()}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("*This issue will remain open until you respond.*")

        self.issue_creator.add_comment(escalation.issue_number, "\n".join(lines))

    def _send_urgent_slack_notice(self, escalation: Escalation):
        """Send urgent Slack notification."""
        if not self.slack_webhook:
            return

        import urllib.request
        import json

        message = {
            "text": f"🚨 URGENT: Escalation requires immediate decision",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🚨 URGENT: Decision Required*\n\n"
                               f"An escalation has timed out and cannot be auto-selected.\n\n"
                               f"Priority: {escalation.priority.value.upper()}\n\n"
                               f"<{escalation.issue_url}|View on GitHub>"
                    }
                }
            ]
        }

        try:
            req = urllib.request.Request(
                self.slack_webhook,
                data=json.dumps(message).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req)
        except Exception as e:
            logger.error(f"Failed to send urgent Slack notice: {e}")

    def _send_urgent_email_notice(self, escalation: Escalation):
        """Send urgent email (placeholder)."""
        logger.info(f"Would send urgent email for {escalation.escalation_id}")

"""
Escalation Manager

Main orchestrator for the escalation system:
- Creates escalations from resolution failures
- Manages the escalation lifecycle
- Coordinates issue creation, responses, and resolution
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import (
    Escalation,
    EscalationOption,
    EscalationPriority,
    EscalationStatus,
    EscalationTrigger,
    EscalationResult,
    TechnicalDetails,
    ALWAYS_ESCALATE_TRIGGERS,
)
from .issue_creator import IssueCreator
from .response_handler import ResponseHandler
from .timeout_handler import TimeoutHandler
from .feature_porter import FeaturePorter

from ..resolution.schema import Resolution, IntentAnalysis, ResolutionCandidate
from ..conflict.pipeline import PipelineResult

logger = logging.getLogger(__name__)


class EscalationManager:
    """
    Main orchestrator for the escalation system.

    Handles the full lifecycle:
    1. Create escalation from resolution failure
    2. Generate options and recommendations
    3. Create GitHub issue
    4. Process responses
    5. Handle timeouts
    6. Execute resolution (port features, create PR)
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        issue_creator: Optional[IssueCreator] = None,
        slack_webhook: Optional[str] = None,
    ):
        self.repo_path = repo_path or Path.cwd()
        self.issue_creator = issue_creator or IssueCreator()
        self.response_handler = ResponseHandler(self.issue_creator)
        self.timeout_handler = TimeoutHandler(self.issue_creator, slack_webhook)
        self.feature_porter = FeaturePorter(repo_path)

        # In-memory store (would be database in production)
        self._escalations: dict[str, Escalation] = {}

    def create_escalation(
        self,
        resolution: Resolution,
        detection_result: Optional[PipelineResult] = None,
        intent_analysis: Optional[IntentAnalysis] = None,
    ) -> Escalation:
        """
        Create an escalation from a failed resolution.

        Args:
            resolution: The Resolution that needs escalation
            detection_result: Original detection result
            intent_analysis: Intent analysis if available

        Returns:
            Created Escalation
        """
        logger.info(f"Creating escalation for resolution {resolution.resolution_id}")

        escalation_id = f"esc-{uuid.uuid4().hex[:8]}"

        # Determine triggers
        triggers = self._determine_triggers(resolution, detection_result)

        # Determine priority
        priority = self._determine_priority(triggers, detection_result)

        # Generate options from candidates
        options = self._generate_options(resolution.all_candidates)

        # Determine recommendation
        recommendation, recommendation_reason = self._generate_recommendation(
            options,
            intent_analysis,
            detection_result,
        )

        # Generate technical details
        technical_details = self._generate_technical_details(
            resolution,
            detection_result,
        )

        # Create escalation
        escalation = Escalation(
            escalation_id=escalation_id,
            triggers=triggers,
            trigger_reason=resolution.escalation_reason or "",
            priority=priority,
            status=EscalationStatus.PENDING,
            detection_result=detection_result,
            intent_analysis=intent_analysis,
            candidates=resolution.all_candidates,
            options=options,
            recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            confidence=self._calculate_confidence(options, resolution),
            technical_details=technical_details,
        )

        # Store escalation
        self._escalations[escalation_id] = escalation

        # Create GitHub issue
        try:
            issue_number, issue_url = self.issue_creator.create_issue(escalation)
            escalation.issue_number = issue_number
            escalation.issue_url = issue_url
            logger.info(f"Created escalation issue #{issue_number}")
        except Exception as e:
            logger.error(f"Failed to create issue: {e}")

        return escalation

    def process_response(
        self,
        escalation_id: str,
        response: str,
    ) -> EscalationResult:
        """
        Process a user response to an escalation.

        Args:
            escalation_id: ID of the escalation
            response: User's response text

        Returns:
            EscalationResult
        """
        escalation = self._escalations.get(escalation_id)
        if not escalation:
            logger.error(f"Escalation not found: {escalation_id}")
            return EscalationResult(resolved=False)

        result = self.response_handler.process_response(escalation, response)

        if result.resolved and result.winner:
            # Port features from losers
            losers = [o for o in escalation.options if o.option_id != result.winner.option_id]
            if losers:
                logger.info("Porting features from losing options")
                ports = self.feature_porter.port_features(result.winner, losers)
                result.ported_features = [p.feature_description for p in ports if p.success]

            # Close issue
            if escalation.issue_number:
                self.issue_creator.close_issue(escalation.issue_number)

        return result

    def check_timeouts(self) -> list[EscalationResult]:
        """
        Check all pending escalations for timeouts.

        Returns:
            List of EscalationResults for auto-selected escalations
        """
        pending = [
            e for e in self._escalations.values()
            if e.status == EscalationStatus.PENDING
        ]

        return self.timeout_handler.check_all_timeouts(pending)

    def get_escalation(self, escalation_id: str) -> Optional[Escalation]:
        """Get an escalation by ID."""
        return self._escalations.get(escalation_id)

    def get_pending_escalations(self) -> list[Escalation]:
        """Get all pending escalations."""
        return [
            e for e in self._escalations.values()
            if e.status == EscalationStatus.PENDING
        ]

    def _determine_triggers(
        self,
        resolution: Resolution,
        detection_result: Optional[PipelineResult],
    ) -> list[EscalationTrigger]:
        """Determine what triggered this escalation."""
        triggers = []

        # From resolution reason
        reason = resolution.escalation_reason or ""

        if "low_intent_confidence" in reason:
            triggers.append(EscalationTrigger.LOW_INTENT_CONFIDENCE)
        if "conflicting" in reason.lower():
            triggers.append(EscalationTrigger.CONFLICTING_INTENTS)
        if "no_viable_candidates" in reason or "no_passing_candidates" in reason:
            triggers.append(EscalationTrigger.NO_VIABLE_CANDIDATES)

        # From detection result
        if detection_result:
            risk_flags = detection_result.risk_flags

            if "security" in risk_flags:
                triggers.append(EscalationTrigger.SECURITY_SENSITIVE)
            if "auth" in risk_flags:
                triggers.append(EscalationTrigger.AUTH_CHANGES)
            if "db_migration" in risk_flags:
                triggers.append(EscalationTrigger.DB_MIGRATIONS)
            if "public_api" in risk_flags:
                triggers.append(EscalationTrigger.PUBLIC_API_CHANGES)

            # Check for many files
            if detection_result.textual_result:
                if detection_result.textual_result.file_count > 20:
                    triggers.append(EscalationTrigger.MANY_FILES_CHANGED)

        return triggers or [EscalationTrigger.LOW_INTENT_CONFIDENCE]

    def _determine_priority(
        self,
        triggers: list[EscalationTrigger],
        detection_result: Optional[PipelineResult],
    ) -> EscalationPriority:
        """Determine escalation priority from triggers."""
        trigger_set = set(triggers)

        # Critical triggers
        critical_triggers = {
            EscalationTrigger.SECURITY_SENSITIVE,
            EscalationTrigger.PAYMENT_PROCESSING,
        }
        if trigger_set & critical_triggers:
            return EscalationPriority.CRITICAL

        # High priority triggers
        high_triggers = {
            EscalationTrigger.AUTH_CHANGES,
            EscalationTrigger.DB_MIGRATIONS,
            EscalationTrigger.PUBLIC_API_CHANGES,
        }
        if trigger_set & high_triggers:
            return EscalationPriority.HIGH

        # From severity
        if detection_result:
            if detection_result.severity.value == "critical":
                return EscalationPriority.CRITICAL
            if detection_result.severity.value == "high":
                return EscalationPriority.HIGH

        # Low priority triggers
        low_triggers = {
            EscalationTrigger.CANDIDATES_TOO_SIMILAR,
            EscalationTrigger.DIFFERENT_TRADEOFFS,
        }
        if trigger_set.issubset(low_triggers):
            return EscalationPriority.LOW

        return EscalationPriority.STANDARD

    def _generate_options(
        self,
        candidates: list[ResolutionCandidate],
    ) -> list[EscalationOption]:
        """Generate escalation options from candidates."""
        options = []
        option_ids = ["A", "B", "C", "D"]

        for i, candidate in enumerate(candidates[:4]):  # Max 4 options
            option = EscalationOption(
                option_id=option_ids[i],
                title=self._generate_option_title(candidate),
                description=self._generate_option_description(candidate),
                tradeoffs=self._generate_tradeoffs(candidate),
                risk_level=self._determine_risk_level(candidate),
                is_recommended=(i == 0),  # First is usually best
                candidate_id=candidate.candidate_id,
                candidate=candidate,
            )
            options.append(option)

        return options

    def _generate_option_title(self, candidate: ResolutionCandidate) -> str:
        """Generate user-friendly title for option."""
        strategy = candidate.strategy

        titles = {
            "agent1_primary": "Keep first agent's approach",
            "agent2_primary": "Keep second agent's approach",
            "convention_primary": "Follow existing conventions",
            "fresh_synthesis": "Fresh implementation",
        }

        return titles.get(strategy, strategy.replace("_", " ").title())

    def _generate_option_description(self, candidate: ResolutionCandidate) -> str:
        """Generate plain-English description of option."""
        desc = candidate.summary or candidate.technical_details or ""

        if not desc:
            desc = f"Uses the {candidate.strategy} strategy"

        # Add key metrics
        if candidate.build_passed:
            desc += "\n- Build passes"
        if candidate.tests_passed > 0:
            desc += f"\n- {candidate.tests_passed} tests pass"

        return desc

    def _generate_tradeoffs(self, candidate: ResolutionCandidate) -> list[str]:
        """Generate tradeoffs for an option."""
        tradeoffs = []

        # File count
        if len(candidate.files_modified) > 10:
            tradeoffs.append(f"Touches {len(candidate.files_modified)} files")

        # Test failures
        if candidate.tests_failed > 0:
            tradeoffs.append(f"{candidate.tests_failed} tests still failing")

        # Lint issues
        if candidate.lint_score < 0.8:
            tradeoffs.append("Some lint warnings")

        # Score
        if candidate.total_score < 0.7:
            tradeoffs.append("Lower overall confidence")

        return tradeoffs

    def _determine_risk_level(
        self,
        candidate: ResolutionCandidate,
    ) -> str:
        """Determine risk level for option."""
        if not candidate.build_passed:
            return "high"
        if candidate.tests_failed > 0:
            return "high"
        if candidate.total_score < 0.6:
            return "medium"
        if candidate.total_score >= 0.8:
            return "low"
        return "medium"

    def _generate_recommendation(
        self,
        options: list[EscalationOption],
        intent_analysis: Optional[IntentAnalysis],
        detection_result: Optional[PipelineResult],
    ) -> tuple[Optional[str], str]:
        """Generate recommendation and reasoning."""
        if not options:
            return None, ""

        # Find best option
        best = options[0]
        for option in options[1:]:
            if option.candidate and best.candidate:
                if option.candidate.total_score > best.candidate.total_score:
                    best = option

        # Generate reasoning
        reasons = []

        if best.candidate:
            if best.candidate.build_passed and best.candidate.tests_failed == 0:
                reasons.append("All tests pass")
            if best.candidate.total_score >= 0.8:
                reasons.append("High confidence score")
            if best.risk_level == "low":
                reasons.append("Low risk")

        # Mark as recommended
        for option in options:
            option.is_recommended = (option.option_id == best.option_id)

        reason_text = ". ".join(reasons) if reasons else "Best overall score"

        return best.option_id, reason_text

    def _calculate_confidence(
        self,
        options: list[EscalationOption],
        resolution: Resolution,
    ) -> float:
        """Calculate confidence in recommendation."""
        if not options:
            return 0.0

        best = options[0]
        if not best.candidate:
            return 0.5

        # Start with candidate score
        confidence = best.candidate.total_score

        # Adjust based on other options
        if len(options) > 1:
            second = options[1]
            if second.candidate:
                # If close race, lower confidence
                diff = best.candidate.total_score - second.candidate.total_score
                if diff < 0.1:
                    confidence *= 0.8

        return round(confidence, 2)

    def _generate_technical_details(
        self,
        resolution: Resolution,
        detection_result: Optional[PipelineResult],
    ) -> TechnicalDetails:
        """Generate technical details for the escalation."""
        details = TechnicalDetails()

        # Collect files from all candidates
        all_files = set()
        for candidate in resolution.all_candidates:
            all_files.update(candidate.files_modified)

        details.files_involved = sorted(all_files)

        # Generate diff (simplified)
        if resolution.all_candidates:
            best = resolution.all_candidates[0]
            details.code_diff = best.diff_from_base[:5000]  # Limit size

        return details


def create_escalation(
    resolution: Resolution,
    detection_result: Optional[PipelineResult] = None,
) -> Escalation:
    """
    Convenience function to create an escalation.

    Args:
        resolution: The resolution that needs escalation
        detection_result: Original detection result

    Returns:
        Created Escalation
    """
    manager = EscalationManager()
    return manager.create_escalation(resolution, detection_result)

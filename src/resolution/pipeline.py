"""
Resolution Pipeline

Main orchestrator for the conflict resolution process:

Stage 1: Context Assembly - Gather all context
Stage 2: Intent Extraction - Extract and compare intents
Stage 3: Interface Harmonization - Make code buildable
Stage 4: Candidate Generation - Generate resolution candidates
Stage 5: Validation - Validate candidates (build + tests)
Stage 6: Selection - Select winning candidate or escalate

Phase 3 Goal: Auto-resolve ~60% of conflicts.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

from .schema import (
    ConflictContext,
    IntentAnalysis,
    HarmonizedResult,
    ResolutionCandidate,
    Resolution,
)
from .context import ContextAssembler
from .intent import IntentExtractor
from .harmonizer import InterfaceHarmonizer
from .candidate import CandidateGenerator
from .validator import ResolutionValidator
from ..conflict.pipeline import PipelineResult

logger = logging.getLogger(__name__)


class ResolutionPipeline:
    """
    Main resolution pipeline orchestrator.

    Runs all stages in sequence and returns final resolution.
    """

    def __init__(
        self,
        base_branch: str = "main",
        repo_path: Optional[Path] = None,
        build_command: Optional[str] = None,
        test_command: Optional[str] = None,
        auto_escalate_low_confidence: bool = True,
    ):
        self.base_branch = base_branch
        self.repo_path = repo_path or Path.cwd()
        self.auto_escalate_low_confidence = auto_escalate_low_confidence

        # Initialize stage components
        self.context_assembler = ContextAssembler(
            base_branch=base_branch,
            repo_path=repo_path,
        )
        self.intent_extractor = IntentExtractor()
        self.harmonizer = InterfaceHarmonizer(
            repo_path=repo_path,
            build_command=build_command,
        )
        self.candidate_generator = CandidateGenerator(
            repo_path=repo_path,
            base_branch=base_branch,
        )
        self.validator = ResolutionValidator(
            repo_path=repo_path,
            build_command=build_command,
            test_command=test_command,
        )

    def resolve(self, detection_result: PipelineResult) -> Resolution:
        """
        Run the full resolution pipeline.

        Args:
            detection_result: Result from detection pipeline

        Returns:
            Resolution with either winning candidate or escalation
        """
        resolution_id = f"resolution-{uuid.uuid4().hex[:8]}"
        logger.info(f"Starting resolution pipeline: {resolution_id}")

        # Quick check: is resolution even needed?
        if not detection_result.has_conflicts:
            logger.info("No conflicts detected, no resolution needed")
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=False,
            )

        # Stage 1: Context Assembly
        logger.info("=== Stage 1: Context Assembly ===")
        try:
            context = self.context_assembler.assemble(detection_result)
        except Exception as e:
            logger.error(f"Stage 1 (Context Assembly) failed: {e}", exc_info=True)
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="stage_1_context_assembly_failed",
            )

        # Stage 2: Intent Extraction
        logger.info("=== Stage 2: Intent Extraction ===")
        try:
            intents = self.intent_extractor.extract(context)
        except Exception as e:
            logger.error(f"Stage 2 (Intent Extraction) failed: {e}", exc_info=True)
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="stage_2_intent_extraction_failed",
            )

        # Check if we should escalate due to low confidence
        if self.auto_escalate_low_confidence and intents.overall_confidence == "low":
            logger.warning("Low confidence in intent extraction - escalating")
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="low_intent_confidence",
            )

        # Stage 3: Interface Harmonization
        logger.info("=== Stage 3: Interface Harmonization ===")
        try:
            harmonized = self.harmonizer.harmonize(context, intents)
        except Exception as e:
            logger.error(f"Stage 3 (Interface Harmonization) failed: {e}", exc_info=True)
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="stage_3_interface_harmonization_failed",
            )

        # Check if harmonization failed
        if not harmonized.build_passes:
            logger.warning("Interface harmonization failed - checking if we can proceed")
            # For Phase 3, try to proceed anyway with candidate generation
            # Phase 5 will be smarter about this

        # Stage 4: Candidate Generation
        logger.info("=== Stage 4: Candidate Generation ===")
        try:
            candidates = self.candidate_generator.generate(context, intents, harmonized)
        except Exception as e:
            logger.error(f"Stage 4 (Candidate Generation) failed: {e}", exc_info=True)
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="stage_4_candidate_generation_failed",
            )

        if not candidates:
            logger.warning("No candidates generated - escalating")
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="no_candidates_generated",
            )

        # Stage 5: Validation
        logger.info("=== Stage 5: Validation ===")
        try:
            validated = self.validator.validate(candidates, context)
        except Exception as e:
            logger.error(f"Stage 5 (Validation) failed: {e}", exc_info=True)
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="stage_5_validation_failed",
                all_candidates=candidates,  # Include what we have
            )

        # Stage 6: Selection
        logger.info("=== Stage 6: Selection ===")
        try:
            return self._select_winner(resolution_id, validated, intents, context)
        except Exception as e:
            logger.error(f"Stage 6 (Selection) failed: {e}", exc_info=True)
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="stage_6_selection_failed",
                all_candidates=validated,  # Include validated candidates
            )

    def _select_winner(
        self,
        resolution_id: str,
        candidates: list[ResolutionCandidate],
        intents: IntentAnalysis,
        context: ConflictContext,
    ) -> Resolution:
        """Select the winning candidate or escalate."""

        # Filter to viable candidates
        viable = [c for c in candidates if c.is_viable]

        if not viable:
            logger.warning("No viable candidates - escalating")
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="no_viable_candidates",
                all_candidates=candidates,
            )

        # Sort by total score
        viable.sort(key=lambda c: c.total_score, reverse=True)
        winner = viable[0]

        # Check if winner score is high enough
        min_score = 0.6  # Phase 3: require 60% score
        if winner.total_score < min_score:
            logger.warning(f"Best candidate score {winner.total_score:.2f} < {min_score} - escalating")
            return Resolution(
                resolution_id=resolution_id,
                needs_escalation=True,
                escalation_reason="low_confidence_resolution",
                all_candidates=candidates,
            )

        # Check for close runner-up (might need human to decide)
        if len(viable) > 1:
            runner_up = viable[1]
            if runner_up.total_score > winner.total_score * 0.95:
                # Very close - might want to escalate
                logger.info(f"Close runner-up: {winner.total_score:.2f} vs {runner_up.total_score:.2f}")
                # For Phase 3, proceed with winner
                # Phase 4 will add proper escalation here

        # Identify ported features (features from losing candidate)
        ported = self._identify_ported_features(winner, candidates, context)

        logger.info(f"Selected winner: {winner.candidate_id} (score={winner.total_score:.2f})")
        return Resolution(
            resolution_id=resolution_id,
            needs_escalation=False,
            winning_candidate=winner,
            ported_features=ported,
            all_candidates=candidates,
        )

    def _identify_ported_features(
        self,
        winner: ResolutionCandidate,
        all_candidates: list[ResolutionCandidate],
        context: ConflictContext,
    ) -> list[str]:
        """Identify features that were ported from losing candidates."""
        ported = []

        # For Phase 3, we do simple file-based identification
        winner_files = set(winner.files_modified)

        for intent in context.agent_ids:
            # Files this agent modified
            derived = next((d for d in context.derived_manifests if d.agent_id == intent), None)
            if derived:
                agent_files = set(derived.all_files_touched)
                # If agent's files are in winner but strategy wasn't theirs
                overlap = winner_files & agent_files
                if overlap and f"agent{intent}" not in winner.strategy:
                    ported.append(f"Features from {intent}: {len(overlap)} files included")

        return ported


def resolve_conflicts(
    detection_result: PipelineResult,
    base_branch: str = "main",
    repo_path: Optional[Path] = None,
) -> Resolution:
    """
    Convenience function to resolve conflicts.

    Args:
        detection_result: Result from detection pipeline
        base_branch: Base branch name
        repo_path: Path to repository

    Returns:
        Resolution with winning candidate or escalation
    """
    pipeline = ResolutionPipeline(
        base_branch=base_branch,
        repo_path=repo_path,
    )
    return pipeline.resolve(detection_result)

"""
Detection Pipeline

Orchestrates the full conflict detection process:
1. Textual conflict check (git merge-tree)
2. Create temporary merge
3. Build test (compile/typecheck)
4. Smoke test (targeted tests)
5. Dependency check
6. Semantic analysis

This catches "clean but broken" merges that git says are clean
but actually have semantic conflicts.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .detector import ConflictDetector, ConflictType, ConflictSeverity, ConflictInfo
from .build_tester import BuildTester, BuildTestResult
from .dependency import DependencyAnalyzer, DependencyConflict
from .semantic import SemanticAnalyzer, SemanticAnalysisResult
from .clusterer import ConflictClusterer, ConflictCluster

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Complete result from the detection pipeline."""
    has_conflicts: bool
    conflict_type: ConflictType
    severity: ConflictSeverity

    # Step results
    textual_result: Optional[ConflictInfo] = None
    build_result: Optional[BuildTestResult] = None
    dependency_conflicts: list[DependencyConflict] = field(default_factory=list)
    semantic_result: Optional[SemanticAnalysisResult] = None

    # Metadata
    branches: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    clusters: list[ConflictCluster] = field(default_factory=list)

    # Recommendation
    recommended_action: str = "fast_merge"  # fast_merge, auto_resolve, escalate
    confidence: float = 1.0

    @property
    def is_fast_path(self) -> bool:
        """Can this be fast-path merged without resolution?"""
        return not self.has_conflicts and self.conflict_type == ConflictType.NONE

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = []
        lines.append(f"Conflict Type: {self.conflict_type.value}")
        lines.append(f"Severity: {self.severity.value}")
        lines.append(f"Recommended: {self.recommended_action}")

        if self.risk_flags:
            lines.append(f"Risk Flags: {', '.join(self.risk_flags)}")

        if self.dependency_conflicts:
            lines.append(f"Dependency Conflicts: {len(self.dependency_conflicts)}")

        if self.semantic_result and self.semantic_result.has_semantic_conflicts:
            lines.append("Semantic Conflicts: Yes")

        return "\n".join(lines)


class DetectionPipeline:
    """
    Orchestrates full conflict detection.

    Runs detection steps in order, with early exit on critical conflicts.
    """

    def __init__(
        self,
        base_branch: str = "main",
        build_command: Optional[str] = None,
        test_command: Optional[str] = None,
        skip_build_test: bool = False,
        skip_semantic: bool = False,
    ):
        self.base_branch = base_branch
        self.skip_build_test = skip_build_test
        self.skip_semantic = skip_semantic

        # Initialize detectors
        self.textual_detector = ConflictDetector(base_branch=base_branch)
        self.build_tester = BuildTester(
            base_branch=base_branch,
            build_command=build_command,
            test_command=test_command,
        )
        self.dependency_analyzer = DependencyAnalyzer()
        self.semantic_analyzer = SemanticAnalyzer()
        self.clusterer = ConflictClusterer()

    def run(
        self,
        branches: list[str],
        modified_files: Optional[dict[str, list[str]]] = None,
    ) -> PipelineResult:
        """
        Run the full detection pipeline.

        Args:
            branches: List of branch names to check
            modified_files: Optional dict of {branch: [files]} for optimization

        Returns:
            PipelineResult with all detection results
        """
        logger.info(f"Running detection pipeline for {len(branches)} branches")

        # Initialize result
        result = PipelineResult(
            has_conflicts=False,
            conflict_type=ConflictType.NONE,
            severity=ConflictSeverity.LOW,
            branches=branches,
        )

        # Step 1: Textual conflict check
        logger.info("Step 1: Checking for textual conflicts...")
        textual_result = self.textual_detector.detect(branches)
        result.textual_result = textual_result

        if textual_result.has_conflicts:
            logger.warning(f"Textual conflicts found: {textual_result.file_count} files")
            result.has_conflicts = True
            result.conflict_type = ConflictType.TEXTUAL
            result.severity = textual_result.severity

            # Detect risk flags
            files = [f.file_path for f in textual_result.conflicting_files]
            result.risk_flags = self.textual_detector.detect_risk_flags(files)

            # For critical conflicts, stop early
            if textual_result.severity == ConflictSeverity.CRITICAL:
                result.recommended_action = "escalate"
                result.confidence = 0.9
                return result

        # Step 2-4: Build and test (catches "clean but broken")
        if not self.skip_build_test:
            logger.info("Steps 2-4: Testing merged result...")
            all_files = []
            if modified_files:
                for files in modified_files.values():
                    all_files.extend(files)

            build_result = self.build_tester.test(branches, all_files)
            result.build_result = build_result

            if not build_result.all_passed:
                logger.warning("Build/test failed on merged code")
                result.has_conflicts = True

                # Upgrade to semantic conflict
                if result.conflict_type == ConflictType.NONE:
                    result.conflict_type = ConflictType.SEMANTIC

                # Increase severity
                if result.severity.value in ["low", "medium"]:
                    result.severity = ConflictSeverity.HIGH

                if not build_result.build_passed:
                    result.recommended_action = "escalate"
                else:
                    result.recommended_action = "auto_resolve"

                result.confidence = 0.7

        # Step 5: Dependency check
        logger.info("Step 5: Checking for dependency conflicts...")
        dep_conflicts = self.dependency_analyzer.analyze(branches, self.base_branch)
        result.dependency_conflicts = dep_conflicts

        if dep_conflicts:
            logger.warning(f"Found {len(dep_conflicts)} dependency conflicts")
            result.has_conflicts = True

            if result.conflict_type == ConflictType.NONE:
                result.conflict_type = ConflictType.DEPENDENCY

            # High-severity dependency conflicts need attention
            high_severity = any(c.severity == "high" for c in dep_conflicts)
            if high_severity:
                result.severity = ConflictSeverity.HIGH
                result.recommended_action = "escalate"

        # Step 6: Semantic analysis
        if not self.skip_semantic:
            logger.info("Step 6: Analyzing semantic conflicts...")
            semantic_result = self.semantic_analyzer.analyze(branches, self.base_branch)
            result.semantic_result = semantic_result

            if semantic_result.has_semantic_conflicts:
                logger.info(f"Semantic analysis: risk level = {semantic_result.risk_level}")

                if semantic_result.risk_level == "high":
                    result.has_conflicts = True
                    if result.conflict_type == ConflictType.NONE:
                        result.conflict_type = ConflictType.SEMANTIC
                    result.severity = ConflictSeverity.HIGH

                # Add risk flags from semantic analysis
                if semantic_result.domain_overlap:
                    for domain in semantic_result.domain_overlap.overlapping_domains:
                        if domain not in result.risk_flags:
                            result.risk_flags.append(domain)

        # Determine final recommendation
        result.recommended_action = self._determine_recommendation(result)
        result.confidence = self._calculate_confidence(result)

        logger.info(f"Pipeline complete: {result.conflict_type.value}, {result.severity.value}")
        return result

    def _determine_recommendation(self, result: PipelineResult) -> str:
        """Determine recommended action based on results."""
        if not result.has_conflicts:
            return "fast_merge"

        if result.severity == ConflictSeverity.CRITICAL:
            return "escalate"

        if result.severity == ConflictSeverity.HIGH:
            # High severity with certain risk flags should escalate
            critical_flags = {"security", "auth", "db_migration"}
            if critical_flags & set(result.risk_flags):
                return "escalate"
            return "auto_resolve"

        if result.conflict_type == ConflictType.DEPENDENCY:
            # Dependency conflicts often need manual resolution
            return "escalate"

        return "auto_resolve"

    def _calculate_confidence(self, result: PipelineResult) -> float:
        """Calculate confidence in the recommendation."""
        confidence = 1.0

        # Lower confidence for semantic conflicts
        if result.semantic_result and result.semantic_result.has_semantic_conflicts:
            confidence *= result.semantic_result.confidence

        # Lower confidence for build failures
        if result.build_result and not result.build_result.all_passed:
            confidence *= 0.8

        # Lower confidence for high severity
        if result.severity == ConflictSeverity.HIGH:
            confidence *= 0.9
        elif result.severity == ConflictSeverity.CRITICAL:
            confidence *= 0.7

        return round(confidence, 2)


def run_detection_pipeline(
    branches: list[str],
    base_branch: str = "main",
    skip_build_test: bool = False,
) -> PipelineResult:
    """
    Convenience function to run the detection pipeline.

    Args:
        branches: Branch names to check
        base_branch: Base branch (default: main)
        skip_build_test: Skip build/test steps for speed

    Returns:
        PipelineResult with all detection results
    """
    pipeline = DetectionPipeline(
        base_branch=base_branch,
        skip_build_test=skip_build_test,
    )
    return pipeline.run(branches)

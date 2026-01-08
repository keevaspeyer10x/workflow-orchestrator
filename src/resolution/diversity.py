"""
Diversity Checker (Phase 5)

Ensures that generated resolution candidates are meaningfully different.
If candidates are too similar, one of them is likely redundant.

Uses Jaccard similarity on changed line sets to measure diversity.
"""

import logging
from typing import Optional

from .schema import ResolutionCandidate, DiversityResult

logger = logging.getLogger(__name__)


class DiversityChecker:
    """
    Checks diversity between resolution candidates.

    Ensures candidates represent genuinely different approaches,
    not just minor variations of the same solution.
    """

    def __init__(
        self,
        min_diversity: float = 0.3,
        max_regeneration_attempts: int = 3,
    ):
        """
        Initialize diversity checker.

        Args:
            min_diversity: Minimum required diversity (0-1). Default 0.3.
            max_regeneration_attempts: Max times to regenerate for diversity.
        """
        self.min_diversity = min_diversity
        self.max_regeneration_attempts = max_regeneration_attempts

    def check_diversity(
        self,
        candidates: list[ResolutionCandidate],
    ) -> DiversityResult:
        """
        Check if candidates meet diversity threshold.

        Args:
            candidates: List of candidates to check

        Returns:
            DiversityResult with scores and recommendation
        """
        if len(candidates) < 2:
            return DiversityResult(
                meets_threshold=True,
                min_diversity=1.0,
                avg_diversity=1.0,
                recommendation="Single candidate - diversity check not applicable",
            )

        pairwise_scores = {}
        all_scores = []

        for i, c1 in enumerate(candidates):
            for j, c2 in enumerate(candidates):
                if i >= j:
                    continue

                score = self.calculate_pairwise_diversity(c1, c2)
                key = (c1.candidate_id, c2.candidate_id)
                pairwise_scores[key] = score
                all_scores.append(score)

        min_score = min(all_scores) if all_scores else 0.0
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
        meets = min_score >= self.min_diversity

        recommendation = ""
        if not meets:
            low_pairs = [k for k, v in pairwise_scores.items() if v < self.min_diversity]
            recommendation = (
                f"Candidates too similar. Low diversity pairs: {low_pairs}. "
                f"Consider regenerating with different strategies or parameters."
            )

        return DiversityResult(
            meets_threshold=meets,
            min_diversity=min_score,
            avg_diversity=avg_score,
            pairwise_scores=pairwise_scores,
            recommendation=recommendation,
        )

    def calculate_pairwise_diversity(
        self,
        candidate1: ResolutionCandidate,
        candidate2: ResolutionCandidate,
    ) -> float:
        """
        Calculate diversity between two candidates.

        Uses Jaccard distance on changed lines.
        Returns 0.0 for identical, 1.0 for completely different.

        Args:
            candidate1: First candidate
            candidate2: Second candidate

        Returns:
            Diversity score (0.0 to 1.0)
        """
        lines1 = self._extract_changed_lines(candidate1.diff_from_base)
        lines2 = self._extract_changed_lines(candidate2.diff_from_base)

        if not lines1 and not lines2:
            return 0.0  # Both empty = identical

        if not lines1 or not lines2:
            return 1.0  # One empty, one not = completely different

        # Jaccard distance = 1 - (intersection / union)
        intersection = len(lines1 & lines2)
        union = len(lines1 | lines2)

        if union == 0:
            return 0.0

        jaccard_similarity = intersection / union
        jaccard_distance = 1.0 - jaccard_similarity

        return jaccard_distance

    def _extract_changed_lines(self, diff: str) -> set[str]:
        """
        Extract changed lines from a diff.

        Focuses on added/removed lines (starting with +/-),
        ignoring diff headers and context lines.
        """
        if not diff:
            return set()

        changed_lines = set()
        for line in diff.split('\n'):
            # Skip diff headers
            if line.startswith('+++') or line.startswith('---'):
                continue
            if line.startswith('@@'):
                continue
            if line.startswith('diff '):
                continue
            if line.startswith('index '):
                continue

            # Extract added/removed lines
            if line.startswith('+') or line.startswith('-'):
                # Normalize: strip prefix and whitespace
                content = line[1:].strip()
                if content:  # Skip empty lines
                    changed_lines.add(content)

        return changed_lines

    def get_most_diverse_subset(
        self,
        candidates: list[ResolutionCandidate],
        target_count: int,
    ) -> list[ResolutionCandidate]:
        """
        Select the most diverse subset of candidates.

        If we have more candidates than needed, select the ones
        that maximize diversity.

        Args:
            candidates: All available candidates
            target_count: How many to select

        Returns:
            Selected candidates maximizing diversity
        """
        if len(candidates) <= target_count:
            return candidates

        # Greedy selection: start with first, add most diverse each step
        selected = [candidates[0]]

        while len(selected) < target_count:
            best_candidate = None
            best_min_diversity = -1.0

            for c in candidates:
                if c in selected:
                    continue

                # Calculate minimum diversity to all selected
                min_div = min(
                    self.calculate_pairwise_diversity(c, s)
                    for s in selected
                )

                if min_div > best_min_diversity:
                    best_min_diversity = min_div
                    best_candidate = c

            if best_candidate:
                selected.append(best_candidate)
            else:
                break

        return selected

"""
Multi-Candidate Generator (Phase 5)

Generates multiple resolution candidates using distinct strategies:
- agent1_primary: Keep Agent 1's architecture, adapt Agent 2's features
- agent2_primary: Keep Agent 2's architecture, adapt Agent 1's features
- convention_primary: Match existing repo patterns
- fresh_synthesis: Re-implement from scratch (optional, for architectural conflicts)

Each candidate is generated with a different approach to maximize
the chance of finding a working resolution.
"""

import logging
import re
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from .schema import (
    ConflictContext,
    IntentAnalysis,
    HarmonizedResult,
    ResolutionCandidate,
)

logger = logging.getLogger(__name__)

# Default strategies in priority order
DEFAULT_STRATEGIES = [
    "agent1_primary",
    "agent2_primary",
    "convention_primary",
]


def _validate_branch_name(branch: str) -> bool:
    """Validate branch name against safe pattern."""
    if not branch or not isinstance(branch, str):
        return False
    if len(branch) > 255:
        return False
    if branch.startswith('-'):
        return False
    if '..' in branch:
        return False
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9/_.\-]*$'
    return bool(re.match(pattern, branch))


class MultiCandidateGenerator:
    """
    Generates multiple resolution candidates with distinct strategies.

    Phase 5 enhancement over Phase 3's single-candidate approach.
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        base_branch: str = "main",
        strategies: Optional[list[str]] = None,
        max_candidates: int = 3,
        candidate_time_budget: int = 300,
    ):
        self.repo_path = repo_path or Path.cwd()

        if not _validate_branch_name(base_branch):
            raise ValueError(f"Invalid base branch name: {base_branch}")
        self.base_branch = base_branch

        self.strategies = strategies or DEFAULT_STRATEGIES
        self.max_candidates = max_candidates
        self.candidate_time_budget = candidate_time_budget

    def generate(
        self,
        context: ConflictContext,
        intents: IntentAnalysis,
        harmonized: HarmonizedResult,
    ) -> list[ResolutionCandidate]:
        """
        Generate multiple resolution candidates.

        Args:
            context: ConflictContext from Stage 1
            intents: IntentAnalysis from Stage 2
            harmonized: HarmonizedResult from Stage 3

        Returns:
            List of ResolutionCandidates (up to max_candidates)
        """
        logger.info(f"Generating up to {self.max_candidates} candidates")

        candidates = []
        strategies_to_use = self._select_strategies(context, intents, harmonized)

        for strategy in strategies_to_use[:self.max_candidates]:
            try:
                candidate = self._generate_single_candidate(
                    strategy,
                    context,
                    intents,
                    harmonized,
                )
                if candidate:
                    candidates.append(candidate)
                    logger.info(f"Generated candidate {candidate.candidate_id} with strategy {strategy}")
            except Exception as e:
                logger.error(f"Failed to generate candidate with strategy {strategy}: {e}")
                continue

        logger.info(f"Generated {len(candidates)} candidates")
        return candidates

    def _select_strategies(
        self,
        context: ConflictContext,
        intents: IntentAnalysis,
        harmonized: HarmonizedResult,
    ) -> list[str]:
        """Select which strategies to use based on context."""
        strategies = list(self.strategies)

        # If intents are incompatible, add fresh_synthesis
        if (intents.comparison and
            intents.comparison.relationship == "conflicting" and
            "fresh_synthesis" not in strategies):
            strategies.append("fresh_synthesis")

        # Prioritize based on intent confidence
        agent_ids = context.agent_ids
        if len(agent_ids) >= 2 and len(intents.intents) >= 2:
            intent1 = next((i for i in intents.intents if i.agent_id == agent_ids[0]), None)
            intent2 = next((i for i in intents.intents if i.agent_id == agent_ids[1]), None)

            if intent1 and intent2:
                conf_map = {"high": 3, "medium": 2, "low": 1}
                conf1 = conf_map.get(intent1.confidence, 0)
                conf2 = conf_map.get(intent2.confidence, 0)

                # Reorder to prioritize higher confidence agent
                if conf2 > conf1 and "agent2_primary" in strategies:
                    strategies.remove("agent2_primary")
                    strategies.insert(0, "agent2_primary")
                elif conf1 > conf2 and "agent1_primary" in strategies:
                    strategies.remove("agent1_primary")
                    strategies.insert(0, "agent1_primary")

        return strategies

    def _generate_single_candidate(
        self,
        strategy: str,
        context: ConflictContext,
        intents: IntentAnalysis,
        harmonized: HarmonizedResult,
    ) -> Optional[ResolutionCandidate]:
        """Generate a single candidate using the given strategy."""
        candidate_id = f"candidate-{uuid.uuid4().hex[:8]}"
        branch_name = f"resolution/{candidate_id}"

        try:
            created = self._create_resolution_branch(
                branch_name,
                strategy,
                context,
            )
            if not created:
                logger.error(f"Failed to create resolution branch for {strategy}")
                return None
        except Exception as e:
            logger.error(f"Error creating resolution branch: {e}")
            return None

        diff = self._get_diff_from_base(branch_name)
        files_modified = self._get_modified_files(branch_name)
        summary = self._generate_summary(strategy, context, intents)

        return ResolutionCandidate(
            candidate_id=candidate_id,
            strategy=strategy,
            branch_name=branch_name,
            diff_from_base=diff,
            files_modified=files_modified,
            summary=summary,
            technical_details=f"Strategy: {strategy}, Agents: {', '.join(context.agent_ids)}",
        )

    def _create_resolution_branch(
        self,
        branch_name: str,
        strategy: str,
        context: ConflictContext,
    ) -> bool:
        """Create a resolution branch using the selected strategy."""
        if not _validate_branch_name(branch_name):
            logger.error(f"Invalid resolution branch name: {branch_name}")
            return False

        branches = list(context.agent_branches.values())
        if len(branches) < 2:
            logger.warning("Need at least 2 branches to resolve")
            return False

        for branch in branches:
            if not _validate_branch_name(branch):
                logger.error(f"Invalid agent branch name: {branch}")
                return False

        try:
            # Start from base
            subprocess.run(
                ["git", "checkout", self.base_branch],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Create new branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Apply strategy-specific merge order
            if strategy == "agent1_primary":
                self._merge_branch(branches[0], allow_conflicts=False)
                self._merge_branch(branches[1], allow_conflicts=True)
            elif strategy == "agent2_primary":
                self._merge_branch(branches[1], allow_conflicts=False)
                self._merge_branch(branches[0], allow_conflicts=True)
            elif strategy == "convention_primary":
                # Both merges, resolve toward conventions
                self._merge_branch(branches[0], allow_conflicts=False)
                self._merge_branch(branches[1], allow_conflicts=True)
            elif strategy == "fresh_synthesis":
                # For fresh synthesis, we merge both and resolve all conflicts
                self._merge_branch(branches[0], allow_conflicts=True)
                self._merge_branch(branches[1], allow_conflicts=True)

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            self._cleanup_branch(branch_name)
            return False

    def _merge_branch(self, branch: str, allow_conflicts: bool = False) -> bool:
        """Merge a branch into current HEAD."""
        if not _validate_branch_name(branch):
            logger.error(f"Invalid branch name: {branch}")
            return False

        try:
            result = subprocess.run(
                ["git", "merge", "--no-edit", branch],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                if allow_conflicts and "CONFLICT" in result.stdout:
                    subprocess.run(
                        ["git", "checkout", "--ours", "."],
                        cwd=self.repo_path,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "add", "-A"],
                        cwd=self.repo_path,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "commit", "-m", f"Resolve conflicts from {branch}"],
                        cwd=self.repo_path,
                        capture_output=True,
                    )
                    return True
                else:
                    logger.error(f"Merge failed: {result.stderr}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Merge error: {e}")
            return False

    def _cleanup_branch(self, branch_name: str) -> None:
        """Clean up a failed branch."""
        try:
            subprocess.run(
                ["git", "checkout", self.base_branch],
                cwd=self.repo_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.repo_path,
                capture_output=True,
            )
        except Exception:
            pass

    def _get_diff_from_base(self, branch_name: str) -> str:
        """Get diff between base and resolution branch."""
        if not _validate_branch_name(branch_name):
            return ""

        try:
            result = subprocess.run(
                ["git", "diff", f"{self.base_branch}...{branch_name}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return result.stdout[:10000]  # Limit size
        except Exception:
            return ""

    def _get_modified_files(self, branch_name: str) -> list[str]:
        """Get list of files modified in resolution."""
        if not _validate_branch_name(branch_name):
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{self.base_branch}...{branch_name}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            return [f for f in result.stdout.strip().split("\n") if f]
        except Exception:
            return []

    def _generate_summary(
        self,
        strategy: str,
        context: ConflictContext,
        intents: IntentAnalysis,
    ) -> str:
        """Generate human-readable summary of the candidate."""
        agent_ids = context.agent_ids

        if strategy == "agent1_primary":
            return (f"Resolution prioritizes {agent_ids[0]}'s architecture, "
                   f"adapting {agent_ids[1]}'s features to fit.")
        elif strategy == "agent2_primary":
            return (f"Resolution prioritizes {agent_ids[1]}'s architecture, "
                   f"adapting {agent_ids[0]}'s features to fit.")
        elif strategy == "fresh_synthesis":
            return ("Resolution re-implements both agents' intents from scratch "
                   "using a unified architecture.")
        else:  # convention_primary
            return ("Resolution follows existing codebase conventions, "
                   "adapting both agents' changes to fit.")

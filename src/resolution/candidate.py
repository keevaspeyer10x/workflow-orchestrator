"""
Candidate Generation (Basic - Phase 3)

Generates resolution candidates using different strategies:
- agent1_primary: Keep agent 1's architecture, adapt agent 2's features
- agent2_primary: Keep agent 2's architecture, adapt agent 1's features
- convention_primary: Match existing repo patterns

Phase 3 generates a single candidate (the most likely to succeed).
Phase 5 will generate multiple candidates with diversity enforcement.
"""

import logging
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


class CandidateGenerator:
    """
    Generates resolution candidates.

    Phase 3: Single candidate using best strategy.
    Phase 5: Multiple diverse candidates.
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        base_branch: str = "main",
    ):
        self.repo_path = repo_path or Path.cwd()
        self.base_branch = base_branch

    def generate(
        self,
        context: ConflictContext,
        intents: IntentAnalysis,
        harmonized: HarmonizedResult,
    ) -> list[ResolutionCandidate]:
        """
        Generate resolution candidates.

        Args:
            context: ConflictContext from Stage 1
            intents: IntentAnalysis from Stage 2
            harmonized: HarmonizedResult from Stage 3

        Returns:
            List of ResolutionCandidates (Phase 3: single candidate)
        """
        logger.info("Generating resolution candidates")

        # Determine best strategy based on intents and harmonization
        strategy = self._select_strategy(context, intents, harmonized)
        logger.info(f"Selected strategy: {strategy}")

        # Generate single candidate for Phase 3
        candidate = self._generate_candidate(
            strategy,
            context,
            intents,
            harmonized,
        )

        if candidate:
            return [candidate]
        return []

    def _select_strategy(
        self,
        context: ConflictContext,
        intents: IntentAnalysis,
        harmonized: HarmonizedResult,
    ) -> str:
        """Select the best resolution strategy."""

        # If intents are orthogonal, just merge (convention_primary)
        if intents.comparison and intents.comparison.relationship == "orthogonal":
            return "convention_primary"

        # If one agent has higher confidence, prefer their approach
        agent_ids = context.agent_ids
        if len(agent_ids) >= 2 and len(intents.intents) >= 2:
            intent1 = next((i for i in intents.intents if i.agent_id == agent_ids[0]), None)
            intent2 = next((i for i in intents.intents if i.agent_id == agent_ids[1]), None)

            if intent1 and intent2:
                conf_map = {"high": 3, "medium": 2, "low": 1}
                conf1 = conf_map.get(intent1.confidence, 0)
                conf2 = conf_map.get(intent2.confidence, 0)

                if conf1 > conf2:
                    return "agent1_primary"
                elif conf2 > conf1:
                    return "agent2_primary"

        # If build passed with harmonized interfaces, use convention_primary
        if harmonized.build_passes:
            return "convention_primary"

        # Default to agent1_primary (first discovered)
        return "agent1_primary"

    def _generate_candidate(
        self,
        strategy: str,
        context: ConflictContext,
        intents: IntentAnalysis,
        harmonized: HarmonizedResult,
    ) -> Optional[ResolutionCandidate]:
        """Generate a single candidate using the selected strategy."""

        candidate_id = f"candidate-{uuid.uuid4().hex[:8]}"
        branch_name = f"resolution/{candidate_id}"

        # Create resolution branch
        try:
            created = self._create_resolution_branch(
                branch_name,
                strategy,
                context,
            )
            if not created:
                logger.error("Failed to create resolution branch")
                return None
        except Exception as e:
            logger.error(f"Error creating resolution branch: {e}")
            return None

        # Get diff from base
        diff = self._get_diff_from_base(branch_name)

        # Get files modified
        files_modified = self._get_modified_files(branch_name)

        # Generate summary
        summary = self._generate_summary(strategy, context, intents)

        return ResolutionCandidate(
            candidate_id=candidate_id,
            strategy=strategy,
            branch_name=branch_name,
            diff_from_base=diff,
            files_modified=files_modified,
            summary=summary,
            technical_details=f"Strategy: {strategy}, "
                            f"Agents: {', '.join(context.agent_ids)}",
        )

    def _create_resolution_branch(
        self,
        branch_name: str,
        strategy: str,
        context: ConflictContext,
    ) -> bool:
        """Create a resolution branch using the selected strategy."""

        agent_ids = context.agent_ids
        branches = list(context.agent_branches.values())

        if len(branches) < 2:
            logger.warning("Need at least 2 branches to resolve")
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

            if strategy == "agent1_primary":
                # Merge agent1 first (their structure is primary)
                self._merge_branch(branches[0], allow_conflicts=False)
                # Then merge agent2's changes on top
                self._merge_branch(branches[1], allow_conflicts=True)

            elif strategy == "agent2_primary":
                # Merge agent2 first
                self._merge_branch(branches[1], allow_conflicts=False)
                # Then merge agent1's changes on top
                self._merge_branch(branches[0], allow_conflicts=True)

            elif strategy == "convention_primary":
                # Merge both, resolving conflicts toward conventions
                self._merge_branch(branches[0], allow_conflicts=False)
                self._merge_branch(branches[1], allow_conflicts=True)

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            # Cleanup
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
            return False

    def _merge_branch(self, branch: str, allow_conflicts: bool = False) -> bool:
        """Merge a branch into current HEAD."""
        try:
            result = subprocess.run(
                ["git", "merge", "--no-edit", branch],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                if allow_conflicts and "CONFLICT" in result.stdout:
                    # Auto-resolve conflicts by keeping current version
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

    def _get_diff_from_base(self, branch_name: str) -> str:
        """Get diff between base and resolution branch."""
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
        else:  # convention_primary
            return ("Resolution follows existing codebase conventions, "
                   "adapting both agents' changes to fit.")

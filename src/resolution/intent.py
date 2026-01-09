"""
Stage 2: Intent Extraction

Extracts agent intents from their work:
- Primary intent (what they're trying to accomplish)
- Hard constraints (must satisfy)
- Soft constraints (prefer)
- Evidence (citations to code/tests)
- Confidence score

Then compares intents to determine relationship:
- Compatible: Both can be satisfied
- Conflicting: Mutually exclusive
- Orthogonal: Independent

CRITICAL: If confidence is LOW, escalate instead of guessing.
"""

import logging
import re
from typing import Optional

from .schema import (
    ConflictContext,
    Constraint,
    ExtractedIntent,
    IntentComparison,
    IntentAnalysis,
)
from ..coordinator.schema import AgentManifest

logger = logging.getLogger(__name__)


class IntentExtractor:
    """
    Extracts and compares agent intents.

    Phase 3 (Basic): Uses heuristic extraction from manifests and code.
    Phase 5 (Advanced): Uses LLM for deeper understanding.
    """

    def __init__(self, llm_client=None):
        # Optional LLM client for Phase 5 advanced extraction
        self.llm_client = llm_client

        # Keywords indicating hard constraints
        self.hard_constraint_patterns = [
            (r"must\s+\w+", "must requirement"),
            (r"required\s+to", "required"),
            (r"cannot\s+\w+", "prohibition"),
            (r"always\s+\w+", "always rule"),
            (r"never\s+\w+", "never rule"),
            (r"security", "security constraint"),
            (r"authentication|authorization", "auth constraint"),
            (r"backward[s]?\s*compatible", "compatibility constraint"),
        ]

        # Keywords indicating soft constraints
        self.soft_constraint_patterns = [
            (r"should\s+\w+", "preference"),
            (r"prefer(?:ably)?", "preference"),
            (r"ideally", "ideal"),
            (r"try\s+to", "attempt"),
            (r"if\s+possible", "optional"),
        ]

    def extract(self, context: ConflictContext) -> IntentAnalysis:
        """
        Extract intents from all agents and compare them.

        Args:
            context: ConflictContext from Stage 1

        Returns:
            IntentAnalysis with extracted intents and comparison
        """
        logger.info("Stage 2: Extracting intents")

        intents = []

        # Extract intent for each agent
        for agent_id in context.agent_ids:
            # Get manifest if available
            manifest = None
            for m in context.agent_manifests:
                if m.agent.id == agent_id:
                    manifest = m
                    break

            # Get files for this agent
            agent_files = context.agent_files.get(agent_id, [])

            # Get derived changes
            derived = None
            for d in context.derived_manifests:
                if d.agent_id == agent_id:
                    derived = d
                    break

            intent = self._extract_single_intent(agent_id, manifest, agent_files, derived)
            intents.append(intent)

        # Compare intents if we have multiple
        comparison = None
        if len(intents) >= 2:
            comparison = self._compare_intents(intents)

        # Determine overall confidence
        overall_confidence = self._calculate_overall_confidence(intents, comparison)

        analysis = IntentAnalysis(
            intents=intents,
            comparison=comparison,
            overall_confidence=overall_confidence,
        )

        logger.info(f"Extracted {len(intents)} intents, confidence={overall_confidence}")
        return analysis

    def _extract_single_intent(
        self,
        agent_id: str,
        manifest: Optional[AgentManifest],
        agent_files: list,
        derived,
    ) -> ExtractedIntent:
        """Extract intent from a single agent's work."""

        # Start with manifest info if available
        if manifest:
            primary_intent = manifest.task.description
            user_prompt = manifest.task.user_prompt
            decisions = manifest.work.decisions
        else:
            primary_intent = f"Unknown task for {agent_id}"
            user_prompt = None
            decisions = []

        # Extract constraints from task description
        hard_constraints = []
        soft_constraints = []
        evidence = []

        text_to_analyze = primary_intent
        if user_prompt:
            text_to_analyze += " " + user_prompt
        if decisions:
            text_to_analyze += " " + " ".join(decisions)

        # Find hard constraints
        for pattern, constraint_type in self.hard_constraint_patterns:
            matches = re.findall(pattern, text_to_analyze, re.IGNORECASE)
            for match in matches:
                hard_constraints.append(Constraint(
                    description=match,
                    constraint_type="hard",
                    evidence=f"Found in task: '{match}'",
                    source="task",
                ))

        # Find soft constraints
        for pattern, constraint_type in self.soft_constraint_patterns:
            matches = re.findall(pattern, text_to_analyze, re.IGNORECASE)
            for match in matches:
                soft_constraints.append(Constraint(
                    description=match,
                    constraint_type="soft",
                    evidence=f"Found in task: '{match}'",
                    source="task",
                ))

        # Analyze code for additional constraints
        code_constraints = self._extract_constraints_from_code(agent_files)
        hard_constraints.extend(code_constraints["hard"])
        soft_constraints.extend(code_constraints["soft"])

        # Calculate confidence
        confidence, reasons = self._calculate_confidence(
            manifest, agent_files, hard_constraints, soft_constraints
        )

        # Find secondary effects
        secondary_effects = self._find_secondary_effects(agent_files, derived)

        return ExtractedIntent(
            agent_id=agent_id,
            primary_intent=primary_intent,
            secondary_effects=secondary_effects,
            hard_constraints=hard_constraints,
            soft_constraints=soft_constraints,
            assumptions=[],
            evidence=evidence,
            confidence=confidence,
            confidence_reasons=reasons,
        )

    def _extract_constraints_from_code(self, agent_files: list) -> dict:
        """Extract constraints from code changes."""
        hard = []
        soft = []

        for file_version in agent_files:
            content = file_version.content

            # Check for security-related code
            if re.search(r'(password|secret|token|api_key|auth)', content, re.IGNORECASE):
                hard.append(Constraint(
                    description="Security-sensitive code changes",
                    constraint_type="hard",
                    evidence=f"Security patterns in {file_version.path}",
                    source="code",
                ))

            # Check for database changes
            if re.search(r'(CREATE TABLE|ALTER TABLE|migration|schema)', content, re.IGNORECASE):
                hard.append(Constraint(
                    description="Database schema changes",
                    constraint_type="hard",
                    evidence=f"DB schema patterns in {file_version.path}",
                    source="code",
                ))

            # Check for API changes
            if re.search(r'(@app\.route|@api\.|endpoint|def\s+(?:get|post|put|delete)_)', content, re.IGNORECASE):
                hard.append(Constraint(
                    description="API endpoint changes",
                    constraint_type="hard",
                    evidence=f"API patterns in {file_version.path}",
                    source="code",
                ))

            # Check for test requirements (soft)
            if re.search(r'(def test_|@pytest|describe\(|it\()', content, re.IGNORECASE):
                soft.append(Constraint(
                    description="Test coverage expected",
                    constraint_type="soft",
                    evidence=f"Test patterns in {file_version.path}",
                    source="tests",
                ))

        # Deduplicate
        seen = set()
        unique_hard = []
        for c in hard:
            key = (c.description, c.source)
            if key not in seen:
                seen.add(key)
                unique_hard.append(c)

        seen = set()
        unique_soft = []
        for c in soft:
            key = (c.description, c.source)
            if key not in seen:
                seen.add(key)
                unique_soft.append(c)

        return {"hard": unique_hard, "soft": unique_soft}

    def _find_secondary_effects(self, agent_files: list, derived) -> list[str]:
        """Find secondary effects of the changes."""
        effects = []

        if derived:
            # Count file types
            py_count = sum(1 for f in derived.files_modified if f.endswith(".py"))
            js_count = sum(1 for f in derived.files_modified if f.endswith((".js", ".ts")))
            test_count = sum(1 for f in derived.files_modified if "test" in f.lower())

            if py_count > 0:
                effects.append(f"Modifies {py_count} Python files")
            if js_count > 0:
                effects.append(f"Modifies {js_count} JavaScript/TypeScript files")
            if test_count > 0:
                effects.append(f"Updates {test_count} test files")

            if derived.files_added:
                effects.append(f"Adds {len(derived.files_added)} new files")
            if derived.files_deleted:
                effects.append(f"Removes {len(derived.files_deleted)} files")

        return effects

    def _calculate_confidence(
        self,
        manifest: Optional[AgentManifest],
        agent_files: list,
        hard_constraints: list,
        soft_constraints: list,
    ) -> tuple[str, list[str]]:
        """Calculate confidence in intent extraction."""
        score = 0.5  # Start at medium
        reasons = []

        # Boost if manifest available
        if manifest and manifest.task.description:
            score += 0.2
            reasons.append("Task description available")
        else:
            score -= 0.2
            reasons.append("No task description")

        # Boost if constraints found
        if hard_constraints:
            score += 0.1
            reasons.append(f"Found {len(hard_constraints)} hard constraints")

        # Penalize if very few files
        if len(agent_files) == 0:
            score -= 0.3
            reasons.append("No files to analyze")

        # Penalize if too many files (complex change)
        if len(agent_files) > 20:
            score -= 0.1
            reasons.append("Large change set (>20 files)")

        # Convert score to confidence level
        if score >= 0.7:
            return "high", reasons
        elif score >= 0.4:
            return "medium", reasons
        else:
            return "low", reasons

    def _compare_intents(self, intents: list[ExtractedIntent]) -> IntentComparison:
        """Compare intents from multiple agents."""
        logger.info(f"Comparing {len(intents)} intents")

        shared_constraints = []
        conflicting_constraints = []

        # Compare all pairs of intents
        for i, intent1 in enumerate(intents):
            for intent2 in intents[i + 1:]:
                # Find shared constraints
                for c1 in intent1.hard_constraints:
                    for c2 in intent2.hard_constraints:
                        if self._constraints_similar(c1, c2):
                            shared_constraints.append(c1)

                # Find conflicting constraints
                conflicts = self._find_conflicting_constraints(
                    intent1.hard_constraints,
                    intent2.hard_constraints,
                )
                conflicting_constraints.extend(conflicts)

        # Determine relationship
        if conflicting_constraints:
            relationship = "conflicting"
            suggested_resolution = "Manual review needed - conflicting requirements"
            requires_human = True
        elif shared_constraints:
            relationship = "compatible"
            suggested_resolution = "Can merge both changes with shared constraints preserved"
            requires_human = False
        else:
            relationship = "orthogonal"
            suggested_resolution = "Changes are independent, can merge directly"
            requires_human = False

        # Calculate comparison confidence
        if all(i.confidence == "high" for i in intents):
            confidence = "high"
        elif any(i.confidence == "low" for i in intents):
            confidence = "low"
        else:
            confidence = "medium"

        return IntentComparison(
            relationship=relationship,
            shared_constraints=shared_constraints,
            conflicting_constraints=conflicting_constraints,
            suggested_resolution=suggested_resolution,
            requires_human_judgment=requires_human,
            confidence=confidence,
        )

    def _constraints_similar(self, c1: Constraint, c2: Constraint) -> bool:
        """Check if two constraints are similar."""
        # Normalize descriptions
        desc1 = c1.description.lower().strip()
        desc2 = c2.description.lower().strip()

        # Direct match
        if desc1 == desc2:
            return True

        # Keyword overlap
        words1 = set(desc1.split())
        words2 = set(desc2.split())
        overlap = words1 & words2
        if len(overlap) >= 2 and len(overlap) / max(len(words1), len(words2)) > 0.5:
            return True

        return False

    def _find_conflicting_constraints(
        self,
        constraints1: list[Constraint],
        constraints2: list[Constraint],
    ) -> list[tuple]:
        """Find constraints that conflict with each other."""
        conflicts = []

        # Known conflict patterns
        conflict_patterns = [
            # (pattern1, pattern2, reason)
            (r"add\s+\w+", r"remove\s+\w+", "Adding vs removing"),
            (r"create\s+\w+", r"delete\s+\w+", "Creating vs deleting"),
            (r"increase\s+\w+", r"decrease\s+\w+", "Increasing vs decreasing"),
            (r"enable\s+\w+", r"disable\s+\w+", "Enabling vs disabling"),
        ]

        for c1 in constraints1:
            for c2 in constraints2:
                for p1, p2, reason in conflict_patterns:
                    if (re.search(p1, c1.description, re.IGNORECASE) and
                        re.search(p2, c2.description, re.IGNORECASE)):
                        conflicts.append((c1, c2, reason))
                    elif (re.search(p2, c1.description, re.IGNORECASE) and
                          re.search(p1, c2.description, re.IGNORECASE)):
                        conflicts.append((c1, c2, reason))

        return conflicts

    def _calculate_overall_confidence(
        self,
        intents: list[ExtractedIntent],
        comparison: Optional[IntentComparison],
    ) -> str:
        """Calculate overall confidence in the analysis."""
        if not intents:
            return "low"

        # If any intent has low confidence, overall is low
        if any(i.confidence == "low" for i in intents):
            return "low"

        # If comparison requires human judgment, lower confidence
        if comparison and comparison.requires_human_judgment:
            return "low" if comparison.confidence == "low" else "medium"

        # All high = high
        if all(i.confidence == "high" for i in intents):
            if comparison and comparison.confidence == "high":
                return "high"
            return "medium"

        return "medium"

    # ========================================================================
    # Phase 5: LLM-based Intent Extraction (for CLI ours/theirs scenarios)
    # ========================================================================

    def extract_from_diff_with_llm(
        self,
        side: str,
        base_content: Optional[str],
        side_content: str,
        file_path: str,
    ) -> ExtractedIntent:
        """
        Extract intent from a diff using LLM.

        Used by CLI conflict resolution (ours/theirs scenarios) where we don't
        have agent manifests, only code diffs.

        Args:
            side: "ours" or "theirs"
            base_content: Common ancestor content (may be None for new files)
            side_content: This side's content
            file_path: Path to the file

        Returns:
            ExtractedIntent with LLM-extracted information
        """
        import json

        if not self.llm_client:
            # Fall back to heuristic extraction
            return self._extract_from_diff_heuristic(side, base_content, side_content, file_path)

        # Build diff summary
        diff_lines = []
        if base_content:
            base_lines = base_content.splitlines()
            side_lines = side_content.splitlines()
            added = set(side_lines) - set(base_lines)
            removed = set(base_lines) - set(side_lines)
            for line in list(removed)[:15]:
                diff_lines.append(f"- {line[:100]}")
            for line in list(added)[:15]:
                diff_lines.append(f"+ {line[:100]}")

        diff_summary = "\n".join(diff_lines[:30])

        prompt = f'''Analyze this code change and extract the intent.

File: {file_path}
Side: {side}

Changes:
```
{diff_summary}
```

Full {side} version (first 100 lines):
```
{side_content[:5000]}
```

Respond in JSON format:
{{
  "primary_intent": "One sentence describing what this change is trying to do",
  "hard_constraints": ["constraint that MUST be satisfied"],
  "soft_constraints": ["preference that should be followed if possible"],
  "confidence": "high" | "medium" | "low"
}}

Output only valid JSON, no markdown or explanation.
'''

        try:
            response = self.llm_client.generate(prompt, max_tokens=500)

            # Clean response
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()

            data = json.loads(response)

            # Convert to Constraint objects
            hard_constraints = [
                Constraint(
                    description=c,
                    constraint_type="hard",
                    evidence=f"LLM extracted from {file_path}",
                    source="inferred",
                )
                for c in data.get("hard_constraints", [])
            ]
            soft_constraints = [
                Constraint(
                    description=c,
                    constraint_type="soft",
                    evidence=f"LLM extracted from {file_path}",
                    source="inferred",
                )
                for c in data.get("soft_constraints", [])
            ]

            confidence = data.get("confidence", "medium")
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"

            return ExtractedIntent(
                agent_id=side,  # Use "ours" or "theirs" as agent_id
                primary_intent=data.get("primary_intent", "Unknown intent"),
                hard_constraints=hard_constraints,
                soft_constraints=soft_constraints,
                confidence=confidence,
                confidence_reasons=["LLM-based extraction"],
            )

        except Exception as e:
            logger.warning(f"LLM intent extraction failed for {side}: {e}")
            return self._extract_from_diff_heuristic(side, base_content, side_content, file_path)

    def _extract_from_diff_heuristic(
        self,
        side: str,
        base_content: Optional[str],
        side_content: str,
        file_path: str,
    ) -> ExtractedIntent:
        """
        Fallback heuristic extraction when LLM is unavailable.

        Uses pattern matching to extract constraints from code.
        """
        hard_constraints = []
        soft_constraints = []

        # Analyze the side content for constraints
        for pattern, constraint_type in self.hard_constraint_patterns:
            matches = re.findall(pattern, side_content, re.IGNORECASE)
            for match in matches[:3]:  # Limit to avoid noise
                hard_constraints.append(Constraint(
                    description=match,
                    constraint_type="hard",
                    evidence=f"Pattern match in {file_path}",
                    source="code",
                ))

        for pattern, constraint_type in self.soft_constraint_patterns:
            matches = re.findall(pattern, side_content, re.IGNORECASE)
            for match in matches[:3]:
                soft_constraints.append(Constraint(
                    description=match,
                    constraint_type="soft",
                    evidence=f"Pattern match in {file_path}",
                    source="code",
                ))

        # Try to infer primary intent from changes
        primary_intent = f"Changes to {file_path}"
        if base_content:
            added_lines = len(side_content.splitlines()) - len(base_content.splitlines())
            if added_lines > 10:
                primary_intent = f"Adds significant code to {file_path}"
            elif added_lines < -10:
                primary_intent = f"Removes code from {file_path}"
            else:
                primary_intent = f"Modifies {file_path}"

        return ExtractedIntent(
            agent_id=side,
            primary_intent=primary_intent,
            hard_constraints=hard_constraints,
            soft_constraints=soft_constraints,
            confidence="low",  # Heuristic = low confidence
            confidence_reasons=["Heuristic extraction (no LLM)"],
        )

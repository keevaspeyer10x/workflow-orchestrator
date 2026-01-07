"""
WF-008: AI Critique at Phase Gates

Lightweight AI critique at phase transitions to catch issues early
before they compound. Uses fast models via ReviewRouter.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import WorkflowEngine

logger = logging.getLogger(__name__)


class ObservationSeverity(str, Enum):
    """Severity levels for critique observations."""
    CRITICAL = "critical"
    WARNING = "warning"
    PASS = "pass"
    INFO = "info"


@dataclass
class CritiqueObservation:
    """A single observation from the critique."""
    message: str
    severity: ObservationSeverity


@dataclass
class CritiqueResult:
    """Result of a phase critique."""
    observations: list[CritiqueObservation] = field(default_factory=list)
    recommendation: Optional[str] = None

    @property
    def should_block(self) -> bool:
        """Return True if any critical issues were found."""
        return any(
            obs.severity == ObservationSeverity.CRITICAL
            for obs in self.observations
        )

    @property
    def has_warnings(self) -> bool:
        """Return True if any warnings were found."""
        return any(
            obs.severity == ObservationSeverity.WARNING
            for obs in self.observations
        )

    @classmethod
    def parse(cls, raw_result: str) -> "CritiqueResult":
        """Parse raw critique output into structured result."""
        observations = []
        recommendation = None

        lines = raw_result.strip().split("\n")
        in_observations = False
        in_recommendation = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect sections
            if "observation" in line.lower() and ":" in line:
                in_observations = True
                in_recommendation = False
                continue
            if "recommendation" in line.lower() and ":" in line:
                in_observations = False
                in_recommendation = True
                continue

            # Parse observations
            if in_observations and line.startswith("-"):
                content = line[1:].strip()
                severity = ObservationSeverity.INFO

                # Detect severity from prefix
                upper_content = content.upper()
                if upper_content.startswith("CRITICAL"):
                    severity = ObservationSeverity.CRITICAL
                    content = content[8:].strip(": ")
                elif upper_content.startswith("WARNING"):
                    severity = ObservationSeverity.WARNING
                    content = content[7:].strip(": ")
                elif upper_content.startswith("PASS"):
                    severity = ObservationSeverity.PASS
                    content = content[4:].strip(": ")

                observations.append(CritiqueObservation(content, severity))

            # Parse recommendation
            if in_recommendation and not line.startswith("-"):
                recommendation = line

        return cls(observations=observations, recommendation=recommendation)


# Critique prompts for each phase transition
CRITIQUE_PROMPTS = {
    "PLAN_EXECUTE": """You are reviewing a development plan before implementation begins.

## Task
{task}

## Constraints
{constraints}

## Completed Planning Items
{completed_items}

## Skipped Items
{skipped_items}

## Your Role
Provide a brief critique focusing on:
1. Are requirements clear and unambiguous?
2. Are risks properly identified?
3. Is the test strategy adequate?
4. Are there any missing dependencies?

Format your response as:
Observations:
- CRITICAL: [issue that must be addressed]
- WARNING: [potential issue to consider]
- PASS: [aspect that looks good]

Recommendation: [brief summary of whether to proceed]
""",

    "EXECUTE_REVIEW": """You are reviewing implementation before code review begins.

## Task
{task}

## Completed Implementation Items
{completed_items}

## Skipped Items
{skipped_items}

## Git Changes
{git_diff_stat}

## Your Role
Provide a brief critique focusing on:
1. Are all planned items complete?
2. Were tests written and passing?
3. Are there any TODO comments left in code?
4. Is the implementation scope appropriate?

Format your response as:
Observations:
- CRITICAL: [issue that must be addressed]
- WARNING: [potential issue to consider]
- PASS: [aspect that looks good]

Recommendation: [brief summary of whether to proceed]
""",

    "REVIEW_VERIFY": """You are reviewing before verification begins.

## Task
{task}

## Review Findings Addressed
{completed_items}

## Skipped Review Items
{skipped_items}

## Your Role
Provide a brief critique focusing on:
1. Were review findings addressed?
2. Are there any unresolved issues?
3. Is documentation updated?

Format your response as:
Observations:
- CRITICAL: [issue that must be addressed]
- WARNING: [potential issue to consider]
- PASS: [aspect that looks good]

Recommendation: [brief summary of whether to proceed]
""",

    "VERIFY_DOCUMENT": """You are reviewing before documentation update begins.

## Task
{task}

## Verification Results
{completed_items}

## Skipped Items
{skipped_items}

## Your Role
Provide a brief critique focusing on:
1. Did all tests pass?
2. Were verification criteria met?
3. Any remaining concerns before documenting?

Format your response as:
Observations:
- CRITICAL: [issue that must be addressed]
- WARNING: [potential issue to consider]
- PASS: [aspect that looks good]

Recommendation: [brief summary of whether to proceed]
""",

    "DOCUMENT_LEARN": """You are reviewing before the learning phase begins.

## Task
{task}

## Documentation Updates
{completed_items}

## Skipped Items
{skipped_items}

## Your Role
Provide a brief critique focusing on:
1. Is documentation complete and accurate?
2. Were changelog entries added?
3. Any updates needed before capturing learnings?

Format your response as:
Observations:
- CRITICAL: [issue that must be addressed]
- WARNING: [potential issue to consider]
- PASS: [aspect that looks good]

Recommendation: [brief summary of whether to proceed]
""",

    "VERIFY_LEARN": """You are reviewing before the learning phase begins.

## Task
{task}

## Verification Results
{completed_items}

## Skipped Items
{skipped_items}

## Your Role
Provide a brief critique focusing on:
1. Did verification pass successfully?
2. Any remaining issues to address?
3. Any concerns before capturing learnings?

Format your response as:
Observations:
- CRITICAL: [issue that must be addressed]
- WARNING: [potential issue to consider]
- PASS: [aspect that looks good]

Recommendation: [brief summary of whether to proceed]
""",
}


class PhaseCritique:
    """
    Lightweight AI critique at phase transitions.

    Uses the ReviewRouter to send critique requests to fast models
    (e.g., Gemini Flash, GPT-4o-mini) for quick feedback.
    """

    def __init__(
        self,
        working_dir: Path,
        max_context_tokens: int = 8000,
        timeout: int = 30,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.max_context_tokens = max_context_tokens
        self.timeout = timeout

    def collect_context(self, engine: "WorkflowEngine") -> dict:
        """Gather context for critique from workflow state."""
        if not engine.state:
            return {}

        current_phase_id = engine.state.current_phase_id
        phase = engine.state.phases.get(current_phase_id)

        # Get completed items with notes
        completed_items = []
        if phase:
            for item_id, item in phase.items.items():
                if item.status.value == "completed":
                    completed_items.append({
                        "id": item_id,
                        "notes": item.notes or "No notes"
                    })

        # Get skipped items
        skipped_items = engine.get_skipped_items(current_phase_id)

        # Get git diff stat
        git_diff_stat = self._get_git_diff_stat()

        # Get next phase
        next_phase_id = self._get_next_phase_id(engine)

        return {
            "task": engine.state.task_description or "No task description",
            "constraints": engine.state.constraints or [],
            "current_phase": current_phase_id,
            "next_phase": next_phase_id,
            "completed_items": completed_items,
            "skipped_items": skipped_items,
            "git_diff_stat": git_diff_stat,
        }

    def _get_next_phase_id(self, engine: "WorkflowEngine") -> Optional[str]:
        """Get the ID of the next phase."""
        if not engine.workflow_def:
            return None

        phase_ids = [p.id for p in engine.workflow_def.phases]
        current_idx = -1

        for i, phase_id in enumerate(phase_ids):
            if phase_id == engine.state.current_phase_id:
                current_idx = i
                break

        if current_idx >= 0 and current_idx < len(phase_ids) - 1:
            return phase_ids[current_idx + 1]
        return None

    def _get_git_diff_stat(self) -> str:
        """Get git diff stat for changed files."""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD~5"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip() or "No changes"
            return "Unable to get git diff"
        except Exception as e:
            logger.debug(f"Git diff failed: {e}")
            return "Git not available"

    def _serialize_context(self, context: dict) -> str:
        """Serialize context to string, respecting token limit."""
        # Format completed items
        completed_str = ""
        for item in context.get("completed_items", []):
            completed_str += f"- {item['id']}: {item['notes']}\n"

        # Format skipped items
        skipped_str = ""
        for item_id, reason in context.get("skipped_items", []):
            skipped_str += f"- {item_id}: {reason}\n"

        # Format constraints
        constraints_str = "\n".join(
            f"- {c}" for c in context.get("constraints", [])
        ) or "None"

        result = f"""Task: {context.get('task', 'N/A')}
Constraints:
{constraints_str}

Completed Items:
{completed_str or 'None'}

Skipped Items:
{skipped_str or 'None'}

Git Changes:
{context.get('git_diff_stat', 'N/A')}
"""

        # Truncate if needed
        if len(result) > self.max_context_tokens:
            result = result[:self.max_context_tokens - 50] + "\n... (truncated)"

        return result

    def _get_transition_key(self, from_phase: str, to_phase: str) -> str:
        """Get the prompt key for a phase transition."""
        return f"{from_phase}_{to_phase}"

    def _get_model(self, model_setting: str) -> str:
        """Resolve model setting to actual model ID."""
        if model_setting == "latest":
            try:
                from .model_registry import ModelRegistry
                registry = ModelRegistry(self.working_dir)
                return registry.get_latest_model("gemini") or "google/gemini-2.0-flash-001"
            except Exception:
                return "google/gemini-2.0-flash-001"
        return model_setting

    def run(
        self,
        engine: "WorkflowEngine",
        from_phase: str,
        to_phase: str,
    ) -> Optional[CritiqueResult]:
        """
        Run critique for a phase transition.

        Args:
            engine: The workflow engine with current state
            from_phase: The phase being completed
            to_phase: The phase being entered

        Returns:
            CritiqueResult or None if critique failed
        """
        try:
            # Get the appropriate prompt
            transition_key = self._get_transition_key(from_phase, to_phase)
            prompt_template = CRITIQUE_PROMPTS.get(transition_key)

            if not prompt_template:
                logger.warning(f"No critique prompt for transition {transition_key}")
                return None

            # Collect and format context
            context = self.collect_context(engine)

            # Format the prompt
            prompt = prompt_template.format(
                task=context.get("task", "N/A"),
                constraints="\n".join(f"- {c}" for c in context.get("constraints", [])) or "None",
                completed_items="\n".join(
                    f"- {item['id']}: {item['notes']}"
                    for item in context.get("completed_items", [])
                ) or "None",
                skipped_items="\n".join(
                    f"- {item_id}: {reason}"
                    for item_id, reason in context.get("skipped_items", [])
                ) or "None",
                git_diff_stat=context.get("git_diff_stat", "N/A"),
            )

            # Call the API
            result = self._call_api(prompt)

            if result:
                return CritiqueResult.parse(result)
            return None

        except Exception as e:
            logger.warning(f"Critique failed: {e}. Continuing without critique.")
            return None

    def _call_api(self, prompt: str) -> Optional[str]:
        """Call the AI API for critique. Override for testing."""
        try:
            from .review import ReviewRouter

            router = ReviewRouter(
                self.working_dir,
                context_limit=self.max_context_tokens,
            )

            # Use the router to execute a lightweight review
            result = router.execute_review(
                review_type="critique",
                context_override=prompt,
            )

            if result and result.content:
                return result.content
            return None

        except Exception as e:
            logger.warning(f"API call failed: {e}")
            return None

    def run_if_enabled(
        self,
        engine: "WorkflowEngine",
        from_phase: str,
        to_phase: str,
    ) -> Optional[CritiqueResult]:
        """
        Run critique only if enabled in workflow settings.

        Args:
            engine: The workflow engine
            from_phase: The phase being completed
            to_phase: The phase being entered

        Returns:
            CritiqueResult or None if disabled/failed
        """
        # Check if critique is enabled
        if engine.workflow_def and engine.workflow_def.settings:
            critique_enabled = engine.workflow_def.settings.get("phase_critique", True)
            if not critique_enabled:
                logger.debug("Phase critique disabled in workflow settings")
                return None

        return self.run(engine, from_phase, to_phase)


def format_critique_result(result: CritiqueResult, from_phase: str, to_phase: str) -> str:
    """Format critique result for display."""
    lines = [
        "=" * 60,
        f"AI CRITIQUE: {from_phase} -> {to_phase}",
        "=" * 60,
        "",
        "Observations:",
    ]

    for obs in result.observations:
        if obs.severity == ObservationSeverity.CRITICAL:
            prefix = "  CRITICAL"
        elif obs.severity == ObservationSeverity.WARNING:
            prefix = "  WARNING"
        elif obs.severity == ObservationSeverity.PASS:
            prefix = "  PASS"
        else:
            prefix = "  INFO"

        lines.append(f"{prefix}: {obs.message}")

    lines.append("")

    if result.recommendation:
        lines.append(f"Recommendation: {result.recommendation}")
        lines.append("")

    if result.should_block:
        lines.append("Critical issues found. Address before proceeding.")
    elif result.has_warnings:
        lines.append("Warnings found. Review before proceeding.")
    else:
        lines.append("No blocking issues found.")

    lines.append("=" * 60)

    return "\n".join(lines)

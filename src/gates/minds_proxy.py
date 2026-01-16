"""
Minds Gate Proxy - Multi-model consensus for autonomous gate decisions.

Issue #39: Zero-Human Mode with Minds as Proxy

This module provides a multi-model consensus system to replace human approval gates.
Key features:
1. Weighted voting (smarter models like GPT have more weight)
2. Re-deliberation (dissenting models can reconsider after seeing other reasoning)
3. Certainty-based escalation (not just risk-based)
4. Full decision audit trail with rollback commands

User requirements addressed:
- Configurable thresholds with supermajority default
- Model weighting (ChatGPT smarter, DeepSeek less so)
- Re-deliberation: models that disagree see other reasoning
- Certainty-based: critical but certain = OK to proceed
- Human sees reasoning/alternatives at end for potential rollback
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Model Weights - Smarter models have more say (per user feedback)
# =============================================================================

MODEL_WEIGHTS = {
    # High capability models - double weight
    "openai/gpt-5.2-codex-max": 2.0,
    "openai/gpt-5.2": 2.0,
    "openai/gpt-4-turbo": 1.8,
    "anthropic/claude-3-opus": 2.0,
    "anthropic/claude-3.5-sonnet": 1.8,
    # Medium capability
    "google/gemini-3-pro": 1.5,
    "google/gemini-2.5-flash": 1.2,
    "xai/grok-4.1": 1.0,
    "xai/grok-3": 1.0,
    # Lower weight (per user feedback about DeepSeek)
    "deepseek/deepseek-chat": 0.5,
    "deepseek/deepseek-coder": 0.5,
}

DEFAULT_MODEL_WEIGHT = 1.0


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class GateContext:
    """
    Context information for gate evaluation.

    Provides all relevant information for models to make a decision.
    """
    gate_id: str
    phase: str
    operation: str
    risk_level: str  # low, medium, high, critical
    commit_sha: Optional[str] = None
    diff_summary: Optional[str] = None
    files_changed: list[str] = field(default_factory=list)
    test_results: Optional[str] = None
    review_summary: Optional[str] = None
    additional_context: dict = field(default_factory=dict)

    def to_prompt(self) -> str:
        """Format context for inclusion in prompts."""
        parts = [
            f"Gate: {self.gate_id}",
            f"Phase: {self.phase}",
            f"Operation: {self.operation}",
            f"Risk Level: {self.risk_level}",
        ]
        if self.commit_sha:
            parts.append(f"Commit: {self.commit_sha}")
        if self.diff_summary:
            parts.append(f"Changes Summary: {self.diff_summary}")
        if self.files_changed:
            parts.append(f"Files Changed: {', '.join(self.files_changed[:10])}")
        if self.test_results:
            parts.append(f"Test Results: {self.test_results}")
        if self.review_summary:
            parts.append(f"Review Summary: {self.review_summary}")
        return "\n".join(parts)


@dataclass
class MindsDecision:
    """
    Result of multi-model gate evaluation.

    Captures the consensus decision with full audit trail for transparency.
    """
    gate_id: str
    decision: Literal["APPROVE", "REJECT", "ESCALATE"]
    certainty: float  # 0.0-1.0 based on consensus strength
    risk_level: str
    model_votes: dict[str, dict]  # model -> {vote, reasoning}
    weighted_consensus: float  # Weighted approval ratio
    reasoning_summary: str
    rollback_command: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    re_deliberation: Optional[dict] = None  # model -> {changed, final_vote, reasoning}

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "gate_id": self.gate_id,
            "decision": self.decision,
            "certainty": self.certainty,
            "risk_level": self.risk_level,
            "model_votes": self.model_votes,
            "weighted_consensus": self.weighted_consensus,
            "reasoning_summary": self.reasoning_summary,
            "rollback_command": self.rollback_command,
            "timestamp": self.timestamp.isoformat(),
            "re_deliberation": self.re_deliberation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MindsDecision":
        """Create from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif timestamp is None:
            timestamp = datetime.now(timezone.utc)

        return cls(
            gate_id=data["gate_id"],
            decision=data["decision"],
            certainty=data["certainty"],
            risk_level=data["risk_level"],
            model_votes=data["model_votes"],
            weighted_consensus=data["weighted_consensus"],
            reasoning_summary=data["reasoning_summary"],
            rollback_command=data["rollback_command"],
            timestamp=timestamp,
            re_deliberation=data.get("re_deliberation"),
        )


# =============================================================================
# Core Functions
# =============================================================================

def weighted_vote(
    votes: dict[str, str],
    weights: Optional[dict[str, float]] = None,
) -> tuple[str, float]:
    """
    Calculate weighted consensus from model votes.

    Args:
        votes: Dict of model -> vote ("APPROVE" or "REJECT")
        weights: Optional custom weights (uses MODEL_WEIGHTS if None)

    Returns:
        Tuple of (decision, confidence) where confidence is approval ratio
    """
    weights = weights or MODEL_WEIGHTS

    approve_weight = 0.0
    reject_weight = 0.0

    for model, vote in votes.items():
        weight = weights.get(model, DEFAULT_MODEL_WEIGHT)
        if vote == "APPROVE":
            approve_weight += weight
        else:
            reject_weight += weight

    total_weight = approve_weight + reject_weight

    if total_weight == 0:
        return "REJECT", 0.0

    if approve_weight > reject_weight:
        return "APPROVE", approve_weight / total_weight
    elif reject_weight > approve_weight:
        return "REJECT", reject_weight / total_weight
    else:
        # Tie - default to APPROVE (per supermajority principle)
        return "APPROVE", 0.5


def should_escalate(
    decision: str,
    certainty: float,
    risk_level: str,
) -> bool:
    """
    Determine if decision should be escalated to human review.

    Based on user requirement: Certainty matters more than risk.
    Even CRITICAL can proceed if certainty is very high.

    Args:
        decision: The consensus decision (APPROVE/REJECT)
        certainty: Confidence level 0.0-1.0
        risk_level: Risk level (low, medium, high, critical)

    Returns:
        True if should escalate to human review
    """
    risk_level = risk_level.upper()

    # Very high certainty (>=0.95) - proceed even on CRITICAL
    # User said: "If it's critical but certain perhaps its OK to proceed"
    if certainty >= 0.95:
        # Only escalate if CRITICAL AND unanimous reject
        return risk_level == "CRITICAL" and decision == "REJECT"

    # High certainty (>=0.80) - only escalate CRITICAL
    if certainty >= 0.80:
        return risk_level == "CRITICAL"

    # Medium certainty (>=0.60) - escalate HIGH and CRITICAL
    if certainty >= 0.60:
        return risk_level in ("HIGH", "CRITICAL")

    # Low certainty (<0.60) - always escalate
    return True


def call_model(model: str, prompt: str) -> str:
    """
    Call a model via API.

    Uses OpenRouter for unified access to multiple models.

    Args:
        model: Model ID (e.g., "openai/gpt-5.2-codex-max")
        prompt: The prompt to send

    Returns:
        Model response as string
    """
    import requests

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
        },
        timeout=60,
    )

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def re_deliberate(
    dissenting_model: str,
    dissenting_vote: str,
    other_votes: dict[str, tuple[str, str]],  # model -> (vote, reasoning)
    gate_context: GateContext,
) -> dict:
    """
    Allow dissenting model to reconsider after seeing other reasoning.

    Per user requirement: "other models can explain their logic to it
    and see if that changes its mind"

    Args:
        dissenting_model: Model that voted differently from majority
        dissenting_vote: The dissenting vote (APPROVE/REJECT)
        other_votes: Other models' votes and reasoning
        gate_context: Context for the gate decision

    Returns:
        Dict with {final_vote, changed, reasoning}
    """
    # Format other models' reasoning
    other_reasoning = []
    for model, (vote, reasoning) in other_votes.items():
        other_reasoning.append(f"- {model} voted {vote}: {reasoning}")

    prompt = f"""You previously voted {dissenting_vote} on this gate decision.

Gate Context:
{gate_context.to_prompt()}

Other models voted differently and provided this reasoning:
{chr(10).join(other_reasoning)}

Please reconsider your vote after seeing these perspectives:
1. Do any of these arguments address your concerns?
2. Were there factors you hadn't considered?
3. Do you want to change your vote, or do you still have unaddressed concerns?

Respond with JSON (no markdown):
{{
    "final_vote": "APPROVE" or "REJECT",
    "changed": true or false,
    "reasoning": "explanation of your final decision"
}}
"""

    try:
        response = call_model(dissenting_model, prompt)

        # Parse response
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]

        result = json.loads(response.strip())
        return {
            "final_vote": result.get("final_vote", dissenting_vote),
            "changed": result.get("changed", False),
            "reasoning": result.get("reasoning", "No reasoning provided"),
        }

    except Exception as e:
        logger.warning(f"Re-deliberation failed for {dissenting_model}: {e}")
        # Keep original vote on failure
        return {
            "final_vote": dissenting_vote,
            "changed": False,
            "reasoning": f"Re-deliberation failed: {e}",
        }


def generate_rollback_command(context: GateContext) -> str:
    """
    Generate a rollback command for this gate decision.

    Per user requirement: Human should be able to rollback if needed.

    Args:
        context: Gate context with commit info

    Returns:
        Git command to rollback the change
    """
    if context.commit_sha:
        return f"git revert {context.commit_sha}"
    else:
        return "git reset --hard HEAD~1  # Caution: verify commit count first"


def write_decision(
    decision: MindsDecision,
    audit_path: Optional[Path] = None,
) -> None:
    """
    Write decision to audit trail (append-only JSONL).

    Args:
        decision: The MindsDecision to record
        audit_path: Path to audit file (default: .orchestrator/minds_decisions.jsonl)
    """
    if audit_path is None:
        audit_path = Path(".orchestrator") / "minds_decisions.jsonl"

    # Ensure directory exists
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    # Append to file
    with open(audit_path, "a") as f:
        f.write(json.dumps(decision.to_dict()) + "\n")

    logger.info(f"Recorded minds decision: {decision.gate_id} -> {decision.decision}")


# =============================================================================
# MindsGateProxy Class
# =============================================================================

class MindsGateProxy:
    """
    Multi-model consensus system for gate decisions.

    This class orchestrates the full gate evaluation process:
    1. Queries multiple models for their votes
    2. Calculates weighted consensus
    3. Triggers re-deliberation for dissenters
    4. Determines escalation based on certainty
    5. Records decision to audit trail
    """

    DEFAULT_MODELS = [
        "openai/gpt-4-turbo",
        "google/gemini-2.5-flash",
        "anthropic/claude-3.5-sonnet",
        "xai/grok-3",
        "deepseek/deepseek-chat",
    ]

    def __init__(
        self,
        models: Optional[list[str]] = None,
        model_weights: Optional[dict[str, float]] = None,
        approval_threshold: float = 0.6,  # Supermajority per user preference
        re_deliberation_enabled: bool = True,
        max_re_deliberation_rounds: int = 1,
    ):
        """
        Initialize MindsGateProxy.

        Args:
            models: List of models to query (default: DEFAULT_MODELS)
            model_weights: Custom weights for models
            approval_threshold: Minimum weighted approval ratio (default: 0.6)
            re_deliberation_enabled: Allow vote changes (default: True)
            max_re_deliberation_rounds: Max re-deliberation rounds (default: 1)
        """
        self.models = models or self.DEFAULT_MODELS
        self.model_weights = model_weights or MODEL_WEIGHTS
        self.approval_threshold = approval_threshold
        self.re_deliberation_enabled = re_deliberation_enabled
        self.max_re_deliberation_rounds = max_re_deliberation_rounds

    def evaluate(self, context: GateContext) -> MindsDecision:
        """
        Evaluate a gate using multi-model consensus.

        Args:
            context: Gate context with all relevant information

        Returns:
            MindsDecision with consensus result
        """
        # Step 1: Get initial votes from all models
        votes = {}
        vote_reasoning = {}

        for model in self.models:
            try:
                vote, reasoning = self._get_model_vote(model, context)
                votes[model] = vote
                vote_reasoning[model] = {"vote": vote, "reasoning": reasoning}
            except Exception as e:
                logger.warning(f"Failed to get vote from {model}: {e}")
                # Skip failed models rather than failing entirely

        if not votes:
            # All models failed - must escalate
            return MindsDecision(
                gate_id=context.gate_id,
                decision="ESCALATE",
                certainty=0.0,
                risk_level=context.risk_level,
                model_votes={},
                weighted_consensus=0.0,
                reasoning_summary="All models failed to respond - escalating to human",
                rollback_command=generate_rollback_command(context),
            )

        # Step 2: Calculate initial consensus
        decision, confidence = weighted_vote(votes, self.model_weights)

        # Step 3: Re-deliberation for dissenters (if enabled)
        re_delib_results = None
        if self.re_deliberation_enabled and confidence < 0.95:
            re_delib_results = self._run_re_deliberation(
                votes, vote_reasoning, context, decision
            )

            # Recalculate with updated votes
            if re_delib_results:
                for model, result in re_delib_results.items():
                    if result.get("changed"):
                        votes[model] = result["final_vote"]
                        vote_reasoning[model]["vote"] = result["final_vote"]
                        vote_reasoning[model]["reasoning"] = result["reasoning"]

                decision, confidence = weighted_vote(votes, self.model_weights)

        # Step 4: Determine if escalation needed
        final_decision = decision
        if should_escalate(decision, confidence, context.risk_level):
            final_decision = "ESCALATE"

        # Step 5: Generate reasoning summary
        reasoning_summary = self._generate_reasoning_summary(
            vote_reasoning, decision, confidence
        )

        # Step 6: Create and record decision
        minds_decision = MindsDecision(
            gate_id=context.gate_id,
            decision=final_decision,
            certainty=confidence,
            risk_level=context.risk_level,
            model_votes=vote_reasoning,
            weighted_consensus=confidence,
            reasoning_summary=reasoning_summary,
            rollback_command=generate_rollback_command(context),
            re_deliberation=re_delib_results,
        )

        # Write to audit trail
        write_decision(minds_decision)

        return minds_decision

    def _get_model_vote(
        self, model: str, context: GateContext
    ) -> tuple[str, str]:
        """Get a single model's vote and reasoning."""
        prompt = f"""You are evaluating whether to approve this workflow gate.

{context.to_prompt()}

Consider:
1. Is the operation safe to proceed?
2. Are there any blocking concerns?
3. What is your confidence level?

Respond with JSON (no markdown):
{{
    "vote": "APPROVE" or "REJECT",
    "reasoning": "brief explanation (1-2 sentences)",
    "confidence": 0.0 to 1.0
}}
"""
        response = call_model(model, prompt)

        # Parse response
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            result = json.loads(response.strip())
            return result.get("vote", "REJECT"), result.get("reasoning", "No reasoning")

        except json.JSONDecodeError:
            # Try to extract vote from plain text
            if "approve" in response.lower():
                return "APPROVE", response[:200]
            return "REJECT", response[:200]

    def _run_re_deliberation(
        self,
        votes: dict[str, str],
        vote_reasoning: dict[str, dict],
        context: GateContext,
        majority_decision: str,
    ) -> Optional[dict]:
        """Run re-deliberation for dissenting models."""
        # Find dissenters
        dissenters = [
            model for model, vote in votes.items()
            if vote != majority_decision
        ]

        if not dissenters:
            return None

        # Get majority reasoning
        majority_reasoning = {
            model: (info["vote"], info["reasoning"])
            for model, info in vote_reasoning.items()
            if info["vote"] == majority_decision
        }

        # Re-deliberate with each dissenter
        results = {}
        for model in dissenters:
            result = re_deliberate(
                dissenting_model=model,
                dissenting_vote=votes[model],
                other_votes=majority_reasoning,
                gate_context=context,
            )
            results[model] = result

        return results

    def _generate_reasoning_summary(
        self,
        vote_reasoning: dict[str, dict],
        decision: str,
        confidence: float,
    ) -> str:
        """Generate human-readable summary of reasoning."""
        approve_count = sum(1 for v in vote_reasoning.values() if v["vote"] == "APPROVE")
        total = len(vote_reasoning)

        summary = f"{approve_count}/{total} models voted APPROVE ({confidence:.0%} weighted confidence). "

        # Add key reasoning points
        key_points = []
        for model, info in vote_reasoning.items():
            if len(info.get("reasoning", "")) > 10:
                key_points.append(f"{model.split('/')[-1]}: {info['reasoning'][:100]}")

        if key_points:
            summary += "Key points: " + "; ".join(key_points[:3])

        return summary

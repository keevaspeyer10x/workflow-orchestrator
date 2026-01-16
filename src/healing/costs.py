"""Cost tracking and controls for healing operations.

This module tracks API costs and enforces limits.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict

from .config import get_config
from .safety import SafetyCategory


@dataclass
class CostStatus:
    """Current cost tracking status."""

    daily_cost_usd: float
    daily_limit_usd: float
    daily_validations: int
    validation_limit: int
    daily_embeddings: int
    budget_remaining_usd: float

    @property
    def is_over_budget(self) -> bool:
        """Check if daily budget is exceeded."""
        return self.daily_cost_usd >= self.daily_limit_usd

    @property
    def is_over_validation_limit(self) -> bool:
        """Check if validation limit is exceeded."""
        return self.daily_validations >= self.validation_limit


@dataclass
class CostTracker:
    """Track and limit API costs.

    This class monitors daily API usage across:
    - Embedding generation
    - Multi-model judging
    - LLM operations

    It enforces limits to prevent runaway costs.
    """

    # Daily tracking
    _daily_cost: float = 0.0
    _daily_validations: int = 0
    _daily_embeddings: int = 0
    _current_date: date = field(default_factory=date.today)

    # Cost estimates per operation (USD)
    COSTS: Dict[str, float] = field(
        default_factory=lambda: {
            "embedding": 0.0002,  # Per error embedding
            "judge_claude": 0.05,  # Claude Opus judge call
            "judge_gemini": 0.02,  # Gemini Pro judge call
            "judge_gpt": 0.05,  # GPT-5.2 judge call
            "judge_grok": 0.02,  # Grok judge call
            "pattern_lookup": 0.001,  # Supabase query
            "rag_search": 0.005,  # Vector similarity search
        }
    )

    def _maybe_reset_daily(self) -> None:
        """Reset daily counters if a new day has started."""
        today = date.today()
        if today > self._current_date:
            self._daily_cost = 0.0
            self._daily_validations = 0
            self._daily_embeddings = 0
            self._current_date = today

    def can_validate(self, safety: SafetyCategory) -> tuple[bool, str]:
        """Check if we can afford another validation.

        Args:
            safety: The safety category of the fix

        Returns:
            Tuple of (allowed, reason)
        """
        self._maybe_reset_daily()
        config = get_config()

        # Check daily cost limit
        if self._daily_cost >= config.max_daily_cost_usd:
            return False, f"Daily cost limit reached (${self._daily_cost:.2f})"

        # Check validation count limit
        if self._daily_validations >= config.max_validations_per_day:
            return False, f"Daily validation limit reached ({self._daily_validations})"

        # Estimate this validation's cost
        judge_count = self._get_judge_count(safety)
        estimated_cost = self._estimate_validation_cost(judge_count)

        if estimated_cost > config.max_cost_per_validation_usd:
            return (
                False,
                f"Validation too expensive (${estimated_cost:.2f} > ${config.max_cost_per_validation_usd:.2f})",
            )

        if self._daily_cost + estimated_cost > config.max_daily_cost_usd:
            return False, f"Would exceed daily limit (${self._daily_cost + estimated_cost:.2f})"

        return True, "OK"

    def record(self, operation: str, count: int = 1) -> float:
        """Record an operation's cost.

        Args:
            operation: The operation type (e.g., 'embedding', 'judge_claude')
            count: Number of times the operation occurred

        Returns:
            The cost that was recorded
        """
        self._maybe_reset_daily()

        cost = self.COSTS.get(operation, 0) * count
        self._daily_cost += cost

        if operation.startswith("judge"):
            self._daily_validations += count
        elif operation == "embedding":
            self._daily_embeddings += count

        return cost

    def get_status(self) -> CostStatus:
        """Get current cost status."""
        self._maybe_reset_daily()
        config = get_config()

        return CostStatus(
            daily_cost_usd=round(self._daily_cost, 4),
            daily_limit_usd=config.max_daily_cost_usd,
            daily_validations=self._daily_validations,
            validation_limit=config.max_validations_per_day,
            daily_embeddings=self._daily_embeddings,
            budget_remaining_usd=round(config.max_daily_cost_usd - self._daily_cost, 4),
        )

    def estimate_cost(self, safety: SafetyCategory) -> float:
        """Estimate the cost of a validation.

        Args:
            safety: The safety category

        Returns:
            Estimated cost in USD
        """
        judge_count = self._get_judge_count(safety)
        return self._estimate_validation_cost(judge_count)

    def _get_judge_count(self, safety: SafetyCategory) -> int:
        """Get number of judges required for safety category."""
        if safety == SafetyCategory.SAFE:
            return 1
        elif safety == SafetyCategory.MODERATE:
            return 2
        else:  # RISKY
            return 3

    def _estimate_validation_cost(self, judge_count: int) -> float:
        """Estimate the total cost of a validation."""
        # Average cost per judge (mixing models)
        avg_judge_cost = (
            self.COSTS["judge_claude"]
            + self.COSTS["judge_gemini"]
            + self.COSTS["judge_gpt"]
            + self.COSTS["judge_grok"]
        ) / 4

        return judge_count * avg_judge_cost

    def reset(self) -> None:
        """Reset all counters (for testing)."""
        self._daily_cost = 0.0
        self._daily_validations = 0
        self._daily_embeddings = 0
        self._current_date = date.today()


# Global cost tracker instance
_COST_TRACKER: CostTracker = None


def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker instance."""
    global _COST_TRACKER
    if _COST_TRACKER is None:
        _COST_TRACKER = CostTracker()
    return _COST_TRACKER


def reset_cost_tracker() -> None:
    """Reset the global cost tracker (for testing)."""
    global _COST_TRACKER
    _COST_TRACKER = None

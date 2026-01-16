"""Configuration for self-healing infrastructure.

This module provides configuration loading from environment variables.
Supabase configuration loading will be added in Phase 2.
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class HealingConfig:
    """Configuration loaded from environment variables.

    Phase 2 will add Supabase config loading.
    """

    # Feature flags
    enabled: bool = True
    auto_apply_safe: bool = True
    auto_apply_moderate: bool = False

    # Cost controls (needed early!)
    max_daily_cost_usd: float = 10.0
    max_validations_per_day: int = 100
    max_cost_per_validation_usd: float = 0.50

    # Safety
    protected_paths: List[str] = field(
        default_factory=lambda: [
            "src/auth/**",
            "migrations/**",
            "*.env*",
        ]
    )

    # Kill switch
    kill_switch_active: bool = False

    # Timeouts (critical for production)
    build_timeout_seconds: int = 300
    test_timeout_seconds: int = 600
    lint_timeout_seconds: int = 60
    judge_timeout_seconds: int = 30

    @classmethod
    def from_environment(cls) -> "HealingConfig":
        """Load config from environment variables.

        Environment variables:
        - HEALING_ENABLED (default: true)
        - HEALING_AUTO_APPLY_SAFE (default: true)
        - HEALING_AUTO_APPLY_MODERATE (default: false)
        - HEALING_MAX_DAILY_COST (default: 10.0)
        - HEALING_MAX_VALIDATIONS_PER_DAY (default: 100)
        - HEALING_KILL_SWITCH (default: false)
        - HEALING_PROTECTED_PATHS (comma-separated, default: src/auth/**,migrations/**,*.env*)
        - HEALING_BUILD_TIMEOUT (default: 300)
        - HEALING_TEST_TIMEOUT (default: 600)
        - HEALING_LINT_TIMEOUT (default: 60)
        - HEALING_JUDGE_TIMEOUT (default: 30)

        Returns:
            HealingConfig: Configuration loaded from environment.
        """

        def parse_bool(value: str, default: bool) -> bool:
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes")

        def parse_float(value: str, default: float) -> float:
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                return default

        def parse_int(value: str, default: int) -> int:
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default

        def parse_list(value: str, default: List[str]) -> List[str]:
            if value is None:
                return default
            return [p.strip() for p in value.split(",") if p.strip()]

        return cls(
            enabled=parse_bool(os.environ.get("HEALING_ENABLED"), True),
            auto_apply_safe=parse_bool(os.environ.get("HEALING_AUTO_APPLY_SAFE"), True),
            auto_apply_moderate=parse_bool(
                os.environ.get("HEALING_AUTO_APPLY_MODERATE"), False
            ),
            max_daily_cost_usd=parse_float(
                os.environ.get("HEALING_MAX_DAILY_COST"), 10.0
            ),
            max_validations_per_day=parse_int(
                os.environ.get("HEALING_MAX_VALIDATIONS_PER_DAY"), 100
            ),
            max_cost_per_validation_usd=parse_float(
                os.environ.get("HEALING_MAX_COST_PER_VALIDATION"), 0.50
            ),
            protected_paths=parse_list(
                os.environ.get("HEALING_PROTECTED_PATHS"),
                ["src/auth/**", "migrations/**", "*.env*"],
            ),
            kill_switch_active=parse_bool(
                os.environ.get("HEALING_KILL_SWITCH"), False
            ),
            build_timeout_seconds=parse_int(
                os.environ.get("HEALING_BUILD_TIMEOUT"), 300
            ),
            test_timeout_seconds=parse_int(
                os.environ.get("HEALING_TEST_TIMEOUT"), 600
            ),
            lint_timeout_seconds=parse_int(
                os.environ.get("HEALING_LINT_TIMEOUT"), 60
            ),
            judge_timeout_seconds=parse_int(
                os.environ.get("HEALING_JUDGE_TIMEOUT"), 30
            ),
        )


# Global config - initialized on first access
_CONFIG: HealingConfig = None


def get_config() -> HealingConfig:
    """Get the global configuration, initializing if needed.

    Returns:
        HealingConfig: The global configuration instance.
    """
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = HealingConfig.from_environment()
    return _CONFIG


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _CONFIG
    _CONFIG = None

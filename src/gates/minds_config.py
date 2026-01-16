"""
Minds Configuration - Load minds proxy settings from workflow.yaml.

Issue #39: Configuration for multi-model consensus gate proxy.

Configuration example in workflow.yaml:
```yaml
settings:
  supervision:
    mode: zero_human  # supervised | hybrid | zero_human

    minds_proxy:
      enabled: true
      models:
        - openai/gpt-5.2-codex-max
        - google/gemini-3-pro
        - anthropic/claude-3-opus
        - xai/grok-4.1
        - deepseek/deepseek-chat

      model_weights:
        openai/gpt-5.2-codex-max: 2.0
        deepseek/deepseek-chat: 0.5

      approval_threshold: 0.6

      re_deliberation:
        enabled: true
        max_rounds: 1

      escalation:
        auto_proceed_certainty: 0.95
        escalate_below_certainty: 0.60

    rollback:
      auto_checkpoint: true
```
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


# Default models and weights (defined outside class for easy access)
DEFAULT_MODELS = [
    "openai/gpt-4-turbo",
    "google/gemini-2.5-flash",
    "anthropic/claude-3.5-sonnet",
    "xai/grok-3",
    "deepseek/deepseek-chat",
]

DEFAULT_MODEL_WEIGHTS = {
    "openai/gpt-5.2-codex-max": 2.0,
    "openai/gpt-4-turbo": 1.8,
    "anthropic/claude-3-opus": 2.0,
    "anthropic/claude-3.5-sonnet": 1.8,
    "google/gemini-3-pro": 1.5,
    "google/gemini-2.5-flash": 1.2,
    "xai/grok-4.1": 1.0,
    "deepseek/deepseek-chat": 0.5,
}


@dataclass
class MindsConfig:
    """
    Configuration for minds gate proxy.

    All fields have sensible defaults for zero-config usage.
    """
    # General settings
    enabled: bool = True
    mode: str = "hybrid"  # supervised | hybrid | zero_human

    # Model configuration
    models: list[str] = field(default_factory=lambda: DEFAULT_MODELS.copy())
    model_weights: dict[str, float] = field(default_factory=lambda: DEFAULT_MODEL_WEIGHTS.copy())

    # Voting thresholds
    approval_threshold: float = 0.6  # Supermajority (per user preference)

    # Re-deliberation settings
    re_deliberation_enabled: bool = True
    re_deliberation_max_rounds: int = 1

    # Escalation thresholds (certainty-based per user preference)
    auto_proceed_certainty: float = 0.95  # Proceed even on CRITICAL
    escalate_below_certainty: float = 0.60  # Always escalate if below

    # Rollback settings
    auto_checkpoint: bool = True


def load_minds_config(
    workflow_path: Optional[Path] = None,
    settings: Optional[dict] = None,
) -> MindsConfig:
    """
    Load minds configuration from workflow.yaml or dict.

    Args:
        workflow_path: Path to workflow.yaml (searches if None)
        settings: Pre-loaded settings dict (takes priority)

    Returns:
        MindsConfig with loaded or default values
    """
    if settings is None:
        settings = _load_workflow_settings(workflow_path)

    supervision = settings.get("supervision", {})
    minds_proxy = supervision.get("minds_proxy", {})
    re_delib = minds_proxy.get("re_deliberation", {})
    escalation = minds_proxy.get("escalation", {})
    rollback = supervision.get("rollback", {})

    return MindsConfig(
        enabled=minds_proxy.get("enabled", True),
        mode=supervision.get("mode", "hybrid"),
        models=minds_proxy.get("models", DEFAULT_MODELS.copy()),
        model_weights=minds_proxy.get("model_weights", DEFAULT_MODEL_WEIGHTS.copy()),
        approval_threshold=minds_proxy.get("approval_threshold", 0.6),
        re_deliberation_enabled=re_delib.get("enabled", True),
        re_deliberation_max_rounds=re_delib.get("max_rounds", 1),
        auto_proceed_certainty=escalation.get("auto_proceed_certainty", 0.95),
        escalate_below_certainty=escalation.get("escalate_below_certainty", 0.60),
        auto_checkpoint=rollback.get("auto_checkpoint", True),
    )


def _load_workflow_settings(workflow_path: Optional[Path] = None) -> dict:
    """
    Load settings from workflow.yaml.

    Searches for workflow.yaml in current directory and parents.

    Args:
        workflow_path: Optional explicit path to workflow.yaml

    Returns:
        Settings dict or empty dict if not found
    """
    if workflow_path and workflow_path.exists():
        try:
            with open(workflow_path) as f:
                workflow = yaml.safe_load(f)
                return workflow.get("settings", {})
        except Exception as e:
            logger.warning(f"Failed to load {workflow_path}: {e}")
            return {}

    # Search for workflow.yaml
    cwd = Path.cwd()
    search_paths = [cwd] + list(cwd.parents)[:5]

    for search_dir in search_paths:
        workflow_path = search_dir / "workflow.yaml"
        if workflow_path.exists():
            try:
                with open(workflow_path) as f:
                    workflow = yaml.safe_load(f)
                    return workflow.get("settings", {})
            except Exception as e:
                logger.warning(f"Failed to load {workflow_path}: {e}")
                break

    # Not found - return empty (will use defaults)
    return {}

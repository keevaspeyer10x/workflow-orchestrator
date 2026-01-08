"""
Model Registry for dynamic model capability detection (CORE-017, CORE-018).

This module provides:
- Automatic model list updates from OpenRouter API
- Staleness detection (30-day threshold)
- Dynamic function calling capability detection
- Caching of model information

Usage:
    from src.model_registry import get_model_registry

    registry = get_model_registry()
    if registry.is_stale():
        registry.update()

    supports_tools = registry.supports_function_calling("openai/gpt-4")
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

# Configuration
REGISTRY_FILE = ".model_registry.json"
STALENESS_DAYS = 30
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
API_TIMEOUT = 30

# Static fallback list for models known to support function calling
# Used when API is unavailable or model not in registry
STATIC_FUNCTION_CALLING_MODELS = {
    # OpenAI models
    "openai/gpt-4",
    "openai/gpt-4-turbo",
    "openai/gpt-4-turbo-preview",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "openai/gpt-5",
    "openai/gpt-5.1",
    "openai/gpt-5.1-codex",
    "openai/gpt-5.1-codex-max",
    "openai/codex",
    # Anthropic models
    "anthropic/claude-3-opus",
    "anthropic/claude-3-sonnet",
    "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-sonnet-4",
    "anthropic/claude-opus-4",
    # Google models
    "google/gemini-pro",
    "google/gemini-pro-1.5",
    "google/gemini-2.0-flash",
    "google/gemini-2.5-pro",
    "google/gemini-3-pro",
    "google/gemini-3-pro-preview",
    # xAI Grok models (OpenRouter format)
    "x-ai/grok-4.1-fast",
    "x-ai/grok-4-fast",
    "x-ai/grok-4",
    "x-ai/grok-3",
    "x-ai/grok-code-fast-1",
}


class ModelRegistry:
    """
    Registry for model information with automatic update capability.

    Stores model metadata including function calling support, context length,
    and other capabilities. Automatically detects staleness and supports
    updates from OpenRouter API.
    """

    def __init__(self, working_dir: Optional[Path] = None):
        """
        Initialize the model registry.

        Args:
            working_dir: Directory for storing the registry file.
                        Defaults to current working directory.
        """
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()
        self._registry_path = self._working_dir / REGISTRY_FILE
        self._data: Dict[str, Any] = {
            "last_updated": None,
            "models": {},
        }
        self._load()

    def _load(self) -> None:
        """Load registry from disk, creating if necessary."""
        if self._registry_path.exists():
            try:
                with open(self._registry_path, "r") as f:
                    self._data = json.load(f)
                logger.debug(f"Loaded model registry from {self._registry_path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load registry: {e}")
                self._data = {"last_updated": None, "models": {}}
        else:
            # Create empty registry
            self._save()

    def _save(self) -> None:
        """Save registry to disk."""
        try:
            self._registry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._registry_path, "w") as f:
                json.dump(self._data, f, indent=2)
            logger.debug(f"Saved model registry to {self._registry_path}")
        except IOError as e:
            logger.error(f"Failed to save registry: {e}")

    @property
    def models(self) -> Dict[str, Any]:
        """Get the models dictionary."""
        return self._data.get("models", {})

    @property
    def last_updated(self) -> Optional[datetime]:
        """Get the last update timestamp."""
        ts = self._data.get("last_updated")
        if ts:
            try:
                return datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                return None
        return None

    def is_stale(self) -> bool:
        """
        Check if the registry is stale (> STALENESS_DAYS since last update).

        Returns:
            True if registry should be updated, False otherwise.
        """
        last = self.last_updated
        if last is None:
            return True

        age = datetime.now() - last
        # Use > (not >=) so exactly STALENESS_DAYS is not stale
        return age.days > STALENESS_DAYS

    def fetch_latest_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch latest model list from OpenRouter API.

        Returns:
            List of model dictionaries, or None on failure.
        """
        if requests is None:
            logger.warning("requests library not available")
            return None

        try:
            response = requests.get(
                OPENROUTER_MODELS_URL,
                timeout=API_TIMEOUT,
                headers={"User-Agent": "workflow-orchestrator"}
            )

            if response.status_code == 429:
                logger.warning("OpenRouter API rate limited")
                return None

            if response.status_code != 200:
                logger.warning(f"OpenRouter API error: {response.status_code}")
                return None

            data = response.json()
            return data.get("data", [])

        except requests.exceptions.Timeout:
            logger.warning("OpenRouter API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"OpenRouter API request failed: {e}")
            return None
        except json.JSONDecodeError:
            logger.warning("Failed to parse OpenRouter API response")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error fetching models: {e}")
            return None

    def update(self, force: bool = False) -> bool:
        """
        Update the registry from OpenRouter API.

        Args:
            force: Update even if not stale.

        Returns:
            True if update was successful, False otherwise.
        """
        if not force and not self.is_stale():
            logger.debug("Registry not stale, skipping update")
            return True

        models_list = self.fetch_latest_models()
        if models_list is None:
            logger.warning("Failed to fetch models, keeping existing data")
            return False

        # Process and store models
        models_dict = {}
        for model in models_list:
            model_id = model.get("id")
            if not model_id:
                continue

            models_dict[model_id] = {
                "supports_tools": model.get("supports_tools", False),
                "context_length": model.get("context_length", 0),
                "supports_vision": model.get("supports_vision", False),
                "description": model.get("description", ""),
                "pricing": model.get("pricing", {}),
            }

        self._data["models"] = models_dict
        self._data["last_updated"] = datetime.now().isoformat()
        self._save()

        logger.info(f"Updated model registry with {len(models_dict)} models")
        return True

    def get_model_capabilities(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get capabilities for a specific model.

        First checks the local cache, then fetches from API if not found.

        Args:
            model_id: The model identifier (e.g., "openai/gpt-4").

        Returns:
            Dictionary of model capabilities, or None if not found.
        """
        # Check cache first
        if model_id in self.models:
            return self.models[model_id]

        # Try to fetch from API
        if requests is None:
            return None

        try:
            # Note: OpenRouter doesn't have a single-model endpoint,
            # so we'd need to fetch the full list. For efficiency,
            # just return None and use static fallback.
            logger.debug(f"Model {model_id} not in cache, using static fallback")
            return None

        except Exception as e:
            logger.debug(f"Failed to fetch capabilities for {model_id}: {e}")
            return None

    def supports_function_calling(self, model_id: str) -> bool:
        """
        Check if a model supports function calling.

        Uses the following priority:
        1. Cached registry data
        2. Static fallback list
        3. Conservative default (False)

        Args:
            model_id: The model identifier.

        Returns:
            True if model supports function calling, False otherwise.
        """
        # Check cached registry
        if model_id in self.models:
            return self.models[model_id].get("supports_tools", False)

        # Check static fallback list (exact match)
        if model_id in STATIC_FUNCTION_CALLING_MODELS:
            return True

        # Check static fallback list (prefix match for versioned models)
        for known_model in STATIC_FUNCTION_CALLING_MODELS:
            if model_id.startswith(known_model):
                return True

        # Conservative default
        return False

    def get_recommended_model(self, category: str = "general") -> Optional[str]:
        """
        Get the recommended model for a category.

        Args:
            category: One of "general", "code", "long_context".

        Returns:
            Model ID string, or None if no recommendation.
        """
        # Default recommendations
        defaults = {
            "general": "anthropic/claude-sonnet-4",
            "code": "openai/gpt-5.1-codex",
            "long_context": "google/gemini-2.5-pro",
        }

        if category in defaults:
            model_id = defaults[category]
            # Verify it's available in registry or static list
            if model_id in self.models or model_id in STATIC_FUNCTION_CALLING_MODELS:
                return model_id

        return defaults.get("general")

    def get_latest_model(self, category: str) -> str:
        """
        Get the latest available model for a category (WF-003).

        Categories map to model families used for different review types:
        - "codex": Code-specialized models (OpenAI Codex family) for security/quality reviews
        - "gemini": Long-context models (Google Gemini) for consistency/holistic reviews
        - "claude": General-purpose models (Anthropic Claude) for general tasks
        - "security": Alias for codex
        - "quality": Alias for codex
        - "consistency": Alias for gemini
        - "holistic": Alias for gemini

        Principle: Use the latest generation model available, don't hardcode versions.

        Args:
            category: Model category or review type

        Returns:
            Model ID string (e.g., "openai/gpt-5.1-codex-max")
        """
        # Map review types to model families
        category_mapping = {
            "security": "codex",
            "quality": "codex",
            "consistency": "gemini",
            "holistic": "gemini",
            "vibe_coding": "grok",
            "vibe": "grok",
        }
        resolved_category = category_mapping.get(category.lower(), category.lower())

        # Latest models by category (update these as new models are released)
        # NOTE: Keep these updated! Check provider docs for latest versions.
        latest_models = {
            "codex": [
                "openai/gpt-5.1-codex-max",
                "openai/gpt-5.1-codex",
                "openai/gpt-5.1",
                "openai/gpt-4.1",
                "openai/gpt-4o",
            ],
            "gemini": [
                "google/gemini-3-pro-preview",
                "google/gemini-3-pro",
                "google/gemini-2.5-pro",
                "google/gemini-2.0-flash",
                "google/gemini-pro-1.5",
            ],
            "claude": [
                "anthropic/claude-opus-4",
                "anthropic/claude-sonnet-4",
                "anthropic/claude-3.5-sonnet",
                "anthropic/claude-3-opus",
            ],
            "grok": [
                "x-ai/grok-4.1-fast",  # Latest as of Jan 2026
                "x-ai/grok-4-fast",
                "x-ai/grok-4",
                "x-ai/grok-3",
            ],
        }

        # Default fallbacks
        fallbacks = {
            "codex": "openai/gpt-4o",
            "gemini": "google/gemini-pro-1.5",
            "claude": "anthropic/claude-sonnet-4",
            "grok": "x-ai/grok-4.1-fast",
        }

        candidates = latest_models.get(resolved_category, [])

        # Check registry for available models
        for model_id in candidates:
            if model_id in self.models:
                logger.debug(f"Found {model_id} in registry for category {category}")
                return model_id

        # Check static list
        for model_id in candidates:
            if model_id in STATIC_FUNCTION_CALLING_MODELS:
                logger.debug(f"Using static fallback {model_id} for category {category}")
                return model_id

        # Last resort fallback
        fallback = fallbacks.get(resolved_category, "anthropic/claude-sonnet-4")
        logger.debug(f"Using default fallback {fallback} for category {category}")
        return fallback


# Module-level singleton
_default_registry: Optional[ModelRegistry] = None


def get_model_registry(working_dir: Optional[Path] = None) -> ModelRegistry:
    """
    Get a ModelRegistry instance.

    Creates a singleton instance if working_dir not specified.

    Args:
        working_dir: Optional working directory for registry file.

    Returns:
        ModelRegistry instance.
    """
    global _default_registry

    if working_dir is not None:
        return ModelRegistry(working_dir=working_dir)

    if _default_registry is None:
        _default_registry = ModelRegistry()

    return _default_registry


def is_registry_stale(working_dir: Optional[Path] = None) -> bool:
    """
    Check if the model registry is stale.

    Args:
        working_dir: Optional working directory.

    Returns:
        True if registry needs updating.
    """
    return get_model_registry(working_dir).is_stale()


def get_latest_models(working_dir: Optional[Path] = None) -> Optional[List[Dict]]:
    """
    Fetch latest models from OpenRouter API.

    Args:
        working_dir: Optional working directory.

    Returns:
        List of model dictionaries, or None on failure.
    """
    return get_model_registry(working_dir).fetch_latest_models()


def get_model_capabilities(
    model_id: str,
    working_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Get capabilities for a model.

    Args:
        model_id: The model identifier.
        working_dir: Optional working directory.

    Returns:
        Capabilities dictionary, or None if not found.
    """
    return get_model_registry(working_dir).get_model_capabilities(model_id)


def supports_function_calling(
    model_id: str,
    working_dir: Optional[Path] = None
) -> bool:
    """
    Check if a model supports function calling.

    Args:
        model_id: The model identifier.
        working_dir: Optional working directory.

    Returns:
        True if model supports function calling.
    """
    return get_model_registry(working_dir).supports_function_calling(model_id)


def update_registry(
    working_dir: Optional[Path] = None,
    force: bool = False
) -> bool:
    """
    Update the model registry.

    Args:
        working_dir: Optional working directory.
        force: Update even if not stale.

    Returns:
        True if update successful.
    """
    return get_model_registry(working_dir).update(force=force)


def get_latest_model(
    category: str,
    working_dir: Optional[Path] = None
) -> str:
    """
    Get the latest available model for a category (WF-003).

    Categories:
    - "codex" / "security" / "quality": Code-specialized models
    - "gemini" / "consistency" / "holistic": Long-context models
    - "claude": General-purpose models

    Args:
        category: Model category or review type
        working_dir: Optional working directory

    Returns:
        Model ID string
    """
    return get_model_registry(working_dir).get_latest_model(category)

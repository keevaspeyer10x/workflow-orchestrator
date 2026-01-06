"""
Provider registry for agent execution.

This module provides the central registry for all agent providers,
including auto-detection logic for selecting the best available provider.
"""

import os
import logging
from typing import Optional, List, Type

from .base import AgentProvider, ExecutionResult
from .openrouter import OpenRouterProvider
from .claude_code import ClaudeCodeProvider
from .manual import ManualProvider

# Import environment detection (optional, for auto-selection)
try:
    from ..environment import detect_environment, Environment, get_recommended_provider
    _HAS_ENVIRONMENT = True
except ImportError:
    _HAS_ENVIRONMENT = False


logger = logging.getLogger(__name__)


# Registry of available providers
_PROVIDERS: dict[str, Type[AgentProvider]] = {
    "openrouter": OpenRouterProvider,
    "claude_code": ClaudeCodeProvider,
    "manual": ManualProvider,
}


def list_providers() -> List[str]:
    """
    List all registered provider names.
    
    Returns:
        List[str]: List of provider names
    """
    return list(_PROVIDERS.keys())


def get_provider(
    name: Optional[str] = None,
    environment: Optional[str] = None,
    **kwargs
) -> AgentProvider:
    """
    Get a provider instance by name or auto-detect the best available.
    
    Auto-detection priority:
    1. Explicit name parameter
    2. Environment-based selection (if environment provided)
    3. API key presence (OPENROUTER_API_KEY → openrouter)
    4. Claude Code CLI availability
    5. Fallback to manual
    
    Args:
        name: Explicit provider name to use
        environment: Environment hint ('claude_code', 'manus', 'standalone')
        **kwargs: Additional arguments passed to provider constructor
    
    Returns:
        AgentProvider: An initialized provider instance
    
    Raises:
        ValueError: If specified provider name is not found
    """
    # If explicit name provided, use it
    if name:
        if name not in _PROVIDERS:
            available = ", ".join(list_providers())
            raise ValueError(f"Unknown provider '{name}'. Available: {available}")
        
        provider_class = _PROVIDERS[name]
        filtered_kwargs = _filter_kwargs_for_provider(name, kwargs)
        provider = provider_class(**filtered_kwargs)
        
        if not provider.is_available():
            logger.warning(f"Requested provider '{name}' is not available, using anyway")
        
        return provider
    
    # Auto-detect based on environment
    if environment:
        provider = _get_provider_for_environment(environment, **kwargs)
        if provider and provider.is_available():
            logger.info(f"Selected provider '{provider.name()}' based on environment '{environment}'")
            return provider
    
    # Auto-detect based on available resources
    return _auto_detect_provider(**kwargs)


def _filter_kwargs_for_provider(name: str, kwargs: dict) -> dict:
    """
    Filter kwargs to only include those accepted by the provider.
    
    Args:
        name: Provider name
        kwargs: All kwargs passed to get_provider
    
    Returns:
        dict: Filtered kwargs for the specific provider
    """
    # Define accepted kwargs for each provider
    accepted_kwargs = {
        'openrouter': {'api_key', 'model', 'timeout'},
        'claude_code': {'working_dir', 'timeout'},
        'manual': set(),  # Manual accepts no kwargs
    }
    
    accepted = accepted_kwargs.get(name, set())
    return {k: v for k, v in kwargs.items() if k in accepted}


def _get_provider_for_environment(environment: str, **kwargs) -> Optional[AgentProvider]:
    """
    Get the preferred provider for a given environment.
    
    Args:
        environment: Environment name (or Environment enum)
        **kwargs: Additional arguments for provider
    
    Returns:
        Optional[AgentProvider]: Provider for the environment, or None
    """
    # Handle both string and Environment enum
    if _HAS_ENVIRONMENT and isinstance(environment, Environment):
        env_lower = environment.value
    else:
        env_lower = str(environment).lower()
    
    # Extract provider-specific kwargs
    working_dir = kwargs.pop('working_dir', None)
    
    if env_lower == "claude_code":
        claude_kwargs = {'working_dir': working_dir} if working_dir else {}
        return ClaudeCodeProvider(**claude_kwargs)
    elif env_lower == "manus":
        # In Manus, prefer OpenRouter if available, otherwise manual
        if os.environ.get("OPENROUTER_API_KEY"):
            return OpenRouterProvider(**kwargs)
        return ManualProvider()
    elif env_lower == "standalone":
        # In standalone, prefer OpenRouter if available
        if os.environ.get("OPENROUTER_API_KEY"):
            return OpenRouterProvider(**kwargs)
        return ManualProvider()
    
    return None


def _auto_detect_provider(**kwargs) -> AgentProvider:
    """
    Auto-detect the best available provider.
    
    Priority:
    1. Environment-based recommendation (if environment module available)
    2. OpenRouter (if API key present)
    3. Claude Code (if CLI available)
    4. Manual (always available)
    
    Args:
        **kwargs: Additional arguments for provider
    
    Returns:
        AgentProvider: The best available provider
    """
    # Extract provider-specific kwargs
    working_dir = kwargs.pop('working_dir', None)
    
    # Try environment-based detection first
    if _HAS_ENVIRONMENT:
        try:
            env = detect_environment()
            recommended = get_recommended_provider(env)
            provider = _get_provider_for_environment(env, working_dir=working_dir, **kwargs)
            if provider and provider.is_available():
                logger.info(f"Auto-selected {provider.name()} provider (environment: {env.value})")
                return provider
        except Exception as e:
            logger.warning(f"Environment detection failed: {e}")
    
    # Try OpenRouter (most flexible)
    if os.environ.get("OPENROUTER_API_KEY"):
        provider = OpenRouterProvider(**kwargs)
        if provider.is_available():
            logger.info("Auto-selected OpenRouter provider (API key found)")
            return provider
    
    # Try Claude Code
    claude_kwargs = {'working_dir': working_dir} if working_dir else {}
    provider = ClaudeCodeProvider(**claude_kwargs)
    if provider.is_available():
        logger.info("Auto-selected Claude Code provider (CLI available)")
        return provider
    
    # Fallback to manual
    logger.info("Auto-selected Manual provider (fallback)")
    return ManualProvider()


def register_provider(name: str, provider_class: Type[AgentProvider]) -> None:
    """
    Register a new provider class.
    
    Args:
        name: Provider name for registry
        provider_class: Provider class (must inherit from AgentProvider)
    """
    if not issubclass(provider_class, AgentProvider):
        raise TypeError(f"Provider class must inherit from AgentProvider")
    
    _PROVIDERS[name] = provider_class
    logger.info(f"Registered provider: {name}")


# Export public API
__all__ = [
    "AgentProvider",
    "ExecutionResult",
    "OpenRouterProvider",
    "ClaudeCodeProvider",
    "ManualProvider",
    "get_provider",
    "list_providers",
    "register_provider",
]

"""
Environment Detection Module

This module provides detection of the execution environment (Claude Code, Manus, Standalone)
to enable automatic provider selection and environment-specific behavior.
"""

import os
import subprocess
import logging
from enum import Enum
from typing import Optional
from pathlib import Path


logger = logging.getLogger(__name__)


class Environment(Enum):
    """Detected execution environment."""
    CLAUDE_CODE = "claude_code"
    MANUS = "manus"
    STANDALONE = "standalone"


def detect_environment() -> Environment:
    """
    Detect the current execution environment.
    
    Detection priority:
    1. Claude Code - CLAUDE_CODE env var, parent process, or .claude directory
    2. Manus - MANUS_SESSION env var or /home/ubuntu home directory
    3. Standalone - Default fallback
    
    Returns:
        Environment: The detected environment
    """
    # Check for Claude Code
    if _is_claude_code_environment():
        logger.info("Detected Claude Code environment")
        return Environment.CLAUDE_CODE
    
    # Check for Manus
    if _is_manus_environment():
        logger.info("Detected Manus environment")
        return Environment.MANUS
    
    # Default to standalone
    logger.info("Detected Standalone environment")
    return Environment.STANDALONE


def _is_claude_code_environment() -> bool:
    """
    Check if running in Claude Code environment.
    
    Detection methods:
    1. CLAUDE_CODE environment variable is set
    2. Parent process is 'claude'
    3. .claude directory exists in home or current directory
    """
    # Check environment variable
    if os.environ.get("CLAUDE_CODE"):
        return True
    
    # Check for .claude directory
    home = Path.home()
    if (home / ".claude").exists():
        return True
    
    if Path(".claude").exists():
        return True
    
    # Check parent process name
    try:
        ppid = os.getppid()
        result = subprocess.run(
            ["ps", "-p", str(ppid), "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            parent_name = result.stdout.strip().lower()
            if "claude" in parent_name:
                return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    
    return False


def _is_manus_environment() -> bool:
    """
    Check if running in Manus environment.
    
    Detection methods:
    1. MANUS_SESSION environment variable is set
    2. Home directory is /home/ubuntu (typical Manus sandbox)
    3. Running in a sandbox-like environment
    """
    # Check environment variable
    if os.environ.get("MANUS_SESSION"):
        return True
    
    # Check home directory pattern
    home = str(Path.home())
    if home == "/home/ubuntu":
        # Additional check: verify it's a sandbox-like environment
        # by checking for typical Manus sandbox indicators
        if _has_manus_indicators():
            return True
    
    return False


def _has_manus_indicators() -> bool:
    """
    Check for additional indicators of Manus environment.
    """
    indicators = [
        # Manus typically has these paths/files
        Path("/home/ubuntu/.manus"),
        Path("/home/ubuntu/Downloads"),
    ]
    
    # If any indicator exists, likely Manus
    for indicator in indicators:
        if indicator.exists():
            return True
    
    # Check if we're in a container-like environment
    if Path("/.dockerenv").exists():
        return True
    
    # Check for sandbox-specific environment variables
    sandbox_vars = ["SANDBOX_ID", "MANUS_TASK_ID"]
    for var in sandbox_vars:
        if os.environ.get(var):
            return True
    
    return False


def get_environment_info() -> dict:
    """
    Get detailed information about the current environment.
    
    Returns:
        dict: Environment information including:
            - environment: The detected environment name
            - home: Home directory path
            - user: Current user
            - indicators: List of detected indicators
    """
    env = detect_environment()
    
    indicators = []
    
    # Collect indicators
    if os.environ.get("CLAUDE_CODE"):
        indicators.append("CLAUDE_CODE env var")
    if os.environ.get("MANUS_SESSION"):
        indicators.append("MANUS_SESSION env var")
    if Path.home() == Path("/home/ubuntu"):
        indicators.append("ubuntu home directory")
    if Path(".claude").exists() or (Path.home() / ".claude").exists():
        indicators.append(".claude directory")
    if Path("/.dockerenv").exists():
        indicators.append("Docker container")
    
    return {
        "environment": env.value,
        "home": str(Path.home()),
        "user": os.environ.get("USER", "unknown"),
        "cwd": str(Path.cwd()),
        "indicators": indicators,
    }


def get_recommended_provider(environment: Optional[Environment] = None) -> str:
    """
    Get the recommended provider for the given environment.

    Args:
        environment: Environment to get recommendation for (auto-detects if None)

    Returns:
        str: Recommended provider name
    """
    if environment is None:
        environment = detect_environment()

    recommendations = {
        Environment.CLAUDE_CODE: "claude_code",
        Environment.MANUS: "openrouter",  # Manus has OpenRouter available
        Environment.STANDALONE: "manual",  # Safest default for unknown environments
    }

    return recommendations.get(environment, "manual")


def detect_manus_connector() -> bool:
    """
    Detect if Manus direct connector is available.

    Checks for:
    1. MANUS_API_URL environment variable
    2. MANUS_SESSION environment variable
    3. Other Manus-specific indicators

    Returns:
        True if Manus connector appears available, False otherwise.
    """
    # Check for explicit API URL
    if os.environ.get("MANUS_API_URL"):
        logger.debug("Manus connector detected via MANUS_API_URL")
        return True

    # Check for session indicator
    if os.environ.get("MANUS_SESSION"):
        logger.debug("Manus connector detected via MANUS_SESSION")
        return True

    # Check for Manus task ID
    if os.environ.get("MANUS_TASK_ID"):
        logger.debug("Manus connector detected via MANUS_TASK_ID")
        return True

    # Check if in Manus environment with connector available
    if _is_manus_environment():
        # Additional check for connector availability
        manus_connector_path = Path("/home/ubuntu/.manus/connector")
        if manus_connector_path.exists():
            logger.debug("Manus connector detected via connector path")
            return True

    return False


def get_available_connectors() -> list:
    """
    Get list of all available connectors/providers.

    Returns:
        List of connector names that are currently available.
    """
    available = []

    # Check Claude Code CLI
    try:
        import shutil
        if shutil.which("claude"):
            available.append("claude_code")
    except Exception:
        pass

    # Check Manus connector
    if detect_manus_connector():
        available.append("manus_direct")

    # Check OpenRouter
    if os.environ.get("OPENROUTER_API_KEY"):
        available.append("openrouter")

    # Manual is always available
    available.append("manual")

    return available

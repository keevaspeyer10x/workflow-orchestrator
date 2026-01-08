"""
Configuration discovery for workflow-orchestrator.

Handles finding workflow.yaml files with fallback to bundled default.
"""

from pathlib import Path
from typing import Optional
import importlib.resources


def get_bundled_workflow_path() -> Path:
    """
    Get the path to the bundled default workflow.yaml.

    Returns:
        Path to the default_workflow.yaml bundled with the package.

    Raises:
        FileNotFoundError: If the bundled workflow is missing (corrupted install).
    """
    # Try importlib.resources first (Python 3.9+)
    try:
        if hasattr(importlib.resources, 'files'):
            # Python 3.9+
            pkg_path = importlib.resources.files('src')
            workflow_path = pkg_path / 'default_workflow.yaml'
            # Convert to actual path
            if hasattr(workflow_path, '_path'):
                return Path(workflow_path._path)
            # For traversable resources
            with importlib.resources.as_file(workflow_path) as path:
                return path
    except (TypeError, AttributeError):
        pass

    # Fallback: look relative to this file
    src_dir = Path(__file__).parent
    bundled_path = src_dir / 'default_workflow.yaml'

    if bundled_path.exists():
        return bundled_path

    raise FileNotFoundError(
        "Bundled default_workflow.yaml not found. "
        "This may indicate a corrupted installation. "
        "Try reinstalling: pip install --force-reinstall workflow-orchestrator"
    )


def find_workflow_path(working_dir: Optional[Path] = None) -> Path:
    """
    Find the workflow.yaml to use, checking local first, then falling back to bundled.

    Args:
        working_dir: Directory to check for local workflow.yaml. Defaults to cwd.

    Returns:
        Path to the workflow.yaml file to use.
    """
    if working_dir is None:
        working_dir = Path.cwd()
    else:
        working_dir = Path(working_dir)

    # Check for local workflow.yaml
    local_workflow = working_dir / 'workflow.yaml'
    if local_workflow.exists():
        return local_workflow

    # Fall back to bundled default
    return get_bundled_workflow_path()


def get_default_workflow_content() -> str:
    """
    Get the content of the bundled default workflow.

    Returns:
        The YAML content of the default workflow as a string.
    """
    bundled_path = get_bundled_workflow_path()
    return bundled_path.read_text()


def is_using_bundled_workflow(working_dir: Optional[Path] = None) -> bool:
    """
    Check if the current workflow is the bundled default.

    Args:
        working_dir: Directory to check for local workflow.yaml.

    Returns:
        True if using bundled workflow, False if using local.
    """
    if working_dir is None:
        working_dir = Path.cwd()
    else:
        working_dir = Path(working_dir)

    local_workflow = working_dir / 'workflow.yaml'
    return not local_workflow.exists()

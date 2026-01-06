# Claude Code Prompt: Implement Global Installation (Method C)

## Task Overview

Convert the workflow-orchestrator from a repo-based tool to a globally installable Python package that can be used in any project directory.

## Repository

```bash
git clone https://github.com/keevaspeyer10x/workflow-orchestrator.git
cd workflow-orchestrator
```

## Current State

- CLI entry point: `./orchestrator` (bash script calling `python3 src/cli.py`)
- Workflow definition: `workflow.yaml` in repo root
- State files: `.workflow_state.json`, `.workflow_log.jsonl` in working directory
- Dependencies: `requirements.txt` (pydantic, pyyaml, requests)

## Desired End State

```bash
# Install globally
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git

# Use in ANY directory
cd ~/any-project
orchestrator status          # Works immediately with built-in workflow
orchestrator start "My task"
orchestrator handoff --execute
```

## Requirements

### 1. Package Structure

Convert to proper Python package:

```
workflow-orchestrator/
├── pyproject.toml           # Modern Python packaging (preferred over setup.py)
├── README.md
├── LICENSE
├── src/
│   └── orchestrator/        # Rename from src/ to src/orchestrator/
│       ├── __init__.py      # Package init with version
│       ├── __main__.py      # Allow `python -m orchestrator`
│       ├── cli.py           # Main CLI (update imports)
│       ├── engine.py
│       ├── schema.py
│       ├── environment.py
│       ├── checkpoint.py
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── openrouter.py
│       │   ├── claude_code.py
│       │   └── manual.py
│       ├── data/            # NEW: bundled data files
│       │   └── default_workflow.yaml  # Copy of workflow.yaml
│       └── ...
├── tests/
└── workflow.yaml            # Keep for repo development
```

### 2. pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "workflow-orchestrator"
version = "2.2.0"
description = "A 5-phase AI-assisted development workflow orchestrator"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Keeva Speyer"}
]
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "requests>=2.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.scripts]
orchestrator = "orchestrator.cli:main"

[project.urls]
Homepage = "https://github.com/keevaspeyer10x/workflow-orchestrator"
Repository = "https://github.com/keevaspeyer10x/workflow-orchestrator"

[tool.hatch.build.targets.wheel]
packages = ["src/orchestrator"]
```

### 3. Config Discovery Logic

Update `cli.py` to find workflow.yaml in this order:

```python
from pathlib import Path
import importlib.resources

def find_workflow_config() -> Path:
    """
    Find workflow.yaml in order of precedence:
    1. ./workflow.yaml (current directory - project specific)
    2. ~/.config/orchestrator/workflow.yaml (user customized)
    3. Built-in default (bundled with package)
    """
    # 1. Current directory
    local = Path.cwd() / "workflow.yaml"
    if local.exists():
        return local
    
    # 2. User config directory
    user_config = Path.home() / ".config" / "orchestrator" / "workflow.yaml"
    if user_config.exists():
        return user_config
    
    # 3. Built-in default
    # For Python 3.9+, use importlib.resources
    with importlib.resources.as_file(
        importlib.resources.files("orchestrator.data").joinpath("default_workflow.yaml")
    ) as default_path:
        return default_path

def find_state_dir() -> Path:
    """
    State files always go in current working directory.
    This keeps project state with the project.
    """
    return Path.cwd()
```

### 4. New `init` Command

Add an `init` command to copy the default workflow to current directory:

```python
def cmd_init(args):
    """Initialize orchestrator in current directory."""
    target = Path.cwd() / "workflow.yaml"
    
    if target.exists() and not args.force:
        print(f"workflow.yaml already exists. Use --force to overwrite.")
        return 1
    
    # Copy default workflow
    import shutil
    default = find_default_workflow()
    shutil.copy(default, target)
    
    print(f"Created workflow.yaml in {Path.cwd()}")
    print("You can now customize this workflow for your project.")
    return 0
```

Add to argument parser:
```python
init_parser = subparsers.add_parser("init", help="Initialize orchestrator in current directory")
init_parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing workflow.yaml")
init_parser.set_defaults(func=cmd_init)
```

### 5. Update Imports

All internal imports need to change from relative to package imports:

```python
# Before (in cli.py)
from src.engine import WorkflowEngine
from src.schema import WorkflowDef

# After
from orchestrator.engine import WorkflowEngine
from orchestrator.schema import WorkflowDef
```

### 6. __main__.py

Create `src/orchestrator/__main__.py`:

```python
"""Allow running as `python -m orchestrator`."""
from orchestrator.cli import main

if __name__ == "__main__":
    main()
```

### 7. __init__.py

Update `src/orchestrator/__init__.py`:

```python
"""Workflow Orchestrator - A 5-phase AI-assisted development workflow tool."""

__version__ = "2.2.0"

from orchestrator.engine import WorkflowEngine
from orchestrator.schema import WorkflowDef, WorkflowState

__all__ = ["WorkflowEngine", "WorkflowDef", "WorkflowState", "__version__"]
```

### 8. Bundle Default Workflow

Copy `workflow.yaml` to `src/orchestrator/data/default_workflow.yaml` and ensure it's included in the package:

In `pyproject.toml`, add:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/orchestrator"]
include = ["src/orchestrator/data/*"]
```

### 9. Backwards Compatibility

- Keep the `./orchestrator` bash script for repo development
- Ensure existing `.workflow_state.json` files still work
- Don't break any existing CLI commands

## Testing

After implementation, verify:

```bash
# 1. Install in development mode
pip install -e .

# 2. Test from repo directory (should use local workflow.yaml)
cd ~/workflow-orchestrator
orchestrator status

# 3. Test from empty directory (should use built-in default)
cd /tmp
mkdir test-project && cd test-project
orchestrator status  # Should work with default workflow

# 4. Test init command
orchestrator init
ls workflow.yaml  # Should exist

# 5. Test python -m
python -m orchestrator status

# 6. Run existing tests
pytest tests/
```

## Files to Create/Modify

| File | Action | Notes |
|------|--------|-------|
| `pyproject.toml` | CREATE | Package configuration |
| `src/orchestrator/__init__.py` | MODIFY | Add version, exports |
| `src/orchestrator/__main__.py` | CREATE | Allow `python -m` |
| `src/orchestrator/cli.py` | MODIFY | Config discovery, init command, fix imports |
| `src/orchestrator/data/default_workflow.yaml` | CREATE | Copy of workflow.yaml |
| `src/orchestrator/*.py` | MODIFY | Fix all imports |
| `tests/*.py` | MODIFY | Fix imports if needed |

## Constraints

- Do NOT change the workflow.yaml structure or content
- Do NOT change CLI command names or arguments (except adding `init`)
- Do NOT break existing functionality
- Keep Python 3.10+ compatibility
- Use modern Python packaging (pyproject.toml, not setup.py)

## Success Criteria

1. `pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git` works
2. `orchestrator` command available globally after install
3. Works in any directory with built-in default workflow
4. `orchestrator init` creates local workflow.yaml
5. All existing tests pass
6. Existing users' workflows continue to work

## Deliverables

1. All code changes committed
2. Updated README.md with new installation instructions
3. Updated docs/SETUP_GUIDE.md with pip install method
4. Brief summary of changes made

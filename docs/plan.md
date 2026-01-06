# Implementation Plan: Global Installation (Method C)

## Overview

Convert workflow-orchestrator from a repo-based tool to a globally pip-installable package. After implementation, users can install via `pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git` and run `orchestrator` from any directory.

## Target Environments
- Local Claude Code CLI
- Claude Code Web
- Manus

## Design Decisions
1. **Default workflow**: Bundle full 5-phase `workflow.yaml` (PLAN -> EXECUTE -> REVIEW -> VERIFY -> LEARN)
2. **Init conflict handling**: Prompt user, then backup to `workflow.yaml.bak` before replacing
3. **State files**: Store in current working directory (`.workflow_state.json`, `.workflow_log.jsonl`)
4. **Config discovery**: Local `workflow.yaml` > bundled default (no user config dir - keep it simple)

---

## Implementation Steps

### Phase 1: Package Structure

**1.1 Create pyproject.toml**
- Define package metadata (name: `workflow-orchestrator`)
- Specify dependencies from requirements.txt
- Define entry point: `orchestrator = "src.cli:main"`
- Include package data for bundled workflow.yaml
- Require Python >= 3.10

**1.2 Add __main__.py to src/**
- Enable `python -m src` invocation
- Call main() from cli.py

**1.3 Update src/__init__.py**
- Ensure version is defined in one place
- Export main() function

### Phase 2: Configuration Discovery

**2.1 Create src/config.py**
- `find_workflow_path()`: Check for local `workflow.yaml`, fall back to bundled
- `get_bundled_workflow_path()`: Return path to package data workflow
- `get_default_workflow_content()`: Return bundled workflow as string

**2.2 Update src/engine.py**
- Modify `load_workflow()` to use config discovery
- When no workflow specified: try local, then bundled default
- Log which workflow is being used

### Phase 3: Init Command

**3.1 Add init command to src/cli.py**
- `orchestrator init`: Copy bundled workflow to current directory
- Check if `workflow.yaml` exists
- If exists: prompt user, backup to `workflow.yaml.bak`, then replace
- If not exists: copy directly
- Print success message with next steps

### Phase 4: CLI Entry Point Refactor

**4.1 Update src/cli.py**
- Add `main()` function as entry point
- Ensure all imports work when installed as package
- Remove sys.path manipulation hack (line 15)
- Handle case where no workflow.yaml exists gracefully

**4.2 Fix relative imports**
- Review all imports in src/*.py files
- Ensure they work both as package and from repo root
- Use relative imports within the package

### Phase 5: Documentation Updates

**5.1 Update README.md**
- Add "Installation" section with pip install command
- Update "Quick Start" to reflect global usage
- Keep local development instructions

**5.2 Update CLAUDE.md**
- Update CLI examples to use `orchestrator` instead of `./orchestrator`
- Add section on global installation for AI agents
- Include the pip install command prominently

**5.3 Update docs/SETUP_GUIDE.md**
- Rewrite installation section
- Document both global install and development setup
- Add troubleshooting for common issues

**5.4 Update docs/CLAUDE_CODE_PROMPT_GLOBAL_INSTALL.md**
- Mark as implemented
- Add actual commands used

### Phase 6: Testing

**6.1 Update existing tests**
- Ensure tests still pass with new structure
- Update any path-dependent tests

**6.2 Add installation tests**
- Test `pip install -e .` works
- Test `orchestrator` command is available after install
- Test workflow discovery (local vs bundled)
- Test init command (new, overwrite, backup)

---

## File Changes Summary

### New Files
- `pyproject.toml` - Package configuration
- `src/__main__.py` - Entry point for `python -m src`
- `src/config.py` - Configuration discovery logic
- `src/default_workflow.yaml` - Bundled workflow (copy of workflow.yaml)

### Modified Files
- `src/__init__.py` - Export main(), version consistency
- `src/cli.py` - Add main(), init command, remove path hack
- `src/engine.py` - Use config discovery for workflow loading
- `README.md` - Installation docs
- `CLAUDE.md` - AI agent instructions
- `docs/SETUP_GUIDE.md` - Updated setup guide
- `docs/CLAUDE_CODE_PROMPT_GLOBAL_INSTALL.md` - Mark complete

### Deprecated (kept for backwards compat)
- `orchestrator` (bash script) - Keep working for existing users
- `requirements.txt` - Keep for reference, pyproject.toml is authoritative

---

## Success Criteria

1. `pip install git+https://...` creates globally available `orchestrator` command
2. Running `orchestrator status` in empty directory uses bundled workflow
3. Running `orchestrator status` with local `workflow.yaml` uses that file
4. `orchestrator init` creates local workflow.yaml (with backup if needed)
5. All existing tests pass
6. Works in Claude Code Web and Manus environments

---

## Execution Approach

Will implement directly in Claude Code (not handed off) since this is primarily:
- Configuration/packaging work
- Documentation updates
- Straightforward code changes

No complex logic requiring specialized implementation.

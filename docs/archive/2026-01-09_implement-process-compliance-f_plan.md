# Happy CLI Integration Plan

## Goal
Enable Claude Squad adapter to spawn sessions using Happy CLI instead of `claude`, allowing spawned instances to appear in the Happy mobile app.

## Background
- Happy (https://happy.engineering) wraps Claude Code and provides mobile app access
- Claude Squad supports custom programs via `-p` flag
- Users launching with `happy` want spawned sessions visible in the mobile app

## Cross-Repo Usage Strategy

The orchestrator is used across multiple repos. Configuration priority (highest to lowest):
1. **Environment variable**: `CLAUDE_BINARY=happy` (per-session override)
2. **Global config**: `orchestrator config set claude_binary happy` (persists in `~/.config/orchestrator/config.yaml`)
3. **SquadConfig default**: `"claude"` (backward compatible)

This means:
- Set once globally with `orchestrator config set claude_binary happy` → works in all repos
- Override per-session with `CLAUDE_BINARY=happy` if needed
- No per-repo setup required

## Changes Required

### 1. Update SquadConfig (squad_adapter.py:28-34)
Add `claude_binary` field with config/env lookup:
```python
import os
from src.secrets import get_user_config_value

def get_claude_binary() -> str:
    """Get claude binary from env var, global config, or default."""
    # 1. Environment variable (highest priority)
    if os.environ.get("CLAUDE_BINARY"):
        return os.environ["CLAUDE_BINARY"]
    # 2. Global orchestrator config
    configured = get_user_config_value("claude_binary")
    if configured:
        return configured
    # 3. Default
    return "claude"

@dataclass
class SquadConfig:
    claude_squad_path: str = "claude-squad"
    claude_binary: str = field(default_factory=get_claude_binary)
    auto_yes: bool = True
    session_prefix: str = "wfo"
    command_timeout: int = 30
```

### 2. Modify spawn_session Command (squad_adapter.py:231)
Add `-p` flag to specify the Claude binary:
```python
cmd = ["new", "--name", session_name, "-p", self.config.claude_binary, "--dir", str(self.working_dir)]
```

### 3. Update Tests (test_squad_adapter.py)
- Test that `-p` flag is correctly added to command
- Test env var override behavior
- Test global config lookup
- Test default behavior (still uses "claude")

### 4. Documentation
- **README.md**: Add Happy integration section
- **CLAUDE.md**: Add Happy integration instructions

## Files to Modify
| File | Change |
|------|--------|
| `src/prd/squad_adapter.py` | Add claude_binary config with env/config lookup, add -p flag |
| `tests/prd/test_squad_adapter.py` | Add tests for Happy integration |
| `README.md` | Document Happy integration |
| `CLAUDE.md` | Document Happy integration |

## Risk Analysis
- **Low risk**: Simple addition of CLI flag
- **Backward compatible**: Defaults to "claude"
- **Consideration**: Happy authentication must work when spawned by Claude Squad

## Success Criteria
1. `orchestrator config set claude_binary happy` persists globally
2. `CLAUDE_BINARY=happy` env var overrides config
3. Spawned sessions use `-p happy` flag
4. Spawned sessions appear in Happy mobile app
5. Default behavior unchanged (uses "claude")
6. Documentation in README.md and CLAUDE.md

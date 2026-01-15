# Code Review: CLI Non-Interactive Fixes & NL Support

## Overall Impression
The changes successfully address the issue of the CLI hanging in non-interactive environments (CI, scripts) by implementing a fail-fast mechanism. Additionally, the optional natural language command support is well-integrated without introducing hard dependencies. The code is clean, follows project conventions, and is well-tested.

## 🟢 Strengths
- **Robustness**: The `is_interactive()` check handles various non-interactive scenarios (pipes, CI env vars) effectively.
- **Fail-Fast**: The `confirm()` helper now correctly raises `SystemExit` in non-interactive modes when prompts are impossible, preventing indefinite hangs.
- **Safety**: Critical commands like `init` (overwrite), `advance` (warnings), and `resolve` (conflicts) now use the new safe `confirm()` helper.
- **Extensibility**: The Natural Language command support (`src/nl_commands.py`) is modular and uses `ai-tool-bridge` via a soft dependency pattern (`try-except ImportError`), ensuring core functionality remains lightweight.
- **Testing**: `tests/test_cli_noninteractive.py` provides excellent coverage for both interactive and non-interactive paths, mocking TTY and env vars appropriately.

## 🔍 Findings & Suggestions

### 1. `src/cli.py` - `confirm` Helper
The implementation is solid.
```python
def confirm(prompt: str, yes_flag: bool = False) -> bool:
    if yes_flag:
        return True
    if not is_interactive():
        # ... prints error and exits ...
        sys.exit(1)
    # ... interactive input ...
```
**Observation**: This forces a hard exit if a prompt is hit in CI. This is the correct design for this requirement ("fail fast").

### 2. Natural Language Integration
The optional import in `src/cli.py` is a good practice:
```python
NL_AVAILABLE = False
try:
    from src.nl_commands import register_nl_commands
    from ai_tool_bridge.argparse_adapter import add_nl_subcommand
    NL_AVAILABLE = True
except ImportError:
    pass
```
**Verification**: Confirmed that `add_nl_subcommand` is only called if `NL_AVAILABLE` is true.

### 3. Dependency Management
- `pyproject.toml` correctly lists `ai-tool-bridge` under `[project.optional-dependencies]`. This ensures users who don't need NL features aren't forced to install extra packages.

## Questions
- **None**: The implementation is self-explanatory and matches the intent described in the commit message.

## Decision
**Approve**.
The changes are high quality, address the root cause of the hanging issue, and introduce new capabilities safely.

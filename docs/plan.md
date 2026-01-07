# Implementation Plan: Multi-Source Secrets Manager

## Overview

Implement a `SecretsManager` that provides unified access to secrets from multiple sources, enabling the orchestrator to work across different environments (local dev, CI/CD, Claude Code Web).

## Problem Statement

When using workflow-orchestrator in Claude Code Web:
- Environment variables don't persist across sessions
- SOPS requires the AGE key, which has the same delivery problem
- No way to access secrets without manual pasting each session

## Solution

Multi-source secrets manager that tries sources in priority order:
1. **Environment Variables** - Direct env var lookup (highest priority)
2. **SOPS-encrypted files** - Decrypt using SOPS_AGE_KEY
3. **GitHub Private Repo** - Fetch from user's private secrets repo

This complements existing SOPS infrastructure rather than replacing it.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Priority order | env → SOPS → GitHub | Env vars fastest, SOPS for teams, GitHub for Claude Code Web |
| Config location | User config + workflow.yaml | Personal settings separate from project |
| GitHub format | Simple text files | One secret per file, easy to manage |
| Caching | In-memory only | Never persist decrypted secrets to disk |

---

## Implementation Steps

### Step 1: Create SecretsManager Class

```python
# src/secrets.py
class SecretsManager:
    """Multi-source secrets management."""

    def __init__(self, config: dict = None, working_dir: Path = None):
        self._config = config or {}
        self._working_dir = working_dir or Path.cwd()
        self._cache = {}

    def get_secret(self, name: str) -> Optional[str]:
        """Get a secret, trying sources in priority order."""
        if name in self._cache:
            return self._cache[name]

        # 1. Environment variable
        if value := os.environ.get(name):
            return value

        # 2. SOPS
        if value := self._try_sops(name):
            self._cache[name] = value
            return value

        # 3. GitHub repo
        if value := self._try_github_repo(name):
            self._cache[name] = value
            return value

        return None
```

### Step 2: SOPS Integration

- Look for `.manus/secrets.enc.yaml` or configured path
- Require `SOPS_AGE_KEY` env var for decryption
- Use subprocess to call `sops -d` with `--extract` for specific keys
- Fall through gracefully if SOPS not installed

### Step 3: GitHub Repo Integration

- Use `gh api` to fetch from private repo
- Repo configured via `secrets_repo` in user config
- Files stored as `{SECRET_NAME}` (no extension)
- Base64 decode the content from GitHub API response

### Step 4: User Configuration

Create `~/.config/orchestrator/config.yaml`:
```yaml
secrets_repo: keevaspeyer10x/secrets
```

Add CLI commands:
```bash
orchestrator config set secrets_repo keevaspeyer10x/secrets
orchestrator config get secrets_repo
orchestrator config list
```

### Step 5: CLI Secrets Commands

```bash
# Test if a secret is accessible
orchestrator secrets test OPENROUTER_API_KEY

# Show which source a secret comes from
orchestrator secrets source OPENROUTER_API_KEY

# List configured sources
orchestrator secrets sources
```

### Step 6: Integration with Providers

Update `OpenRouterProvider` and review system to use `SecretsManager`:
```python
# In provider initialization
secrets = SecretsManager(config, working_dir)
api_key = secrets.get_secret("OPENROUTER_API_KEY")
```

---

## File Changes Summary

### New Files
| File | Description |
|------|-------------|
| `src/secrets.py` | SecretsManager class |
| `tests/test_secrets.py` | Unit tests |

### Modified Files
| File | Changes |
|------|---------|
| `src/cli.py` | Add `config` and `secrets` commands |
| `src/config.py` | Add user config support |
| `src/providers/openrouter.py` | Use SecretsManager for API key |
| `src/review/api_executor.py` | Use SecretsManager |
| `docs/SETUP_GUIDE.md` | Document secrets configuration |
| `CLAUDE.md` | Add secrets setup instructions |

---

## Security Considerations

1. **Never log secrets** - All secret values redacted in output
2. **Cache in memory only** - No disk persistence of decrypted secrets
3. **GitHub repo validation** - Only fetch from user-configured repo
4. **SOPS key handling** - SOPS_AGE_KEY only read from env (not cached)

---

## Test Cases

### Unit Tests
- `test_get_from_env` - Returns env var when set
- `test_get_from_sops` - Decrypts from SOPS file
- `test_get_from_github` - Fetches from GitHub repo
- `test_priority_order` - Env beats SOPS beats GitHub
- `test_caching` - Second call uses cache
- `test_not_found` - Returns None when not in any source
- `test_sops_not_installed` - Falls through gracefully
- `test_github_not_configured` - Falls through gracefully

### Integration Tests
- `test_provider_uses_secrets_manager` - OpenRouterProvider integrates
- `test_review_uses_secrets_manager` - Review system integrates

---

## Success Criteria

1. Secrets accessible from env vars (existing behavior preserved)
2. Secrets accessible from SOPS when SOPS_AGE_KEY provided
3. Secrets accessible from GitHub private repo
4. User can configure secrets_repo via CLI
5. All existing tests pass
6. Documentation updated

---

## Backwards Compatibility

- All existing env var usage continues to work unchanged
- SOPS infrastructure unchanged (additive)
- New sources are fallbacks, not replacements
- No breaking changes to existing workflows

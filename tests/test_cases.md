# Test Cases: Multi-Source Secrets Manager

## Unit Tests

### SecretsManager Core Tests

#### TC-SEC-001: Get Secret from Environment
**Component:** `src/secrets.py`
**Description:** Returns secret from environment variable
**Setup:** Set `TEST_SECRET=value` in environment
**Input:** `secrets.get_secret("TEST_SECRET")`
**Expected:** Returns "value"
**Priority:** High

#### TC-SEC-002: Environment Priority Over SOPS
**Component:** `src/secrets.py`
**Description:** Env var takes precedence over SOPS
**Setup:** Set env var AND have same secret in SOPS
**Input:** `secrets.get_secret("DUAL_SECRET")`
**Expected:** Returns env var value, not SOPS value
**Priority:** High

#### TC-SEC-003: Environment Priority Over GitHub
**Component:** `src/secrets.py`
**Description:** Env var takes precedence over GitHub
**Setup:** Set env var AND have same secret in GitHub repo
**Input:** `secrets.get_secret("DUAL_SECRET")`
**Expected:** Returns env var value
**Priority:** High

#### TC-SEC-004: Secret Not Found Returns None
**Component:** `src/secrets.py`
**Description:** Returns None when secret not in any source
**Input:** `secrets.get_secret("NONEXISTENT_SECRET")`
**Expected:** Returns None
**Priority:** High

#### TC-SEC-005: Caching Works
**Component:** `src/secrets.py`
**Description:** Second call uses cached value
**Setup:** Mock SOPS to return value once
**Input:** Call `get_secret` twice
**Expected:** SOPS called only once, both return same value
**Priority:** Medium

#### TC-SEC-006: Cache Only In Memory
**Component:** `src/secrets.py`
**Description:** Cache not persisted to disk
**Setup:** Get a secret, check filesystem
**Expected:** No cache files created anywhere
**Priority:** High

### SOPS Integration Tests

#### TC-SOPS-001: Get Secret from SOPS
**Component:** `src/secrets.py`
**Description:** Decrypts and returns secret from SOPS file
**Setup:** Create encrypted SOPS file, set SOPS_AGE_KEY
**Input:** `secrets.get_secret("OPENROUTER_API_KEY")`
**Expected:** Returns decrypted value
**Priority:** High

#### TC-SOPS-002: SOPS Not Installed Falls Through
**Component:** `src/secrets.py`
**Description:** Gracefully skips SOPS when not installed
**Setup:** Mock shutil.which("sops") to return None
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Continues to GitHub source, no error
**Priority:** High

#### TC-SOPS-003: SOPS_AGE_KEY Not Set Falls Through
**Component:** `src/secrets.py`
**Description:** Skips SOPS when key not set
**Setup:** Ensure SOPS_AGE_KEY not in env
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Continues to GitHub source, no error
**Priority:** High

#### TC-SOPS-004: SOPS File Not Found Falls Through
**Component:** `src/secrets.py`
**Description:** Skips SOPS when file doesn't exist
**Setup:** Configure nonexistent sops_file path
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Continues to GitHub source, no error
**Priority:** Medium

#### TC-SOPS-005: SOPS Decryption Error Falls Through
**Component:** `src/secrets.py`
**Description:** Handles decryption errors gracefully
**Setup:** Corrupt SOPS file or wrong key
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Logs error, continues to GitHub source
**Priority:** Medium

### GitHub Repo Integration Tests

#### TC-GH-001: Get Secret from GitHub Repo
**Component:** `src/secrets.py`
**Description:** Fetches secret from private GitHub repo
**Setup:** Configure secrets_repo, mock gh api response
**Input:** `secrets.get_secret("OPENROUTER_API_KEY")`
**Expected:** Returns file content from repo
**Priority:** High

#### TC-GH-002: GitHub Repo Not Configured Falls Through
**Component:** `src/secrets.py`
**Description:** Skips GitHub when not configured
**Setup:** No secrets_repo in config
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Returns None (no more sources)
**Priority:** High

#### TC-GH-003: GitHub Secret Not Found Falls Through
**Component:** `src/secrets.py`
**Description:** Handles 404 from GitHub gracefully
**Setup:** Configure repo, mock 404 response
**Input:** `secrets.get_secret("NONEXISTENT")`
**Expected:** Returns None
**Priority:** High

#### TC-GH-004: GitHub Auth Error Falls Through
**Component:** `src/secrets.py`
**Description:** Handles 401/403 gracefully
**Setup:** Mock auth error from gh api
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Logs warning, returns None
**Priority:** Medium

#### TC-GH-005: GitHub Rate Limit Handled
**Component:** `src/secrets.py`
**Description:** Handles 429 rate limit
**Setup:** Mock 429 response
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Logs warning, returns None
**Priority:** Medium

#### TC-GH-006: Invalid Repo Format Rejected
**Component:** `src/secrets.py`
**Description:** Validates repo format (owner/name)
**Setup:** Configure secrets_repo="invalid"
**Input:** `secrets.get_secret("SECRET")`
**Expected:** Logs warning, skips GitHub source
**Priority:** Medium

### CLI Config Command Tests

#### TC-CLI-001: Config Set Command
**Component:** `src/cli.py`
**Description:** Sets config value in user config
**Input:** `orchestrator config set secrets_repo owner/repo`
**Expected:** Value saved to ~/.config/orchestrator/config.yaml
**Priority:** High

#### TC-CLI-002: Config Get Command
**Component:** `src/cli.py`
**Description:** Gets config value
**Setup:** Set secrets_repo in config
**Input:** `orchestrator config get secrets_repo`
**Expected:** Prints "owner/repo"
**Priority:** High

#### TC-CLI-003: Config List Command
**Component:** `src/cli.py`
**Description:** Lists all config values
**Input:** `orchestrator config list`
**Expected:** Shows all configured values
**Priority:** Medium

#### TC-CLI-004: Config File Created on First Set
**Component:** `src/cli.py`
**Description:** Creates config dir and file if needed
**Setup:** Remove ~/.config/orchestrator/
**Input:** `orchestrator config set secrets_repo owner/repo`
**Expected:** Directory and file created
**Priority:** Medium

### CLI Secrets Command Tests

#### TC-CLI-005: Secrets Test Command - Found
**Component:** `src/cli.py`
**Description:** Tests if secret is accessible
**Setup:** Set TEST_SECRET in env
**Input:** `orchestrator secrets test TEST_SECRET`
**Expected:** Prints success message
**Priority:** High

#### TC-CLI-006: Secrets Test Command - Not Found
**Component:** `src/cli.py`
**Description:** Reports when secret not found
**Input:** `orchestrator secrets test NONEXISTENT`
**Expected:** Prints not found message
**Priority:** High

#### TC-CLI-007: Secrets Source Command
**Component:** `src/cli.py`
**Description:** Shows which source provides secret
**Setup:** Set TEST_SECRET in env
**Input:** `orchestrator secrets source TEST_SECRET`
**Expected:** Prints "env"
**Priority:** Medium

#### TC-CLI-008: Secrets Sources Command
**Component:** `src/cli.py`
**Description:** Lists available sources and their status
**Input:** `orchestrator secrets sources`
**Expected:** Shows env (always), SOPS (if installed), GitHub (if configured)
**Priority:** Medium

### Security Tests

#### TC-SECURITY-001: Secret Values Never Logged
**Component:** `src/secrets.py`
**Description:** No secret values appear in logs
**Setup:** Enable debug logging, fetch secret
**Expected:** Only secret names logged, never values
**Priority:** High

#### TC-SECURITY-002: Secret Values Redacted in Errors
**Component:** `src/secrets.py`
**Description:** Errors don't expose secret values
**Setup:** Trigger error with secret in path
**Expected:** [REDACTED] in error message
**Priority:** High

#### TC-SECURITY-003: SOPS_AGE_KEY Not Cached
**Component:** `src/secrets.py`
**Description:** AGE key only read from env, not cached
**Expected:** No AGE key stored in SecretsManager
**Priority:** High

## Integration Tests

### TC-INT-001: Full Priority Chain
**Description:** Verify env → SOPS → GitHub priority
**Setup:** Same secret in all three sources
**Expected:** Returns env value
**Priority:** High

### TC-INT-002: Provider Uses SecretsManager
**Description:** OpenRouterProvider gets API key from SecretsManager
**Setup:** Configure secrets_repo with OPENROUTER_API_KEY
**Expected:** Provider works with fetched key
**Priority:** High

### TC-INT-003: Review System Uses SecretsManager
**Description:** Review API executor gets key from SecretsManager
**Setup:** Configure secrets
**Expected:** Reviews work with fetched keys
**Priority:** Medium

## Backwards Compatibility Tests

### TC-BC-001: Existing Env Var Usage Unchanged
**Description:** Direct OPENROUTER_API_KEY env var still works
**Setup:** Set OPENROUTER_API_KEY directly
**Input:** Use OpenRouterProvider
**Expected:** Works exactly as before
**Priority:** High

### TC-BC-002: Existing SOPS Scripts Work
**Description:** .manus/decrypt-secrets.sh still works
**Setup:** Existing SOPS infrastructure
**Input:** Run existing decrypt script
**Expected:** Script works unchanged
**Priority:** High

## Coverage Requirements

- Minimum 90% coverage for `src/secrets.py`
- All source fallthrough paths tested
- All error paths have tests
- No secret values in test output
- Integration tests marked with `@pytest.mark.integration`

# Gemini CLI Setup for Orchestrator

## Current Status: WORKING

**Last verified:** January 2026
**Method:** SOPS-encrypted API key

Gemini CLI is configured and working with API key authentication via SOPS.

## Quick Start

The orchestrator now has SOPS-based secrets management configured.

**To load secrets:**
```bash
source ./scripts/load-secrets.sh
```

**Or with direnv (auto-loads when entering directory):**
```bash
direnv allow
```

**Files:**
- `secrets.enc.yaml` - Encrypted secrets (safe to commit)
- `scripts/load-secrets.sh` - Helper script to load secrets
- `.envrc` - Auto-load for direnv users
- `~/.config/sops/age/keys.txt` - AGE private key (DO NOT COMMIT)

## Alternative: Manual API Key Setup

For the orchestrator to use Gemini CLI consistently without interactive login:

### Step 1: Get a Gemini API Key

1. Go to [Google AI Studio](https://ai.google.dev/gemini-api/docs/api-key)
2. Create or select a project
3. Generate an API key

### Step 2: Configure the Key (Choose ONE method)

**Option A: Environment Variable (Best for shell sessions)**

Add to `~/.bashrc` or `~/.zshrc`:
```bash
export GEMINI_API_KEY="your-api-key-here"
```

**Option B: .env File (Best for project-specific)**

Create `~/.gemini/.env`:
```
GEMINI_API_KEY="your-api-key-here"
```

**Option C: Project .env (Best for per-project keys)**

Create `.gemini/.env` in the project root:
```
GEMINI_API_KEY="your-api-key-here"
```

### Step 3: Verify

```bash
source ~/.bashrc  # or restart terminal
gemini "Hello, test connection"
```

## Alternative: Google Login (Interactive Only)

For interactive use only:
```bash
gemini
# Select "Login with Google" when prompted
# Follow OAuth flow in browser
```

Note: This requires periodic re-authentication and won't work for automated orchestrator calls.

## For Vertex AI (Enterprise)

If using Google Cloud Vertex AI instead of consumer Gemini API:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
gcloud auth application-default login
```

Then set `GOOGLE_GENAI_USE_VERTEXAI=true`.

## Integration with Orchestrator

For the orchestrator to use Gemini CLI programmatically, ensure:

1. API key is set as environment variable before starting orchestrator
2. Or API key is in `~/.gemini/.env` (loaded automatically)

The orchestrator should NOT rely on interactive "Login with Google" authentication.

## Sources

- [Gemini CLI Authentication](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/authentication.md)
- [Gemini CLI Configuration](https://geminicli.com/docs/get-started/configuration/)
- [Google AI API Keys](https://ai.google.dev/gemini-api/docs/api-key)

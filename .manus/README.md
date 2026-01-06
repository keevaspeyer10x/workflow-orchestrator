# Manus AI Workflow Secrets

This directory contains encrypted project-specific secrets for AI workflow automation.

## Architecture

- **Encryption:** [age](https://github.com/FiloSottile/age) + [SOPS](https://github.com/getsops/sops)
- **Key Storage:** Master decryption key stored in Manus project secrets as `SOPS_AGE_KEY`
- **Encrypted File:** `secrets.enc.yaml` - committed to repo, values encrypted

## Files

| File | Purpose |
|------|---------|
| `secrets.enc.yaml` | Encrypted secrets (safe to commit) |
| `decrypt-secrets.sh` | Helper script to decrypt secrets |
| `README.md` | This documentation |

## Usage

### Prerequisites

1. Install tools: `apt-get install age` and download [sops](https://github.com/getsops/sops/releases)
2. Set the decryption key: `export SOPS_AGE_KEY="<key-from-manus-secrets>"`

### Decrypt Secrets

```bash
# View decrypted secrets
./decrypt-secrets.sh

# Output as JSON
./decrypt-secrets.sh --json

# Get a specific key
./decrypt-secrets.sh --get "workflow_orchestrator.api_keys.openrouter"

# Export as environment variables
eval $(./decrypt-secrets.sh --env)
```

### Add/Edit Secrets

```bash
# Edit encrypted file directly (requires SOPS_AGE_KEY)
sops .manus/secrets.enc.yaml

# Or create new plaintext, encrypt, then delete plaintext
sops --encrypt secrets.yaml > secrets.enc.yaml
rm secrets.yaml
```

## Key Information

- **Public Key:** `age1g30eu0w5xsudt5pg0dt28xm2d82dwmvvyznxu60acsm8vv9x4q6se6dkvq`
- **Secret Key:** Stored in Manus project secrets as `SOPS_AGE_KEY`

## Security Notes

1. Never commit plaintext secrets
2. The encrypted file is safe to commit - only key holders can decrypt
3. Rotate keys periodically by re-encrypting with a new key pair
4. Decrypted values should stay in memory, not written to disk

## Current Secrets

| Key Path | Description |
|----------|-------------|
| `workflow_orchestrator.api_keys.openrouter` | OpenRouter API key for LLM provider |

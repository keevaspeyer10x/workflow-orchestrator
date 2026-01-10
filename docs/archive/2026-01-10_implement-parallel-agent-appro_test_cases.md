# Test Cases for CORE-024: Session Transcript Logging

## TranscriptLogger Tests

### TC-SCRUB-001: Known Secrets Scrubbing
- Input: Text containing actual API key from SecretsManager
- Expected: Key replaced with `[REDACTED:SECRET_NAME]`

### TC-SCRUB-002: Pattern-based Scrubbing (OpenAI)
- Input: Text containing `sk-abc123xyz`
- Expected: Replaced with `[REDACTED:OPENAI_KEY]`

### TC-SCRUB-003: Pattern-based Scrubbing (GitHub)
- Input: Text containing `ghp_abc123xyz`
- Expected: Replaced with `[REDACTED:GITHUB_TOKEN]`

### TC-SCRUB-004: Pattern-based Scrubbing (xAI)
- Input: Text containing `xai-abc123xyz`
- Expected: Replaced with `[REDACTED:XAI_KEY]`

### TC-SCRUB-005: Pattern-based Scrubbing (Stripe)
- Input: Text containing `pk_live_xxx` or `sk_live_xxx`
- Expected: Replaced with `[REDACTED:STRIPE_KEY]`

### TC-SCRUB-006: Bearer Token Scrubbing
- Input: Text containing `Bearer eyJhbGc...`
- Expected: Replaced with `[REDACTED:BEARER_TOKEN]`

### TC-LOG-001: Session Logging
- Input: Session ID and content
- Expected: File created in `.workflow_sessions/`

### TC-LOG-002: Session Directory Auto-creation
- Input: Log to non-existent directory
- Expected: Directory created automatically

### TC-LIST-001: List Sessions
- Input: Multiple sessions in directory
- Expected: List sorted by date, newest first

### TC-SHOW-001: Get Session Content
- Input: Valid session ID
- Expected: Session content returned

### TC-CLEAN-001: Clean Old Sessions
- Input: Sessions older than N days
- Expected: Old sessions removed, new ones kept

## CLI Tests

### TC-CLI-001: sessions list command
### TC-CLI-002: sessions show command
### TC-CLI-003: sessions clean command

# Codex Review: Existing Orchestrator Codebase

**Date:** January 2026
**Reviewer:** OpenAI Codex (gpt-5.1-codex-max)
**Focus:** Existing workflow orchestrator security and design issues

---

## Critical Issues

1. **Path traversal check is ineffective** (`src/engine.py:700-708`)
   - Uses `str(path).startswith(str(self.working_dir))` for allow-listing
   - `/tmp/a` will accept `/tmp/a-evil` and other sibling paths
   - A workflow can probe files outside the project
   - **Fix:** Use `Path.is_relative_to`/`commonpath` with resolved paths instead of string prefix

2. **Manual/required gates are bypassable** (`src/schema.py:74-82`)
   - Checklist items default to `skippable=True`
   - A required manual gate can be skipped with a 10-char reason and the phase can advance
   - Undermines "active verification" guarantees

3. **Dashboard approval endpoint has no auth or CSRF protection** (`src/dashboard.py:592-609`)
   - Any local page can POST `/api/approve` and advance phases
   - A malicious site visited in the same browser could silently approve a gate

---

## Security Concerns

1. **Template variable validation gap** (`src/cli.py:188-210`)
   - Workflow validation doesn't detect missing template vars unless `settings` exists
   - Templated commands can execute with raw `{{var}}` tokens
   - Leads to unintended shell tokens or false sense of sanitization

2. **Command verification only sanitizes substituted settings** (`src/engine.py:715-757`)
   - Base command not sanitized
   - A malicious workflow file can run arbitrary binaries
   - No allow-list or prompting for dangerous commands despite "security hardening" claims

3. **Dashboard serves dynamic status without protection** (`src/dashboard.py:566-609`)
   - No caching headers or auth
   - Exposes workflow metadata to any local user
   - Enables trivial scraping

4. **No integrity checks on stored files** (`src/engine.py:264-306`)
   - Workflow definition and log/state files have no integrity checks or signatures
   - Tampering or rollback isn't detectable
   - Checksum is recorded but never enforced when reloading

---

## Missing Elements

1. **No policy model for per-item skippable/force rules**
   - No way to specify "manual_gate items are never skippable"
   - No "force advance requires human auth" option

2. **No provenance or trust level on workflow YAML/commands**
   - Nothing distinguishes user-authored vs. downloaded workflows

3. **No multi-agent concurrency controls**
   - No coordination primitives beyond single shared state
   - Parallel phases/tasks aren't supported
   - No conflict resolution between agents

4. **No audit-log integrity (hash chain/MAC) or rotation**
   - A compromised agent can rewrite `.workflow_log.jsonl`

5. **No test coverage for critical paths**
   - Engine transitions, security gates, dashboard endpoints untested

---

## Improvement Suggestions

1. **Fix path safety**
   - Use `resolved_path.is_relative_to(working_dir)` (or `commonpath`) for all file checks
   - Add tests for traversal edge cases

2. **Make manual-gate items non-skippable by default**
   - Enforce "required gates cannot be skipped"
   - Add policy flag to override explicitly with human approval

3. **Add auth/CSRF defenses to dashboard**
   - CSRF tokens, same-site cookies, optional API key
   - Make approve API opt-in/disabled by default

4. **Enforce stored YAML checksum on reload**
   - Fail or warn loudly when on-disk workflow doesn't match version-locked definition

5. **Strengthen command verification**
   - Optional allow-list of executables
   - Explicit "dangerous command" prompt
   - Validation of unresolved `{{vars}}` regardless of settings presence

6. **Enhance validation**
   - Flag missing template variables
   - Flag duplicate IDs across phases
   - Flag conflicting required/skippable combinations

7. **Add log hardening**
   - Append-only hash chain
   - Rotation
   - Lightweight audit viewer that highlights tampering

8. **Broaden test suite**
   - State transitions
   - Skip/advance rules
   - Traversal checks
   - Dashboard handlers

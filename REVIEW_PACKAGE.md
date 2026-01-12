# Multi-Repo Support & Containment Strategy Review Package

## Context

The workflow-orchestrator is a 5-phase development workflow tool for AI agents. We're evaluating changes to support multi-repo usage, especially for Claude Code Web (ephemeral browser sessions).

## Current Problems

### 1. File Pollution (10+ files scattered in repo root)
```
repo/
├── .workflow_state.json
├── .workflow_log.jsonl
├── .workflow_checkpoints/
├── .workflow_feedback.jsonl
├── .workflow_tool_feedback.jsonl
├── .workflow_process_feedback.jsonl
├── .secrets.enc
├── secrets.enc.yaml
├── .orchestra.yaml
├── .orchestrator/
└── .claude/prd_state.json
```

**Issues:**
- Namespace pollution (7 gitignore patterns needed)
- Hard to understand "what's orchestrator vs my code"
- Difficult to migrate state between repos
- Not ephemeral-friendly (web sessions)

### 2. Multi-Repo Gaps

**From codebase analysis:**

1. **Session Hook Path Hardcoding** - Each repo needs `.claude/hooks/session-start.sh`
2. **Global State Confusion** - `~/.orchestrator/config.yaml` applies to ALL repos
3. **Secrets Password is Global** - `SECRETS_PASSWORD` shared across repos
4. **No Per-Repo Validation** - Missing secrets fail silently
5. **Feedback File Conflicts** - No file locking for concurrent sessions
6. **PRD State Collisions** - `.claude/prd_state.json` can be overwritten
7. **Bundled Workflow Updates** - New features don't propagate to old repos

### 3. Claude Code Web Compatibility

**What doesn't work:**
- Session hooks (desktop-only feature)
- Global config persistence (`~` may be ephemeral)
- SOPS/age encryption (complex key chain)
- Install script (may not be allowed in sandbox)

**What does work:**
- Direct pip install
- GitHub private repo secrets (already implemented)
- Environment variables via Happy
- Per-repo state files

## Proposed Solution: Containment Strategy

### Single Directory Structure

```
repo/
├── .orchestrator/           # Everything in one place
│   ├── state.json           # Was .workflow_state.json
│   ├── log.jsonl            # Was .workflow_log.jsonl
│   ├── checkpoints/
│   ├── feedback/
│   │   ├── tool.jsonl
│   │   └── process.jsonl
│   ├── secrets/
│   ├── prd/
│   └── config.yaml          # Was .orchestra.yaml
├── workflow.yaml            # User-facing (committable)
└── .claude/                 # Claude Code convention
```

### Benefits

1. **Minimal Footprint** - 2 items in root vs 10+
2. **Simple Gitignore** - 1 pattern vs 7
3. **Easy Cleanup** - `rm -rf .orchestrator/`
4. **Clear Ownership** - "Everything in .orchestrator/ is orchestrator's"
5. **Migration-Friendly** - Copy one directory between repos
6. **Ephemeral-Ready** - Easy to commit/restore entire state

### Implementation Plan

**Phase 1: Backward Compatibility (v2.7.0)**
- Add `PathResolver` class that checks both old/new locations
- Auto-migrate files when accessed
- No user action needed

**Phase 2: Migration Command (v2.7.0)**
- Add `orchestrator migrate --to-contained`
- Explicit migration with backup

**Phase 3: New Default (v2.8.0)**
- New workflows use `.orchestrator/` by default
- Old workflows still work

**Phase 4: Remove Old Paths (v3.0.0)**
- Only support contained structure (breaking change)

## Alternative Approaches Considered

### Alternative 1: Keep Current Structure, Add Web Support
**Pros:** No migration needed
**Cons:** Doesn't solve file pollution, harder to maintain two code paths

### Alternative 2: Per-Repo Config Only
**Pros:** Simpler than full containment
**Cons:** Still leaves scattered files, doesn't solve cleanup/migration

### Alternative 3: Portable Mode Flag
**Pros:** Users can opt-in to containment
**Cons:** Split behavior makes debugging harder

## Review Questions

### Architecture
1. Is the containment strategy sound? Any missing edge cases?
2. Is the migration path (4 phases over 6 months) reasonable?
3. Should we support both structures long-term or deprecate old?

### Multi-Repo Usage
4. What other multi-repo pain points should we address?
5. Is session isolation (session IDs, file locking) sufficient?
6. Should secrets be per-repo or global by default?

### Web Compatibility
7. Is auto-commit state persistence a good approach for web?
8. Should we prioritize containment or web features first?
9. What other web-specific considerations are we missing?

### Implementation
10. Is `PathResolver` class the right abstraction?
11. Should migration be automatic (on-access) or manual (command)?
12. How do we handle repos with custom `.workflow_*` files?

### User Experience
13. Will this break existing workflows? How to minimize disruption?
14. Is the communication/documentation strategy clear?
15. Should we offer a "portable mode" for testing containment?

## Success Metrics

- [ ] New users never see scattered files
- [ ] Existing users can migrate with one command
- [ ] Gitignore complexity: 7 patterns → 1 pattern
- [ ] Cleanup: multi-step → `rm -rf .orchestrator/`
- [ ] Multi-repo: manual setup → copy one directory
- [ ] Web sessions: complex setup → auto-bootstrap

## Additional Context

**Current Usage:**
- Desktop: Claude Code CLI (primary)
- Web: Claude Code Web via Happy (growing)
- Standalone: Direct Python usage (minimal)

**User Base:**
- Single developer (keevaspeyer10x)
- Dogfooding on orchestrator development
- Planning to use across multiple repos for "vibe coding"

**Technical Constraints:**
- Python 3.8+ required
- Git required
- Optional: tmux (for parallel agents), SOPS (for encryption)

**Related Work:**
- WF-034 Phase 2: Adherence validation (self-assessment)
- PRD-008: Zero-config enforcement (`orchestrator enforce`)
- Phase 3b: Two-tier feedback system (tool vs process)

## Files to Review

1. `CONTAINMENT_PROPOSAL.md` - Full technical specification
2. This document - Summary and review questions
3. Current codebase state (for context)

# PRD Task: core-024-session-logging

## Description
CORE-024: Session Transcript Logging with Secret Scrubbing

Implement session transcript logging that automatically scrubs secrets.

**Deliverables:**
1. Create `src/transcript_logger.py` with:
   - TranscriptLogger class
   - Known-secret replacement (from SecretsManager)
   - Pattern-based scrubbing (API key formats: sk-*, ghp_*, xai-*, Bearer tokens)
   - Configurable custom patterns

2. Create `.workflow_sessions/` directory management:
   - Auto-create on first log
   - Add to .gitignore template

3. Add `sessions` CLI command group:
   - `orchestrator sessions list` - List recent sessions
   - `orchestrator sessions show <id>` - View specific session
   - `orchestrator sessions clean --older <days>` - Clean old sessions

4. Add retention/rotation policy (configurable, default 30 days)

5. Add tests in `tests/test_transcript_logger.py`

6. Update CLAUDE.md with documentation

**Reference:** See ROADMAP.md section "CORE-024: Session Transcript Logging"


## IMPORTANT: Use the Orchestrator Workflow

You MUST use the orchestrator workflow system for this task. This ensures proper planning,
external AI code reviews, verification, and learning documentation.

```bash
# Start the workflow
orchestrator start "CORE-024: Session Transcript Logging with Secret Scrubbing

Implement session transcript logging that automatically scrubs secrets.

**Deliverables:**
1. Create `src/transcript_logger.py` with:
   - TranscriptLogger class
   - Known-secret replacement (from SecretsManager)
   - Pattern-based scrubbing (API key formats: sk-*, ghp_*, xai-*, Bearer tokens)
   - Configurable custom patterns

2. Create `.workflow_sessions/` directory management:
   - Auto-create on first log
   - Add to .gitignore template

3. Add `sessions` CLI command group:
   - `orchestrator sessions list` - List recent sessions
   - `orchestrator sessions show <id>` - View specific session
   - `orchestrator sessions clean --older <days>` - Clean old sessions

4. Add retention/rotation policy (configurable, default 30 days)

5. Add tests in `tests/test_transcript_logger.py`

6. Update CLAUDE.md with documentation

**Reference:** See ROADMAP.md section "CORE-024: Session Transcript Logging"
"

# Follow all 5 phases:
# 1. PLAN - Define approach, get approval
# 2. EXECUTE - Implement code and tests
# 3. REVIEW - Run external AI reviews (security, quality, consistency)
# 4. VERIFY - Final testing
# 5. LEARN - Document learnings

# Use orchestrator commands throughout:
orchestrator status          # Check current phase
orchestrator complete <id>   # Complete items
orchestrator advance         # Move to next phase
orchestrator finish          # Complete workflow
```

## Branch
Create your work on branch: `claude/core-024-session-logging`

## Requirements
1. Use `orchestrator start` FIRST before any implementation
2. Follow all orchestrator phases - do not skip REVIEW or LEARN
3. Ensure external AI reviews pass (REVIEW phase)
4. Write tests for your changes
5. Ensure all tests pass
6. Commit with clear messages

## When Complete
- Ensure orchestrator workflow is finished (`orchestrator finish`)
- Commit all changes
- Push your branch
- The parent PRD executor will handle merging

## PRD Context
This task is part of PRD: prd-parallel-core-work
Dependencies: None

# PRD v2.2 Summary

## 5 Features to Implement

### Feature 1: Provider Abstraction
- Create `src/providers/base.py` with AgentProvider interface
- Implement OpenRouter provider (default, uses OPENROUTER_API_KEY)
- Refactor Claude Code provider from existing claude_integration.py
- Implement Manual provider (fallback)
- Add `--provider` and `--model` CLI flags
- Auto-detection priority: explicit flag → env detection → API key → manual

### Feature 2: Environment Detection
- Create `src/environment.py` with Environment enum (CLAUDE_CODE, MANUS, STANDALONE)
- Detection heuristics for each environment
- Environment-specific behavior (default provider, output format, handoff style)
- Add `--env` CLI flag for override

### Feature 3: Operating Notes System
- Add `notes: list[str]` field to PhaseDef and ChecklistItemDef in schema.py
- Display notes in status command with emoji prefixes
- Include notes in handoff prompts
- Learning engine suggests note additions

### Feature 4: Task Constraints Flag
- Add `--constraints` flag to `start` command (multiple allowed)
- Store constraints in WorkflowState
- Display in status and handoff prompts

### Feature 5: Checkpoint/Resume System
- Checkpoint data model with decisions, file_manifest, context_summary
- Store in `.workflow_checkpoints/` directory
- CLI commands: checkpoint, checkpoints, resume
- Auto-checkpoint on phase completion
- Resume handoff prompt with context recovery

## File Changes Summary
| File | Changes |
|------|---------|
| `src/schema.py` | Add notes, constraints, Checkpoint model |
| `src/engine.py` | Add checkpoint/resume methods, integrate constraints |
| `src/cli.py` | Add --provider, --model, --env, --constraints flags, checkpoint commands |
| `src/providers/` | New directory with base.py, openrouter.py, claude_code.py, manual.py |
| `src/environment.py` | New file for environment detection |
| `src/claude_integration.py` | Refactor into src/providers/claude_code.py |

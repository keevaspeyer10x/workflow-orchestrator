# Workflow Orchestrator Roadmap

This document tracks planned features, deferred ideas, and future possibilities for the workflow orchestrator.

## Currently Implementing

> Being implemented in the next development cycle

### Provider Abstraction & OpenRouter Integration
- Generic HTTP API provider interface
- OpenRouter as default provider (requires API key setup)
- Support for model selection per phase/item
- Environment variable configuration for API keys

### Environment Detection & Adaptation
- Auto-detect execution environment (Claude Code, Manus, Standalone CLI)
- Adapt behavior and output format per environment
- Environment-specific handoff generation

### Operating Notes System
- `notes` field on phases and items in workflow.yaml
- Optional categorization via conventions: `[tip]`, `[caution]`, `[learning]`, `[context]`
- Display in recitation (status) and handoff prompts
- Learning engine suggests notes additions after workflows

### Task Constraints Flag
- `--constraints` flag on `orchestrator start`
- Freeform text stored in state
- Included in all recitation and handoff output
- Allows task-specific guidance without schema changes

### Checkpoint/Resume System
- `orchestrator checkpoint` - Save state with context summary
- `orchestrator resume` - Restore from checkpoint with handoff prompt
- Auto-checkpoint at phase transitions (configurable)
- Enables long workflows across context limits

---

## Deferred / Future Ideas

### Sub-Agent Type Hints
- `agent_hint` field on items: `explore`, `plan`, `execute`
- Maps to different models or agent types
- Enables cost/speed optimization
- **Status**: Deferred until provider abstraction settles

### Tool Result Compression
- Change handoff prompts to reference files rather than include content
- "Read these files" lists instead of embedded code
- Reduces context consumption
- **Status**: Optimize later if needed

### Slack Integration
- Slack bot/channel for workflow notifications
- Approval requests via Slack
- Status updates posted to channel
- Manual gate approvals from Slack
- **Status**: Future consideration

### GitHub Integration
- Create issues from workflow items
- Link PRs to workflow phases
- Auto-complete items when PRs merge
- **Status**: Future consideration

### VS Code Extension
- Sidebar showing workflow status
- Click to complete/skip items
- Inline display of operating notes
- **Status**: Future consideration

### Web Dashboard Enhancements
- Multi-workflow view
- Historical analytics graphs
- Learning trends over time
- **Status**: Nice to have

### Workflow Templates Library
- Pre-built workflows for common tasks (bug fix, feature, refactor)
- `orchestrator init --template bugfix`
- Community-contributed templates
- **Status**: Future consideration

### Distributed/Team Workflows
- Multiple agents working on same workflow
- Locking/claiming of items
- Shared state via Git or API
- **Status**: Complex, long-term

### LLM-Assisted Workflow Generation
- Describe task, LLM generates workflow.yaml
- Adaptive workflows that adjust based on progress
- **Status**: Experimental idea

---

## Completed

> Features that have been implemented

- Core workflow engine with phase/item state machine
- YAML-based workflow definitions
- Active verification (file_exists, command, manual_gate)
- Claude Code CLI integration
- Analytics and learning engine
- Web dashboard
- Security hardening (injection protection, path traversal blocking)
- Version-locked workflow definitions in state
- Template variable substitution

---

## Contributing Ideas

Have an idea? Add it to the "Deferred / Future Ideas" section with:
- Brief description
- Use case / motivation
- Status: `Future consideration` or `Experimental idea`

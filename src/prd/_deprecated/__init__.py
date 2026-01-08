"""
Deprecated backends - preserved for reference.

These backends were deprecated in Phase 2 of PRD-001 when the execution
model shifted from WorkerPool-based parallel execution to Claude Squad.

Files:
- local.py: LocalBackend for running Claude Code CLI locally
- modal_worker.py: ModalBackend for Modal serverless
- render.py: RenderBackend for Render containers
- github_actions.py: GitHubActionsBackend for GitHub Actions
- sequential.py: SequentialBackend for sequential execution
- worker_pool.py: WorkerPool for managing parallel workers

See: ClaudeSquadAdapter in src/prd/squad/ for the new model.
"""

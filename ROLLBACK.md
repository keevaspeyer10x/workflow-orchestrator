# Emergency Rollback to v2

If v3 hybrid orchestration introduces issues, follow these steps to rollback.

## Quick Rollback

```bash
# Return to last stable v2 version
git checkout v2.0-stable

# Reinstall the v2 version
pip install -e .

# Clean up any v3 state files
rm -rf .orchestrator/v3/
```

## Verify Rollback

```bash
# Check version
orchestrator --version
# Should show: 2.0.0

# Check status
orchestrator status
# Should work normally without v3 features
```

## What Gets Removed

- v3 hybrid orchestration features
- LLM mode detection changes
- Emergency override functionality
- Any v3-specific state files in `.orchestrator/v3/`

## What Gets Preserved

- Existing workflow state in `.orchestrator/`
- Workflow configuration in `.orchestrator.yaml`
- All committed work (git history preserved)

## Recovery from Partial v3 State

If you need to recover from corrupted v3 state:

```bash
# Remove v3 state but keep v2 state
rm -rf .orchestrator/v3/

# Force re-initialization of current workflow (keeps history)
orchestrator sync --force

# Or if workflow state is completely broken:
mv .orchestrator .orchestrator.backup
orchestrator init
```

## Tag Reference

- `v2.0-stable`: Last stable v2 release before v3 refactor
- Use `git show v2.0-stable` to see what commit this points to

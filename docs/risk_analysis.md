# Risk Analysis: Global Installation (Method C)

## Risk Assessment

### 1. Import Path Breakage

**Risk:** Changing from `sys.path` manipulation to proper package imports could break existing imports across the codebase.

**Impact:** High - CLI could fail to start if imports break.

**Mitigation:**
- Test imports from multiple entry points (direct, pip install, editable install)
- Keep backward compatibility with existing `./orchestrator` bash script
- Run all tests after import changes
- Use relative imports consistently within package

### 2. Package Data Not Found

**Risk:** Bundled `default_workflow.yaml` not included in pip install, causing "no workflow found" errors.

**Impact:** High - Core feature (bundled defaults) wouldn't work.

**Mitigation:**
- Use `package_data` or `include_package_data` in pyproject.toml correctly
- Test installation in fresh environment to verify data files included
- Add startup check that logs which workflow source is being used
- Fall back to clear error message if bundled workflow missing

### 3. Entry Point Not Created

**Risk:** `orchestrator` command not available after pip install due to misconfigured entry points.

**Impact:** High - Global install would be useless.

**Mitigation:**
- Test `pip install .` and verify `which orchestrator` finds command
- Use standard `[project.scripts]` syntax in pyproject.toml
- Document fallback: `python -m src` if entry point fails

### 4. Backward Compatibility for Existing Users

**Risk:** Users with existing repo-based workflows may experience different behavior after update.

**Impact:** Medium - Could disrupt existing workflows.

**Mitigation:**
- Keep `./orchestrator` bash script working exactly as before
- Local `workflow.yaml` always takes precedence over bundled
- State files remain in same location (current directory)
- Document any behavior changes in release notes

### 5. Init Command Overwrites User Data

**Risk:** `orchestrator init` could accidentally overwrite customized `workflow.yaml`.

**Impact:** Medium - User loses customizations.

**Mitigation:**
- Always prompt before overwriting existing file
- Create backup (`workflow.yaml.bak`) before overwriting
- Add `--force` flag to skip prompt (for scripted use)
- Print clear warning showing what will be backed up

### 6. Python Version Compatibility

**Risk:** Package may not work on older Python versions users have installed.

**Impact:** Medium - Users on older Python can't install.

**Mitigation:**
- Specify `requires-python >= "3.10"` in pyproject.toml
- Test on Python 3.10, 3.11, 3.12
- Document minimum Python version prominently
- pip will error clearly if Python version incompatible

### 7. Dependency Conflicts

**Risk:** Package dependencies (pydantic, pyyaml, requests) could conflict with user's existing packages.

**Impact:** Low-Medium - Could prevent installation or break user's environment.

**Mitigation:**
- Use flexible version specifiers (`>=2.0` not `==2.0.1`)
- Recommend `pipx` for isolated installation
- Document as CLI tool, not library (reduces conflict risk)

### 8. Config Discovery Confusion

**Risk:** Users unclear about which workflow.yaml is being used (local vs bundled).

**Impact:** Low - Unexpected behavior, confusion.

**Mitigation:**
- `orchestrator status` always shows workflow source path
- Log message on start: "Using workflow from: <path>"
- Document discovery behavior clearly

## Security Considerations

### No New Attack Surface

This change doesn't introduce new security risks:
- No new network access
- No new file system access beyond current directory
- Package data is read-only
- Init command only writes to current directory

### Dependency Supply Chain

**Risk:** pip install from GitHub could be compromised if repo is compromised.

**Mitigation:**
- Use HTTPS URL
- Pin to specific commits/tags for production use
- Consider signing releases in future

## Rollback Plan

If global installation causes issues:

1. **Immediate:** Use `./orchestrator` bash script directly (always works from repo)
2. **Short-term:** `pip uninstall workflow-orchestrator` and use repo-based workflow
3. **Long-term:** Fix issues and re-release

## Testing Checklist

Before release:
- [ ] `pip install .` works in fresh venv
- [ ] `orchestrator --help` accessible after install
- [ ] `orchestrator status` works with bundled workflow
- [ ] `orchestrator status` works with local workflow.yaml
- [ ] `orchestrator init` creates workflow correctly
- [ ] `orchestrator init` backs up existing file
- [ ] `./orchestrator` bash script still works from repo
- [ ] All existing tests pass

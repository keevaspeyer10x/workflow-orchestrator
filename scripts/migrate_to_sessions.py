#!/usr/bin/env python3
"""
CORE-025 Phase 2b: Migration Script for Session-Based State Management

Migrates legacy orchestrator state files to the new session-based structure:
  .workflow_state.json      -> .orchestrator/sessions/<id>/state.json
  .workflow_log.jsonl       -> .orchestrator/sessions/<id>/log.jsonl
  .workflow_checkpoints/    -> .orchestrator/sessions/<id>/checkpoints/

Legacy files are renamed to .bak extensions (not deleted) unless --cleanup is specified.

Usage:
    python scripts/migrate_to_sessions.py /path/to/repo [--dry-run]
    python scripts/migrate_to_sessions.py /path/to/repo --cleanup  # Also remove legacy files

Options:
    --dry-run    Show what would be done without making changes
    --cleanup    Remove legacy files after successful migration (default: rename to .bak)
"""

import argparse
import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

MAX_SESSION_ID_RETRIES = 10


def generate_session_id() -> str:
    """Generate a unique 8-character session ID using UUID4."""
    return uuid.uuid4().hex[:8]


def is_safe_path(path: Path, base_dir: Path) -> bool:
    """Verify path is within base_dir to prevent directory traversal attacks."""
    try:
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        return str(resolved_path).startswith(str(resolved_base) + "/") or resolved_path == resolved_base
    except (OSError, ValueError):
        return False


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file for verification."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def log_action(log_file: Path, action: str, details: dict):
    """Log an action to the migration log. Resilient to logging failures."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        **details
    }
    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"  [WARN] Could not write to log: {e}")
    print(f"  [{action}] {details.get('message', details)}")


def verify_copy(source: Path, dest: Path) -> bool:
    """Verify that a file was copied correctly using SHA-256 hash comparison."""
    if not dest.exists():
        return False
    if source.is_file() and dest.is_file():
        # First check size (fast), then hash (thorough)
        if source.stat().st_size != dest.stat().st_size:
            return False
        return compute_file_hash(source) == compute_file_hash(dest)
    return True


def migrate_repo(repo_path: Path, dry_run: bool = False, cleanup: bool = False) -> dict:
    """
    Migrate a repository from legacy to session-based state.

    Args:
        repo_path: Path to the repository
        dry_run: If True, show what would be done without making changes
        cleanup: If True, delete legacy files; if False, rename to .bak

    Returns:
        dict with migration results
    """
    results = {
        "repo": str(repo_path),
        "dry_run": dry_run,
        "cleanup": cleanup,
        "migrated_files": [],
        "backed_up_files": [],
        "errors": [],
        "session_id": None,
    }

    # Define paths
    legacy_state = repo_path / ".workflow_state.json"
    legacy_log = repo_path / ".workflow_log.jsonl"
    legacy_checkpoints = repo_path / ".workflow_checkpoints"
    orchestrator_dir = repo_path / ".orchestrator"

    # Migration log file (inside .orchestrator for containment)
    log_file = orchestrator_dir / "migration.log"

    print(f"\n{'='*60}")
    print(f"Migrating: {repo_path}")
    print(f"{'='*60}")

    if dry_run:
        print("  [DRY RUN] No changes will be made")
    if cleanup:
        print("  [CLEANUP] Legacy files will be DELETED after migration")
    else:
        print("  [SAFE] Legacy files will be renamed to .bak")

    # Check if this looks like a valid repo
    is_git_repo = (repo_path / ".git").exists()
    has_workflow = (repo_path / "workflow.yaml").exists()
    if not is_git_repo and not has_workflow:
        msg = f"Warning: {repo_path} doesn't look like a repo (no .git or workflow.yaml)"
        print(f"  [WARN] {msg}")

    # Verify legacy paths are safe (within repo to prevent traversal attacks)
    for legacy_path in [legacy_state, legacy_log, legacy_checkpoints]:
        if not is_safe_path(legacy_path, repo_path):
            msg = f"Security: {legacy_path} is outside repo boundary"
            results["errors"].append(msg)
            print(f"  [ERROR] {msg}")
            return results

    # Check what needs migration
    has_state = legacy_state.exists()
    has_log = legacy_log.exists()
    has_checkpoints = legacy_checkpoints.exists()
    if has_checkpoints:
        try:
            if not legacy_checkpoints.is_dir():
                results["errors"].append(f"{legacy_checkpoints} exists but is not a directory")
                has_checkpoints = False
            else:
                has_checkpoints = any(legacy_checkpoints.iterdir())
        except (PermissionError, NotADirectoryError) as e:
            results["errors"].append(f"Cannot read {legacy_checkpoints}: {e}")
            has_checkpoints = False

    if not has_state and not has_log and not has_checkpoints:
        msg = "No legacy files found - nothing to migrate"
        print(f"  [SKIP] {msg}")
        results["migrated_files"].append(msg)
        return results

    # Generate unique session ID with retry loop for collision handling
    session_id = None
    session_dir = None
    for attempt in range(MAX_SESSION_ID_RETRIES):
        candidate_id = generate_session_id()
        candidate_dir = orchestrator_dir / "sessions" / candidate_id

        # Try to atomically create the directory to avoid race conditions
        if not dry_run:
            try:
                candidate_dir.mkdir(parents=True, exist_ok=False)
                session_id = candidate_id
                session_dir = candidate_dir
                break
            except FileExistsError:
                # Directory exists, retry with new ID
                continue
        else:
            # In dry-run, just check if it exists
            if not candidate_dir.exists():
                session_id = candidate_id
                session_dir = candidate_dir
                break

    if session_id is None:
        msg = f"Failed to generate unique session ID after {MAX_SESSION_ID_RETRIES} attempts"
        results["errors"].append(msg)
        print(f"  [ERROR] {msg}")
        return results

    results["session_id"] = session_id

    # Define new paths
    new_state = session_dir / "state.json"
    new_log = session_dir / "log.jsonl"
    new_checkpoints = session_dir / "checkpoints"
    current_file = orchestrator_dir / "current"
    gitignore_file = orchestrator_dir / ".gitignore"

    print(f"  Session ID: {session_id}")
    print(f"  Target: {session_dir}")

    # === PHASE 1: Copy all files to new location ===
    print("\n  Phase 1: Copying files...")

    # Session directory was already created atomically above
    if not dry_run:
        log_action(log_file, "CREATE_DIR", {"path": str(session_dir), "message": f"Created {session_dir}"})

    # Copy state file
    if has_state:
        if not dry_run:
            try:
                shutil.copy2(legacy_state, new_state)
                if not verify_copy(legacy_state, new_state):
                    raise Exception("Copy verification failed")
                log_action(log_file, "COPY", {
                    "source": str(legacy_state),
                    "dest": str(new_state),
                    "message": f"Copied state file"
                })
                results["migrated_files"].append(str(legacy_state))
            except Exception as e:
                results["errors"].append(f"Failed to copy state: {e}")
                print(f"  [ERROR] Failed to copy state file: {e}")
        print(f"  [COPY] .workflow_state.json -> sessions/{session_id}/state.json")

    # Copy log file
    if has_log:
        if not dry_run:
            try:
                shutil.copy2(legacy_log, new_log)
                if not verify_copy(legacy_log, new_log):
                    raise Exception("Copy verification failed")
                log_action(log_file, "COPY", {
                    "source": str(legacy_log),
                    "dest": str(new_log),
                    "message": f"Copied log file"
                })
                results["migrated_files"].append(str(legacy_log))
            except Exception as e:
                results["errors"].append(f"Failed to copy log: {e}")
                print(f"  [ERROR] Failed to copy log file: {e}")
        print(f"  [COPY] .workflow_log.jsonl -> sessions/{session_id}/log.jsonl")

    # Copy checkpoints
    if has_checkpoints:
        if not dry_run:
            try:
                # Use dirs_exist_ok=False to fail on collision rather than silently merge
                if new_checkpoints.exists():
                    raise FileExistsError(f"Checkpoints destination already exists: {new_checkpoints}")
                shutil.copytree(legacy_checkpoints, new_checkpoints)
                log_action(log_file, "COPY_TREE", {
                    "source": str(legacy_checkpoints),
                    "dest": str(new_checkpoints),
                    "message": f"Copied checkpoints directory"
                })
                results["migrated_files"].append(str(legacy_checkpoints))
            except Exception as e:
                results["errors"].append(f"Failed to copy checkpoints: {e}")
                print(f"  [ERROR] Failed to copy checkpoints: {e}")
        print(f"  [COPY] .workflow_checkpoints/ -> sessions/{session_id}/checkpoints/")

    # Check if any errors occurred during copy phase
    if results["errors"]:
        print(f"\n  [ABORT] Errors occurred during copy - skipping cleanup")
        return results

    # Create current session pointer
    if not dry_run:
        try:
            current_file.write_text(session_id)
            log_action(log_file, "CREATE", {
                "path": str(current_file),
                "content": session_id,
                "message": f"Created current session pointer"
            })
        except Exception as e:
            results["errors"].append(f"Failed to create current pointer: {e}")
            print(f"  [ERROR] Failed to create current pointer: {e}")
    print(f"  [CREATE] .orchestrator/current -> {session_id}")

    # Create .gitignore
    if not dry_run and not gitignore_file.exists():
        try:
            gitignore_file.write_text("*\n")
            log_action(log_file, "CREATE", {
                "path": str(gitignore_file),
                "message": f"Created .gitignore"
            })
        except Exception as e:
            results["errors"].append(f"Failed to create .gitignore: {e}")
            print(f"  [ERROR] Failed to create .gitignore: {e}")
    print(f"  [CREATE] .orchestrator/.gitignore")

    # Check for errors before proceeding to cleanup phase
    if results["errors"]:
        print(f"\n  [ABORT] Errors occurred during setup - skipping cleanup")
        return results

    # === PHASE 2: Handle legacy files (backup or cleanup) ===
    print(f"\n  Phase 2: {'Cleaning up' if cleanup else 'Backing up'} legacy files...")

    if not dry_run:
        if has_state:
            try:
                if cleanup:
                    # Safety: verify path before deletion
                    if legacy_state.name != ".workflow_state.json":
                        raise ValueError(f"Refusing to delete unexpected file: {legacy_state}")
                    legacy_state.unlink()
                    log_action(log_file, "DELETE", {"path": str(legacy_state), "message": "Deleted legacy state"})
                    print(f"  [DELETE] .workflow_state.json")
                else:
                    backup_path = legacy_state.with_suffix(".json.bak")
                    if backup_path.exists():
                        # Generate unique backup name to avoid collision
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_path = repo_path / f".workflow_state.json.{timestamp}.bak"
                    legacy_state.rename(backup_path)
                    log_action(log_file, "BACKUP", {"path": str(legacy_state), "backup": str(backup_path), "message": "Backed up legacy state"})
                    results["backed_up_files"].append(str(backup_path))
                    print(f"  [BACKUP] .workflow_state.json -> {backup_path.name}")
            except Exception as e:
                results["errors"].append(f"Failed to handle legacy state: {e}")
                print(f"  [ERROR] Failed to handle legacy state: {e}")

        if has_log:
            try:
                if cleanup:
                    # Safety: verify path before deletion
                    if legacy_log.name != ".workflow_log.jsonl":
                        raise ValueError(f"Refusing to delete unexpected file: {legacy_log}")
                    legacy_log.unlink()
                    log_action(log_file, "DELETE", {"path": str(legacy_log), "message": "Deleted legacy log"})
                    print(f"  [DELETE] .workflow_log.jsonl")
                else:
                    backup_path = legacy_log.with_suffix(".jsonl.bak")
                    if backup_path.exists():
                        # Generate unique backup name to avoid collision
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_path = repo_path / f".workflow_log.jsonl.{timestamp}.bak"
                    legacy_log.rename(backup_path)
                    log_action(log_file, "BACKUP", {"path": str(legacy_log), "backup": str(backup_path), "message": "Backed up legacy log"})
                    results["backed_up_files"].append(str(backup_path))
                    print(f"  [BACKUP] .workflow_log.jsonl -> {backup_path.name}")
            except Exception as e:
                results["errors"].append(f"Failed to handle legacy log: {e}")
                print(f"  [ERROR] Failed to handle legacy log: {e}")

        if has_checkpoints:
            try:
                if cleanup:
                    # Safety: verify path is the expected legacy checkpoints directory
                    if legacy_checkpoints.name != ".workflow_checkpoints":
                        raise ValueError(f"Refusing to delete unexpected directory: {legacy_checkpoints}")
                    if not legacy_checkpoints.is_dir():
                        raise ValueError(f"Expected directory but found file: {legacy_checkpoints}")
                    shutil.rmtree(legacy_checkpoints)
                    log_action(log_file, "DELETE_TREE", {"path": str(legacy_checkpoints), "message": "Deleted legacy checkpoints"})
                    print(f"  [DELETE] .workflow_checkpoints/")
                else:
                    backup_path = repo_path / ".workflow_checkpoints.bak"
                    if backup_path.exists():
                        # Generate unique backup name to avoid collision
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        backup_path = repo_path / f".workflow_checkpoints.{timestamp}.bak"
                    legacy_checkpoints.rename(backup_path)
                    log_action(log_file, "BACKUP", {"path": str(legacy_checkpoints), "backup": str(backup_path), "message": "Backed up legacy checkpoints"})
                    results["backed_up_files"].append(str(backup_path))
                    print(f"  [BACKUP] .workflow_checkpoints/ -> {backup_path.name}/")
            except Exception as e:
                results["errors"].append(f"Failed to handle legacy checkpoints: {e}")
                print(f"  [ERROR] Failed to handle legacy checkpoints: {e}")

    # Log completion
    if not dry_run and not results["errors"]:
        log_action(log_file, "COMPLETE", {
            "session_id": session_id,
            "migrated_count": len(results["migrated_files"]),
            "backed_up_count": len(results["backed_up_files"]),
            "message": "Migration completed successfully"
        })

    status = "would be " if dry_run else ""
    if results["errors"]:
        print(f"\n  Migration {status}completed with {len(results['errors'])} error(s)")
    else:
        print(f"\n  Migration {status}complete!")
    print(f"  Log file: {log_file}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Migrate orchestrator state to session-based structure"
    )
    parser.add_argument("repo_path", type=Path, help="Path to repository to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--cleanup", action="store_true",
                       help="Delete legacy files instead of renaming to .bak")

    args = parser.parse_args()

    if not args.repo_path.exists():
        print(f"Error: Repository path does not exist: {args.repo_path}")
        sys.exit(1)

    results = migrate_repo(args.repo_path, dry_run=args.dry_run, cleanup=args.cleanup)

    if results["errors"]:
        print(f"\nErrors occurred:")
        for error in results["errors"]:
            print(f"  - {error}")
        sys.exit(1)

    return results


if __name__ == "__main__":
    main()

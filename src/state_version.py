"""
State file versioning for safe rollback.

V3 state files are stored in .orchestrator/v3/ to avoid conflicts with v2.
Includes integrity verification via checksums.
"""

import os
import json
import hashlib
import random
from pathlib import Path
from datetime import datetime, timezone


STATE_VERSION = "3.0"


class StateIntegrityError(Exception):
    """Raised when state file integrity check fails."""
    pass
STATE_DIR_V3 = ".orchestrator/v3"


def get_state_dir() -> Path:
    """Get versioned state directory."""
    return Path(STATE_DIR_V3)


def compute_state_checksum(state_data: dict) -> str:
    """
    Compute checksum for state integrity verification.

    The checksum excludes metadata fields (_checksum, _updated_at) to allow
    verification. Uses SHA256 truncated to 32 chars (128 bits) for security.
    """
    # Exclude metadata fields from hash
    excluded = {'_checksum', '_updated_at'}
    data_copy = {k: v for k, v in state_data.items() if k not in excluded}
    content = json.dumps(data_copy, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def save_state_with_integrity(state_path: Path, state_data: dict):
    """
    Save state with integrity checksum.

    Uses atomic write (temp file + rename + fsync) to prevent corruption.
    Includes directory fsync to ensure rename durability (Issue #80).

    Args:
        state_path: Path to save state file
        state_data: Dictionary of state data
    """
    # Add version and checksum
    state_data['_version'] = STATE_VERSION
    state_data['_checksum'] = compute_state_checksum(state_data)
    state_data['_updated_at'] = datetime.now(timezone.utc).isoformat()

    # Ensure parent directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write - use unique temp file to avoid race conditions
    random_suffix = random.randint(0, 999999)
    temp_path = state_path.with_suffix(f'.tmp.{random_suffix}')
    try:
        with open(temp_path, 'w') as f:
            json.dump(state_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # Ensure written to disk

        temp_path.rename(state_path)

        # Issue #80: Sync directory to ensure rename is durable
        # On some filesystems (e.g., ext4), a crash after rename but before
        # directory sync can lose the rename. This is a best-effort operation.
        try:
            # Use O_DIRECTORY if available (Unix), fallback to O_RDONLY
            flags = os.O_RDONLY
            if hasattr(os, 'O_DIRECTORY'):
                flags |= os.O_DIRECTORY
            dir_fd = os.open(str(state_path.parent), flags)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # Directory fsync failure is non-fatal - state is still saved
            # This can happen on some platforms or filesystems
            pass

    except Exception:
        # Clean up temp file on failure
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def load_state_with_verification(state_path: Path) -> dict:
    """
    Load state and verify integrity.

    Raises:
        StateIntegrityError: If checksum mismatch or version incompatible.
        json.JSONDecodeError: If file contains invalid JSON.
        FileNotFoundError: If state file doesn't exist.
    """
    with open(state_path) as f:
        state_data = json.load(f)

    # Check version
    version = state_data.get('_version', '1.0')
    if not version.startswith('3.'):
        raise StateIntegrityError(
            f"State file version {version} incompatible with v3 orchestrator. "
            f"Run rollback or delete .orchestrator/v3/ to start fresh."
        )

    # Verify checksum exists
    stored_checksum = state_data.get('_checksum')
    if stored_checksum is None:
        raise StateIntegrityError(
            "State file missing checksum. File may be corrupted or tampered."
        )

    # Verify checksum matches
    computed_checksum = compute_state_checksum(state_data)

    if stored_checksum != computed_checksum:
        raise StateIntegrityError(
            f"State file integrity check failed. "
            f"File may have been tampered with or corrupted. "
            f"Expected checksum {stored_checksum}, got {computed_checksum}."
        )

    return state_data

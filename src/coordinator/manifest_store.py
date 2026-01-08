"""
Manifest Storage

Stores and retrieves agent manifests via GitHub Artifacts.
Falls back to local file storage when not running in GitHub Actions.

CRITICAL: Manifests are stored as artifacts, NOT committed to repo.
This avoids merge conflicts, commit noise, and security issues.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import AgentManifest, DerivedManifest

logger = logging.getLogger(__name__)


# ============================================================================
# Manifest Store
# ============================================================================

class ManifestStore:
    """
    Store and retrieve agent manifests.

    When running in GitHub Actions: Uses artifacts API
    When running locally: Uses local file storage for development/testing
    """

    ARTIFACT_PREFIX = "agent-manifest-"
    ARTIFACT_RETENTION_DAYS = 7

    def __init__(
        self,
        local_storage_path: Optional[Path] = None,
    ):
        """
        Initialize manifest store.

        Args:
            local_storage_path: Path for local storage (default: .claude/manifests/)
        """
        self.local_storage_path = local_storage_path or Path(".claude/manifests")
        self.is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"

        if not self.is_github_actions:
            self.local_storage_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using local manifest storage at {self.local_storage_path}")

    def store_manifest(self, manifest: AgentManifest) -> bool:
        """
        Store a manifest.

        Args:
            manifest: The AgentManifest to store

        Returns:
            True if successful, False otherwise
        """
        agent_id = manifest.agent.id

        if self.is_github_actions:
            return self._store_github_artifact(agent_id, manifest)
        else:
            return self._store_local(agent_id, manifest)

    def get_manifest(self, agent_id: str) -> Optional[AgentManifest]:
        """
        Retrieve a manifest by agent ID.

        Args:
            agent_id: The agent's unique identifier

        Returns:
            AgentManifest if found, None otherwise
        """
        if self.is_github_actions:
            return self._get_github_artifact(agent_id)
        else:
            return self._get_local(agent_id)

    def get_all_manifests(self) -> list[AgentManifest]:
        """
        Get all stored manifests.

        Returns:
            List of all AgentManifest objects
        """
        if self.is_github_actions:
            return self._get_all_github_artifacts()
        else:
            return self._get_all_local()

    def delete_manifest(self, agent_id: str) -> bool:
        """
        Delete a manifest.

        Args:
            agent_id: The agent's unique identifier

        Returns:
            True if deleted, False otherwise
        """
        if self.is_github_actions:
            return self._delete_github_artifact(agent_id)
        else:
            return self._delete_local(agent_id)

    # ========================================================================
    # Local Storage (Development/Testing)
    # ========================================================================

    def _store_local(self, agent_id: str, manifest: AgentManifest) -> bool:
        """Store manifest to local file."""
        try:
            file_path = self.local_storage_path / f"{agent_id}.json"
            with open(file_path, "w") as f:
                f.write(manifest.model_dump_json(indent=2))
            logger.debug(f"Stored manifest locally: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to store manifest locally: {e}")
            return False

    def _get_local(self, agent_id: str) -> Optional[AgentManifest]:
        """Get manifest from local file."""
        try:
            file_path = self.local_storage_path / f"{agent_id}.json"
            if not file_path.exists():
                return None
            with open(file_path) as f:
                data = json.load(f)
            return AgentManifest.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to get manifest locally: {e}")
            return None

    def _get_all_local(self) -> list[AgentManifest]:
        """Get all manifests from local storage."""
        manifests = []
        try:
            for file_path in self.local_storage_path.glob("*.json"):
                try:
                    with open(file_path) as f:
                        data = json.load(f)
                    manifests.append(AgentManifest.model_validate(data))
                except Exception as e:
                    logger.warning(f"Failed to load manifest {file_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to list local manifests: {e}")
        return manifests

    def _delete_local(self, agent_id: str) -> bool:
        """Delete manifest from local storage."""
        try:
            file_path = self.local_storage_path / f"{agent_id}.json"
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete local manifest: {e}")
            return False

    # ========================================================================
    # GitHub Artifacts Storage
    # ========================================================================

    def _store_github_artifact(self, agent_id: str, manifest: AgentManifest) -> bool:
        """
        Store manifest as GitHub Actions artifact.

        Uses the @actions/artifact package via gh CLI or direct API calls.
        """
        artifact_name = f"{self.ARTIFACT_PREFIX}{agent_id}"

        try:
            # Write manifest to temp file
            temp_path = Path(f"/tmp/{artifact_name}.json")
            with open(temp_path, "w") as f:
                f.write(manifest.model_dump_json(indent=2))

            # Use GitHub's artifact upload action
            # This works within GitHub Actions workflows
            # For direct API calls, we'd need the actions/upload-artifact action
            # or use the REST API with proper authentication

            # Set output for artifact upload
            github_output = os.environ.get("GITHUB_OUTPUT")
            if github_output:
                with open(github_output, "a") as f:
                    f.write(f"manifest_path={temp_path}\n")
                    f.write(f"artifact_name={artifact_name}\n")

            logger.info(f"Prepared manifest artifact: {artifact_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to store GitHub artifact: {e}")
            return False

    def _get_github_artifact(self, agent_id: str) -> Optional[AgentManifest]:
        """
        Retrieve manifest from GitHub Actions artifact.

        Uses gh CLI to download artifact.
        """
        artifact_name = f"{self.ARTIFACT_PREFIX}{agent_id}"

        try:
            # Use gh CLI to download artifact
            result = subprocess.run(
                [
                    "gh", "run", "download",
                    "--name", artifact_name,
                    "--dir", "/tmp/artifacts"
                ],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.debug(f"Artifact {artifact_name} not found: {result.stderr}")
                return None

            # Read the manifest
            artifact_path = Path(f"/tmp/artifacts/{artifact_name}.json")
            if artifact_path.exists():
                with open(artifact_path) as f:
                    data = json.load(f)
                return AgentManifest.model_validate(data)

            return None

        except Exception as e:
            logger.error(f"Failed to get GitHub artifact: {e}")
            return None

    def _get_all_github_artifacts(self) -> list[AgentManifest]:
        """
        Get all manifest artifacts from GitHub Actions.

        Lists artifacts with our prefix and downloads them.
        """
        manifests = []

        try:
            # List artifacts with our prefix
            result = subprocess.run(
                [
                    "gh", "api",
                    f"/repos/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/artifacts",
                    "--jq", f'.artifacts[] | select(.name | startswith("{self.ARTIFACT_PREFIX}")) | .name'
                ],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.warning(f"Failed to list artifacts: {result.stderr}")
                return []

            artifact_names = [n.strip() for n in result.stdout.strip().split("\n") if n.strip()]

            for artifact_name in artifact_names:
                agent_id = artifact_name.replace(self.ARTIFACT_PREFIX, "")
                manifest = self._get_github_artifact(agent_id)
                if manifest:
                    manifests.append(manifest)

        except Exception as e:
            logger.error(f"Failed to list GitHub artifacts: {e}")

        return manifests

    def _delete_github_artifact(self, agent_id: str) -> bool:
        """Delete a GitHub artifact."""
        artifact_name = f"{self.ARTIFACT_PREFIX}{agent_id}"

        try:
            # Get artifact ID first
            result = subprocess.run(
                [
                    "gh", "api",
                    f"/repos/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/artifacts",
                    "--jq", f'.artifacts[] | select(.name == "{artifact_name}") | .id'
                ],
                capture_output=True,
                text=True
            )

            if result.returncode != 0 or not result.stdout.strip():
                return False

            artifact_id = result.stdout.strip()

            # Delete the artifact
            result = subprocess.run(
                [
                    "gh", "api", "--method", "DELETE",
                    f"/repos/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/artifacts/{artifact_id}"
                ],
                capture_output=True,
                text=True
            )

            return result.returncode == 0

        except Exception as e:
            logger.error(f"Failed to delete GitHub artifact: {e}")
            return False


# ============================================================================
# Convenience Functions
# ============================================================================

def get_manifest_store(local_path: Optional[Path] = None) -> ManifestStore:
    """Get a configured manifest store instance."""
    return ManifestStore(local_storage_path=local_path)

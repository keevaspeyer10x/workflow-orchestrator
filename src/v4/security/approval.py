"""
Approval authentication for V4 Control Inversion.

This module provides:
- HMAC signature verification for approvals
- GitHub OAuth token verification
- Replay attack protection with nonces
- Expiration validation

Security Model:
1. Approvals are signed with HMAC-SHA256
2. Signatures bind request_id, approver, artifact_hash, and nonce
3. OAuth tokens are verified against GitHub API
4. Nonces prevent replay attacks
5. Expiration timestamps prevent stale approvals
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set
import hashlib
import hmac
import secrets
import httpx


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class InvalidSignatureError(Exception):
    """Raised when approval signature is invalid."""
    pass


class UnauthorizedApproverError(Exception):
    """Raised when approver is not authorized."""
    pass


class ReplayAttackError(Exception):
    """Raised when a replay attack is detected."""
    pass


@dataclass
class ApprovalRequest:
    """Request for human approval."""
    id: str
    workflow_id: str
    gate_id: str
    artifact_hash: str  # SHA256 hash of what's being approved
    required_approvers: List[str]
    created_at: datetime
    expires_at: datetime


@dataclass
class Approval:
    """Signed approval record."""
    request_id: str
    approved_by: str  # Identity (e.g., GitHub username)
    approved_at: datetime
    artifact_hash: str  # Must match request
    nonce: str  # Random nonce for replay protection
    signature: str  # HMAC-SHA256 signature

    @classmethod
    def create(
        cls,
        request: ApprovalRequest,
        approver: str,
        signing_key: bytes,
    ) -> "Approval":
        """
        Create signed approval with nonce.

        The signature covers:
        - request_id
        - approved_by
        - artifact_hash
        - nonce
        - approved_at (ISO format)

        This binding prevents:
        - Approval for different request
        - Approval by different user
        - Approval for different content
        - Replay attacks (nonce)
        - Backdating (timestamp)
        """
        nonce = secrets.token_hex(16)  # 128-bit random nonce
        approved_at = _utcnow()

        approval = cls(
            request_id=request.id,
            approved_by=approver,
            approved_at=approved_at,
            artifact_hash=request.artifact_hash,
            nonce=nonce,
            signature="",  # Computed below
        )

        # Compute signature
        approval.signature = approval._compute_signature(signing_key)

        return approval

    def _compute_signature(self, signing_key: bytes) -> str:
        """Compute HMAC-SHA256 signature over approval fields."""
        payload = (
            f"{self.request_id}:"
            f"{self.approved_by}:"
            f"{self.artifact_hash}:"
            f"{self.nonce}:"
            f"{self.approved_at.isoformat()}"
        )
        return hmac.new(
            signing_key,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify(self, signing_key: bytes) -> bool:
        """
        Verify approval signature.

        Uses constant-time comparison to prevent timing attacks.
        """
        expected = self._compute_signature(signing_key)
        return hmac.compare_digest(self.signature, expected)


class ApprovalAuthenticator:
    """
    Authenticates approvers and validates approvals.

    Provides:
    - GitHub OAuth token verification
    - Approver authorization checking
    - Replay protection via nonce tracking
    - Expiration validation
    """

    def __init__(
        self,
        signing_key: bytes,
        nonce_expiry_hours: int = 24,
    ):
        """
        Initialize authenticator.

        Args:
            signing_key: Key for HMAC signatures (should be 32+ bytes)
            nonce_expiry_hours: How long to remember used nonces
        """
        self.signing_key = signing_key
        self.nonce_expiry_hours = nonce_expiry_hours

        # Track used nonces (in production, use Redis or similar)
        self._used_nonces: Set[str] = set()
        self._nonce_timestamps: dict[str, datetime] = {}

    async def authenticate(self, token: str) -> Optional[str]:
        """
        Verify OAuth token and return identity.

        Currently supports GitHub tokens. Returns GitHub username
        if token is valid, None otherwise.

        Args:
            token: OAuth token to verify

        Returns:
            GitHub username if valid, None otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"token {token}",
                        "Accept": "application/vnd.github.v3+json",
                    }
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("login")

        except httpx.RequestError:
            pass

        return None

    def is_authorized(self, identity: str, required_approvers: List[str]) -> bool:
        """
        Check if identity is in required approvers list.

        Args:
            identity: The authenticated identity (e.g., GitHub username)
            required_approvers: List of authorized approvers

        Returns:
            True if identity is authorized
        """
        return identity in required_approvers

    def use_nonce(self, nonce: str) -> None:
        """
        Mark nonce as used (for replay protection).

        Args:
            nonce: The nonce to mark as used

        Raises:
            ReplayAttackError: If nonce was already used
        """
        # Clean up expired nonces first
        self._cleanup_expired_nonces()

        if nonce in self._used_nonces:
            raise ReplayAttackError(f"Nonce already used: {nonce}")

        self._used_nonces.add(nonce)
        self._nonce_timestamps[nonce] = _utcnow()

    def _cleanup_expired_nonces(self) -> None:
        """Remove nonces older than expiry time."""
        cutoff = _utcnow() - timedelta(hours=self.nonce_expiry_hours)

        expired = [
            nonce for nonce, ts in self._nonce_timestamps.items()
            if ts < cutoff
        ]

        for nonce in expired:
            self._used_nonces.discard(nonce)
            del self._nonce_timestamps[nonce]

    def validate_approval(
        self,
        approval: Approval,
        request: ApprovalRequest,
    ) -> None:
        """
        Fully validate an approval.

        Checks:
        1. Signature is valid
        2. Approval not expired
        3. Artifact hash matches request
        4. Approver is authorized
        5. Nonce not previously used

        Args:
            approval: The approval to validate
            request: The original approval request

        Raises:
            InvalidSignatureError: If signature is invalid or approval expired
            UnauthorizedApproverError: If approver not in required list
            ReplayAttackError: If nonce was already used
        """
        # 1. Verify signature
        if not approval.verify(self.signing_key):
            raise InvalidSignatureError("Invalid approval signature")

        # 2. Check expiration
        if _utcnow() > request.expires_at:
            raise InvalidSignatureError(
                f"Approval expired at {request.expires_at.isoformat()}"
            )

        # 3. Verify artifact hash matches
        if approval.artifact_hash != request.artifact_hash:
            raise InvalidSignatureError(
                "Artifact hash mismatch - content changed since approval requested"
            )

        # 4. Check approver is authorized
        if not self.is_authorized(approval.approved_by, request.required_approvers):
            raise UnauthorizedApproverError(
                f"Approver '{approval.approved_by}' not in required approvers: "
                f"{request.required_approvers}"
            )

        # 5. Check nonce not previously used
        self.use_nonce(approval.nonce)

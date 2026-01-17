"""
Path traversal prevention for V4 Control Inversion.

This module provides:
- Safe path resolution with canonicalization
- Symlink escape prevention
- Per-component path validation
- Glob pattern validation

Security Model:
1. All paths are canonicalized (resolve . and ..)
2. Each path component is validated (not just final path)
3. Symlinks are followed and checked for escape
4. URL-encoded and Unicode tricks are detected
5. Absolute paths and tilde expansion are blocked
"""
from pathlib import Path
from typing import Set
import os
import re
import unicodedata
import urllib.parse


class PathTraversalError(Exception):
    """Raised when a path traversal attempt is detected."""
    pass


# Characters that look like dots but aren't (Unicode normalization attacks)
UNICODE_DOT_VARIANTS: Set[str] = {
    "\uff0e",  # FULLWIDTH FULL STOP
    "\u2024",  # ONE DOT LEADER
    "\ufe52",  # SMALL FULL STOP
    "\u0701",  # SYRIAC SUPRALINEAR FULL STOP
    "\u0702",  # SYRIAC SUBLINEAR FULL STOP
}

# Characters that look like slashes but aren't
UNICODE_SLASH_VARIANTS: Set[str] = {
    "\uff0f",  # FULLWIDTH SOLIDUS
    "\u2044",  # FRACTION SLASH
    "\u2215",  # DIVISION SLASH
    "\u29f8",  # BIG SOLIDUS
}


def safe_path(base_dir: Path, user_path: str) -> Path:
    """
    Resolve user path safely within base directory.

    Prevents:
    - Path traversal (../)
    - Symlink escapes
    - Absolute path injection
    - URL-encoded traversal
    - Unicode normalization attacks
    - Null byte injection
    - Tilde expansion

    Args:
        base_dir: The base directory (must be absolute)
        user_path: User-provided path (relative to base)

    Returns:
        Resolved Path within base_dir

    Raises:
        PathTraversalError: If path would escape base_dir
    """
    # Normalize base to absolute canonical form
    base = base_dir.resolve()

    # Check for null bytes
    if "\x00" in user_path:
        raise PathTraversalError(f"Path contains null byte: {user_path}")

    # Check for tilde expansion
    if user_path.startswith("~"):
        raise PathTraversalError(f"Tilde expansion not allowed: {user_path}")

    # Check for absolute paths
    if user_path.startswith("/") or (len(user_path) > 1 and user_path[1] == ":"):
        raise PathTraversalError(f"Absolute paths not allowed: {user_path}")

    # Decode URL encoding and check for traversal
    decoded = _decode_path(user_path)

    # Normalize Unicode (prevent homoglyph attacks)
    normalized = _normalize_unicode(decoded)

    # Check for suspicious patterns after normalization
    _check_traversal_patterns(normalized)

    # Validate each path component
    _validate_path_components(normalized)

    # Check for symlink escapes BEFORE final resolution
    # This gives better error messages for symlink-based escapes
    _check_symlink_escape(base, normalized)

    # Resolve the full path
    target = (base / normalized).resolve()

    # Verify target is within base
    try:
        target.relative_to(base)
    except ValueError:
        # Determine if this was a symlink escape
        _check_for_symlink_in_path(base, normalized, user_path, target)

    return target


def _decode_path(path: str) -> str:
    """
    Decode URL-encoded path and detect encoded traversal.

    Checks both single and double encoding.
    """
    # First decode
    decoded = urllib.parse.unquote(path)

    # Check for traversal in decoded form
    if ".." in decoded and ".." not in path:
        raise PathTraversalError(
            f"URL-encoded path traversal detected: {path}"
        )

    # Check for double encoding
    double_decoded = urllib.parse.unquote(decoded)
    if ".." in double_decoded and ".." not in decoded:
        raise PathTraversalError(
            f"Double-encoded path traversal detected: {path}"
        )

    return decoded


def _normalize_unicode(path: str) -> str:
    """
    Normalize Unicode and detect homoglyph attacks.

    Converts lookalike characters to their ASCII equivalents.
    """
    # Check for dot variants
    for variant in UNICODE_DOT_VARIANTS:
        if variant in path:
            raise PathTraversalError(
                f"Unicode dot variant detected in path: {path}"
            )

    # Check for slash variants
    for variant in UNICODE_SLASH_VARIANTS:
        if variant in path:
            raise PathTraversalError(
                f"Unicode slash variant detected in path: {path}"
            )

    # Normalize to NFC form
    normalized = unicodedata.normalize("NFC", path)

    # Replace backslashes with forward slashes (Windows compatibility)
    normalized = normalized.replace("\\", "/")

    return normalized


def _check_traversal_patterns(path: str) -> None:
    """
    Check for common traversal patterns.
    """
    # Direct .. reference
    if ".." in path:
        raise PathTraversalError(f"Path contains '..' traversal: {path}")

    # Check for encoded patterns that might have slipped through
    suspicious_patterns = [
        r"\.%2e",  # .%2e = ..
        r"%2e\.",  # %2e. = ..
        r"%2e%2e",  # %2e%2e = ..
        r"%252e",  # Double encoded .
        r"%%32%65",  # Mixed encoding
    ]

    lower_path = path.lower()
    for pattern in suspicious_patterns:
        if re.search(pattern, lower_path, re.IGNORECASE):
            raise PathTraversalError(
                f"Suspicious encoded pattern in path: {path}"
            )


def _validate_path_components(path: str) -> None:
    """
    Validate each path component individually.

    This catches attacks where intermediate components escape
    even if the final path resolves inside base.
    """
    components = path.replace("\\", "/").split("/")

    for i, component in enumerate(components):
        # Empty components are OK (consecutive slashes)
        if not component:
            continue

        # Check for .. in any component
        if component == "..":
            raise PathTraversalError(
                f"Path component '{component}' at position {i} is traversal"
            )

        # Check for hidden .. in component (e.g., "foo.." or "..bar")
        if component.startswith("..") or component.endswith(".."):
            if ".." in component:
                raise PathTraversalError(
                    f"Suspicious path component: {component}"
                )


def _check_for_symlink_in_path(
    base: Path,
    normalized: str,
    user_path: str,
    target: Path
) -> None:
    """
    Check if path escape was due to symlink and raise appropriate error.

    This is called after we detect the path escapes base, to provide
    a better error message when the escape is due to a symlink.
    """
    components = normalized.replace("\\", "/").split("/")
    current = base

    for component in components:
        if not component:
            continue
        current = current / component
        if current.exists() and current.is_symlink():
            raise PathTraversalError(
                f"Symlink escapes base directory: {user_path} -> {target}"
            )

    # No symlink found, generic escape error
    raise PathTraversalError(
        f"Path escapes base directory: {user_path} -> {target}"
    )


def _check_symlink_escape(base: Path, user_path: str) -> None:
    """
    Check each path component for symlink escapes.

    Validates that no symlink in the path points outside base.
    """
    components = user_path.replace("\\", "/").split("/")
    current = base

    for component in components:
        if not component:
            continue

        current = current / component

        # If this component exists and is a symlink, check where it points
        if current.exists() and current.is_symlink():
            # Resolve the symlink target
            resolved = current.resolve()

            try:
                resolved.relative_to(base)
            except ValueError:
                raise PathTraversalError(
                    f"Symlink escapes base directory: {component} -> {resolved}"
                )


def validate_glob_pattern(pattern: str) -> bool:
    """
    Validate glob pattern doesn't allow traversal.

    Returns True if pattern is safe, False if potentially dangerous.
    """
    # Deny patterns with ..
    if ".." in pattern:
        return False

    # Deny absolute paths
    if pattern.startswith("/"):
        return False

    # Deny Windows absolute paths
    if len(pattern) > 1 and pattern[1] == ":":
        return False

    # Deny patterns starting with glob that could match parent
    if pattern.startswith("**/.."):
        return False

    # Deny tilde expansion
    if pattern.startswith("~"):
        return False

    return True

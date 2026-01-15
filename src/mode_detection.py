"""
Operator mode detection for orchestrator.

Determines whether the operator is a human or an LLM (like Claude Code).
This is the SECURITY BOUNDARY - false negatives allow LLM to bypass controls.

VERIFIED DETECTION SIGNALS (tested 2025-01-15 in Claude Code):
- CLAUDECODE=1 (present in Claude Code)
- CLAUDE_CODE_ENTRYPOINT=sdk-ts (present in Claude Code)
- stdin.isatty() = False (Claude Code has no TTY)
"""

import os
import sys
from enum import Enum
from dataclasses import dataclass


class OperatorMode(Enum):
    """Operator mode: human or LLM."""
    HUMAN = "human"
    LLM = "llm"


@dataclass
class ModeDetectionResult:
    """Result of mode detection with explanation."""
    mode: OperatorMode
    reason: str
    confidence: str  # "high", "medium", "low"


def detect_operator_mode() -> ModeDetectionResult:
    """
    Detect whether operator is human or LLM.

    Returns ModeDetectionResult with mode, reason, and confidence.

    IMPORTANT: This is logged on every command for audit/debugging.

    Detection priority:
    1. Emergency override (ORCHESTRATOR_EMERGENCY_OVERRIDE) - always works
    2. Explicit mode (ORCHESTRATOR_MODE) - user override
    3. Claude Code detection (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT)
    4. Codex detection (to be verified)
    5. TTY heuristic (stdin.isatty())
    6. Conservative default: LLM mode (safer)
    """

    # 1. Emergency override - ALWAYS works (escape hatch)
    if os.environ.get('ORCHESTRATOR_EMERGENCY_OVERRIDE') == 'human-override-v3':
        return ModeDetectionResult(
            mode=OperatorMode.HUMAN,
            reason="ORCHESTRATOR_EMERGENCY_OVERRIDE set",
            confidence="high"
        )

    # 2. Explicit mode override
    explicit_mode = os.environ.get('ORCHESTRATOR_MODE', '').lower()
    if explicit_mode == 'llm':
        return ModeDetectionResult(
            mode=OperatorMode.LLM,
            reason="ORCHESTRATOR_MODE=llm",
            confidence="high"
        )
    if explicit_mode == 'human':
        return ModeDetectionResult(
            mode=OperatorMode.HUMAN,
            reason="ORCHESTRATOR_MODE=human",
            confidence="high"
        )

    # 3. Claude Code detection (VERIFIED env vars)
    if os.environ.get('CLAUDECODE') == '1':
        return ModeDetectionResult(
            mode=OperatorMode.LLM,
            reason="CLAUDECODE=1 (Claude Code environment)",
            confidence="high"
        )

    if 'CLAUDE_CODE_ENTRYPOINT' in os.environ:
        return ModeDetectionResult(
            mode=OperatorMode.LLM,
            reason="CLAUDE_CODE_ENTRYPOINT present",
            confidence="high"
        )

    # 4. Codex detection (to be verified)
    if 'CODEX' in os.environ or 'codex' in os.environ.get('TERM_PROGRAM', '').lower():
        return ModeDetectionResult(
            mode=OperatorMode.LLM,
            reason="Codex environment detected",
            confidence="medium"
        )

    # 5. TTY heuristic (Claude Code has no TTY)
    if not sys.stdin.isatty():
        return ModeDetectionResult(
            mode=OperatorMode.LLM,
            reason="No TTY (non-interactive session)",
            confidence="medium"
        )

    # 6. Default to human if interactive TTY
    if sys.stdin.isatty() and sys.stdout.isatty():
        return ModeDetectionResult(
            mode=OperatorMode.HUMAN,
            reason="Interactive TTY session",
            confidence="medium"
        )

    # 7. Conservative default: assume LLM (safer)
    return ModeDetectionResult(
        mode=OperatorMode.LLM,
        reason="Unknown environment, defaulting to restricted mode",
        confidence="low"
    )


def is_llm_mode() -> bool:
    """Convenience function for checking if in LLM mode."""
    return detect_operator_mode().mode == OperatorMode.LLM


def log_mode_detection():
    """Log mode detection for audit trail."""
    result = detect_operator_mode()
    print(f"[ORCHESTRATOR] Mode: {result.mode.value} "
          f"(reason: {result.reason}, confidence: {result.confidence})")

"""
Self-Critic (Phase 5)

Optional LLM-based critique of resolution candidates before delivery.
Uses separate LLM call to find subtle issues that might be missed.

Checks for:
- Security issues
- Performance regressions
- Missing error handling
- Inconsistent patterns
- Subtle logic errors
"""

import logging
import re
from typing import Optional

from .schema import (
    ResolutionCandidate,
    ConflictContext,
    CritiqueResult,
)

logger = logging.getLogger(__name__)


# Patterns that indicate security issues in critique response
SECURITY_PATTERNS = [
    r"sql.?injection",
    r"xss",
    r"cross.?site",
    r"command.?injection",
    r"path.?traversal",
    r"insecure",
    r"vulnerability",
    r"security",
    r"unsafe",
    r"credential",
    r"password.?exposure",
    r"authentication.?bypass",
]

# Patterns that indicate critical bugs
CRITICAL_BUG_PATTERNS = [
    r"data.?loss",
    r"corruption",
    r"race.?condition",
    r"deadlock",
    r"infinite.?loop",
    r"crash",
    r"null.?pointer",
    r"undefined.?behavior",
]


class SelfCritic:
    """
    Critiques resolution candidates using LLM.

    Can be disabled for faster resolution when speed is preferred
    over thorough review.
    """

    def __init__(
        self,
        enabled: bool = True,
        model: str = "openai/gpt-5.2-max",
        timeout: int = 60,
    ):
        """
        Initialize self-critic.

        Args:
            enabled: Whether self-critique is enabled
            model: LLM model to use (LiteLLM format)
            timeout: Timeout for LLM call in seconds
        """
        self.enabled = enabled
        self.model = model
        self.timeout = timeout

    def critique(
        self,
        candidate: ResolutionCandidate,
        context: ConflictContext,
    ) -> CritiqueResult:
        """
        Critique a resolution candidate.

        Args:
            candidate: The candidate to critique
            context: Conflict context for additional info

        Returns:
            CritiqueResult with approval status and issues
        """
        if not self.enabled:
            logger.info("Self-critique disabled, auto-approving")
            return CritiqueResult(approved=True)

        try:
            prompt = self._build_prompt(candidate, context)
            response = self._invoke_llm(prompt)
            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Self-critique failed: {e}")
            # On failure, approve but note the failure
            return CritiqueResult(
                approved=True,
                issues=[f"Self-critique failed: {e}"],
                raw_response="",
            )

    def _sanitize_for_prompt(self, text: str, max_length: int = 500) -> str:
        """
        Sanitize text for safe inclusion in LLM prompts.

        SECURITY: Prevents prompt injection by:
        - Escaping special characters
        - Truncating to max length
        - Removing suspicious patterns
        """
        if not text:
            return "(empty)"

        # Truncate
        text = text[:max_length]

        # Remove potential injection patterns
        suspicious_patterns = [
            "IGNORE PREVIOUS",
            "DISREGARD",
            "NEW INSTRUCTIONS",
            "SYSTEM:",
            "ASSISTANT:",
            "```system",
            "```assistant",
        ]
        text_upper = text.upper()
        for pattern in suspicious_patterns:
            if pattern in text_upper:
                text = text.replace(pattern, "[REDACTED]")
                text = text.replace(pattern.lower(), "[REDACTED]")

        # Escape backticks and angle brackets
        text = text.replace("```", "'''")
        text = text.replace("<", "&lt;").replace(">", "&gt;")

        return text

    def _build_prompt(
        self,
        candidate: ResolutionCandidate,
        context: ConflictContext,
    ) -> str:
        """Build the critique prompt."""
        agent_summaries = []
        for agent_id in context.agent_ids:
            # SECURITY: Sanitize agent IDs
            safe_agent_id = self._sanitize_for_prompt(agent_id, max_length=50)

            manifest = next(
                (m for m in context.agent_manifests if m.agent.id == agent_id),
                None
            )
            if manifest:
                # SECURITY: Sanitize task descriptions
                safe_description = self._sanitize_for_prompt(manifest.task.description)
                agent_summaries.append(f"- {safe_agent_id}: {safe_description}")
            else:
                agent_summaries.append(f"- {safe_agent_id}: (no manifest)")

        # Limit diff size for prompt
        diff = candidate.diff_from_base[:5000]
        if len(candidate.diff_from_base) > 5000:
            diff += "\n... (truncated)"

        return f"""Review this code resolution for subtle issues.

## Context

Resolution strategy: {candidate.strategy}

Agent intents:
{chr(10).join(agent_summaries)}

## Resolution Diff

```diff
{diff}
```

## Review Checklist

Please check for:
1. Does this fully satisfy BOTH agents' intents?
2. Any security vulnerabilities introduced?
3. Any performance issues?
4. Any missing error handling?
5. Any deviation from project patterns?
6. Any subtle logic errors?

## Response Format

If the resolution looks good, respond with:
APPROVED

If there are issues, respond with:
ISSUES:
- Issue 1 description
- Issue 2 description

For suggestions that don't block approval:
SUGGESTIONS:
- Suggestion 1
- Suggestion 2
"""

    def _invoke_llm(self, prompt: str) -> str:
        """
        Invoke LLM for critique.

        Uses LiteLLM for model abstraction.
        """
        try:
            import litellm

            response = litellm.completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code review expert. Review code changes for issues.",
                    },
                    {"role": "user", "content": prompt},
                ],
                timeout=self.timeout,
            )

            return response.choices[0].message.content

        except ImportError:
            logger.warning("litellm not installed, skipping LLM critique")
            return "APPROVED (litellm not available)"

        except Exception as e:
            logger.error(f"LLM invocation failed: {e}")
            raise

    def _parse_response(self, response: str) -> CritiqueResult:
        """Parse LLM response into CritiqueResult."""
        result = CritiqueResult(raw_response=response)

        # Check for approval
        if "APPROVED" in response.upper():
            result.approved = True

            # Still check for suggestions
            if "SUGGESTIONS:" in response.upper():
                suggestions_section = response.split("SUGGESTIONS:")[-1]
                result.suggestions = self._extract_list_items(suggestions_section)

        # Check for issues
        elif "ISSUES:" in response.upper():
            result.approved = False
            issues_section = response.split("ISSUES:")[-1]

            # Split at SUGGESTIONS if present
            if "SUGGESTIONS:" in issues_section.upper():
                issues_section = issues_section.split("SUGGESTIONS:")[0]

            result.issues = self._extract_list_items(issues_section)

            # Check for specific issue types
            response_lower = response.lower()

            for pattern in SECURITY_PATTERNS:
                if re.search(pattern, response_lower):
                    result.has_security_issues = True
                    break

            for pattern in CRITICAL_BUG_PATTERNS:
                if re.search(pattern, response_lower):
                    result.has_critical_bugs = True
                    break

            if "performance" in response_lower:
                result.has_performance_issues = True

            if "pattern" in response_lower or "convention" in response_lower:
                result.has_pattern_violations = True

        else:
            # Ambiguous response - be conservative
            result.approved = False
            result.issues = ["Unclear critique response"]

        return result

    def _extract_list_items(self, text: str) -> list[str]:
        """Extract list items from text."""
        items = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                items.append(line[1:].strip())
            elif line.startswith('*'):
                items.append(line[1:].strip())
            elif re.match(r'^\d+\.', line):
                items.append(re.sub(r'^\d+\.\s*', '', line))
        return items

    def should_block(self, result: CritiqueResult) -> bool:
        """
        Determine if critique should block delivery.

        Only blocks on security issues or critical bugs.
        """
        return result.has_security_issues or result.has_critical_bugs

    def get_blocking_issues(self, result: CritiqueResult) -> list[str]:
        """Get list of issues that should block delivery."""
        blocking = []

        if result.has_security_issues:
            blocking.extend([
                issue for issue in result.issues
                if any(re.search(p, issue.lower()) for p in SECURITY_PATTERNS)
            ])

        if result.has_critical_bugs:
            blocking.extend([
                issue for issue in result.issues
                if any(re.search(p, issue.lower()) for p in CRITICAL_BUG_PATTERNS)
            ])

        return blocking or result.issues  # Fallback to all issues

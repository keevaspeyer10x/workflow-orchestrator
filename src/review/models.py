"""
Model Adapters for Multi-Model Review

Provides unified interface to multiple AI providers for code review.
Uses litellm as the backend for provider abstraction.
"""

import os
import json
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from .schema import (
    ModelSpec,
    ModelReview,
    ReviewIssue,
    ReviewFocus,
    ChangeContext,
    IssueSeverity,
    IssueCategory,
    ConfidenceLevel,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Review Prompt Template
# ============================================================================

REVIEW_PROMPT_TEMPLATE = """You are a senior software architect performing a code review.
Your focus areas: {focus_areas}

## Change Context
Description: {description}
Files changed: {files_changed}
Branch: {branch_name} -> {base_branch}

## Diff
```diff
{diff_content}
```

## Instructions

Analyze this change critically. You are encouraged to find issues - it's better to flag a potential problem than to miss a real one.

For each issue found, provide:
1. **Severity**: critical (must fix), high (should fix), medium (consider), low (nice-to-have), info
2. **Category**: security, bug, design, performance, maintainability, edge_case, missing, suggestion
3. **Title**: Brief description (1 line)
4. **Description**: Detailed explanation
5. **File/Line**: Where the issue is (if applicable)
6. **Recommendation**: How to fix it

Also note any good design choices that should be kept.

## Output Format

Return a JSON object with this structure:
```json
{{
  "issues": [
    {{
      "severity": "high",
      "category": "security",
      "title": "SQL injection vulnerability",
      "description": "The query uses string interpolation...",
      "file_path": "src/db.py",
      "line_start": 42,
      "recommendation": "Use parameterized queries instead"
    }}
  ],
  "validated_choices": [
    "Good use of dependency injection in AuthService",
    "Proper error handling in payment flow"
  ],
  "summary": "Overall assessment of the change..."
}}
```

Be thorough. Focus especially on: {focus_areas}
"""


# ============================================================================
# Base Reviewer Class
# ============================================================================

class BaseReviewer(ABC):
    """Base class for model-specific reviewers."""

    def __init__(self, model_spec: ModelSpec):
        self.model_spec = model_spec
        self.provider = model_spec.provider
        self.model_id = model_spec.model_id

    @abstractmethod
    async def review(self, context: ChangeContext) -> ModelReview:
        """Perform review and return results."""
        pass

    def _build_prompt(self, context: ChangeContext) -> str:
        """Build the review prompt."""
        focus_str = ", ".join(f.value for f in self.model_spec.focus) if self.model_spec.focus else "general code quality"

        return REVIEW_PROMPT_TEMPLATE.format(
            focus_areas=focus_str,
            description=context.description or "No description provided",
            files_changed=", ".join(context.files_changed[:20]),  # Limit for prompt size
            branch_name=context.branch_name or "feature",
            base_branch=context.base_branch,
            diff_content=context.diff_content[:50000],  # Limit diff size
        )

    def _parse_response(self, response_text: str, model_id: str) -> tuple[list[ReviewIssue], list[str], str]:
        """Parse model response into structured data."""
        issues = []
        validated = []
        summary = ""

        try:
            # Try to extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)

                # Parse issues
                for issue_data in data.get("issues", []):
                    try:
                        issues.append(ReviewIssue(
                            severity=IssueSeverity(issue_data.get("severity", "medium")),
                            category=IssueCategory(issue_data.get("category", "suggestion")),
                            title=issue_data.get("title", "Untitled issue"),
                            description=issue_data.get("description", ""),
                            file_path=issue_data.get("file_path"),
                            line_start=issue_data.get("line_start"),
                            line_end=issue_data.get("line_end"),
                            recommendation=issue_data.get("recommendation"),
                            code_suggestion=issue_data.get("code_suggestion"),
                            confidence=ConfidenceLevel.MEDIUM,
                            found_by=[model_id],
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to parse issue: {e}")

                validated = data.get("validated_choices", [])
                summary = data.get("summary", "")

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response from {model_id}: {e}")
            # Try to extract summary from plain text
            summary = response_text[:500] if response_text else "Review completed but parsing failed"

        return issues, validated, summary


# ============================================================================
# LiteLLM-based Reviewer (supports all providers)
# ============================================================================

class LiteLLMReviewer(BaseReviewer):
    """
    Reviewer using litellm for provider abstraction.

    Supports:
    - OpenAI (gpt-4, gpt-5.2-max, etc.)
    - Anthropic (claude-3, claude-opus-4, etc.)
    - Google (gemini-pro, gemini-2.5-pro, etc.)
    - xAI (grok-4.1, etc.)
    - Codex (via OpenAI)
    - OpenRouter (any model)
    """

    # Model ID mappings for litellm
    MODEL_MAPPINGS = {
        # OpenAI
        "openai/gpt-5.2-max": "gpt-5.2-max",
        "openai/gpt-4-turbo": "gpt-4-turbo",
        "openai/o3": "o3",
        "openai/codex": "gpt-4-turbo",  # Codex deprecated, use GPT-4

        # Google
        "google/gemini-2.5-pro": "gemini/gemini-2.5-pro",
        "google/gemini-pro": "gemini/gemini-pro",

        # xAI
        "xai/grok-4.1": "xai/grok-4-1-fast-reasoning",
        "xai/grok-beta": "xai/grok-4-1-fast-reasoning",  # Deprecated, redirect

        # Anthropic (self-review)
        "anthropic/claude-opus-4.5": "claude-opus-4-5-20251101",
        "anthropic/claude-sonnet-4": "claude-sonnet-4-20250514",

        # OpenRouter (prefix with openrouter/)
        "openrouter/anthropic/claude-3-opus": "openrouter/anthropic/claude-3-opus",
    }

    async def review(self, context: ChangeContext) -> ModelReview:
        """Perform review using litellm."""
        import litellm

        review = ModelReview(
            model_id=self.model_id,
            model_provider=self.provider,
            focus=self.model_spec.focus,
            started_at=datetime.now(timezone.utc),
        )

        start_time = time.time()

        try:
            # Get litellm model ID
            full_id = self.model_spec.full_id
            litellm_model = self.MODEL_MAPPINGS.get(full_id, self.model_id)

            # Build prompt
            prompt = self._build_prompt(context)

            # Call model
            response = await litellm.acompletion(
                model=litellm_model,
                messages=[
                    {"role": "system", "content": "You are a senior software architect performing thorough code reviews. Return your analysis as JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.model_spec.temperature,
                max_tokens=self.model_spec.max_tokens,
            )

            # Extract response
            response_text = response.choices[0].message.content

            # Parse response
            issues, validated, summary = self._parse_response(response_text, full_id)

            review.issues = issues
            review.validated_choices = validated
            review.summary = summary
            review.tokens_used = response.usage.total_tokens if response.usage else 0

        except Exception as e:
            logger.error(f"Review failed for {self.model_spec.full_id}: {e}")
            review.error = str(e)

        finally:
            review.completed_at = datetime.now(timezone.utc)
            review.latency_ms = int((time.time() - start_time) * 1000)

        return review


# ============================================================================
# Self-Reviewer (Claude reviewing its own work)
# ============================================================================

class SelfReviewer(BaseReviewer):
    """
    Self-review by Claude.

    This is a special case where Claude reviews code it may have written.
    Focuses on edge cases, UX, and completeness since Claude has full context.
    """

    def __init__(self):
        super().__init__(ModelSpec(
            provider="anthropic",
            model_id="claude-self",
            focus=[ReviewFocus.EDGE_CASES, ReviewFocus.UX, ReviewFocus.COMPLETENESS],
        ))

    async def review(self, context: ChangeContext) -> ModelReview:
        """
        Perform self-review.

        Note: In practice, this is invoked by the orchestrator which
        asks Claude to review the changes before sending to external models.
        The actual review happens in the conversation context.
        """
        review = ModelReview(
            model_id="claude-self",
            model_provider="anthropic",
            focus=self.model_spec.focus,
            started_at=datetime.now(timezone.utc),
        )

        # Self-review is typically done inline in conversation
        # This method is a placeholder for when we want to formalize it
        review.summary = "Self-review performed inline"
        review.completed_at = datetime.now(timezone.utc)
        review.latency_ms = 0

        return review


# ============================================================================
# Reviewer Factory
# ============================================================================

class ReviewerFactory:
    """Factory for creating appropriate reviewers."""

    @staticmethod
    def create(model_spec: ModelSpec) -> BaseReviewer:
        """Create a reviewer for the given model spec."""
        if model_spec.model_id == "claude-self":
            return SelfReviewer()
        else:
            return LiteLLMReviewer(model_spec)

    @staticmethod
    def create_from_id(model_id: str, focus: Optional[list[ReviewFocus]] = None) -> BaseReviewer:
        """Create a reviewer from a model ID string (e.g., 'openai/gpt-5.2-max')."""
        parts = model_id.split("/", 1)
        if len(parts) == 2:
            provider, model = parts
        else:
            provider = "openai"  # Default
            model = parts[0]

        spec = ModelSpec(
            provider=provider,
            model_id=model,
            focus=focus or [],
        )
        return ReviewerFactory.create(spec)

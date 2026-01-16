"""Pattern Generator - Phase 2 Pattern Memory & Lookup.

Uses LLM (Claude Sonnet) to generalize specific fixes into reusable patterns.
"""

import json
import logging
from typing import Optional, TYPE_CHECKING

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore

if TYPE_CHECKING:
    from .models import ErrorEvent


logger = logging.getLogger(__name__)


class PatternGenerator:
    """Generate reusable patterns from error resolutions using LLM.

    This generator uses Claude Sonnet to:
    - Analyze error + fix pairs
    - Generalize specific fixes into reusable patterns
    - Extract patterns from conversation transcripts
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
    ):
        """Initialize the pattern generator.

        Args:
            api_key: Anthropic API key. If None, generator is unavailable.
            model: Model to use. Defaults to Claude Sonnet.
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self._client = None

        if self.available and anthropic is not None:
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)

    @property
    def available(self) -> bool:
        """Check if the generator is available.

        Returns:
            True if API key is set and anthropic module is available
        """
        return bool(self.api_key) and anthropic is not None

    async def generate_from_diff(
        self,
        error: "ErrorEvent",
        fix_diff: str,
        context: Optional[str] = None,
    ) -> Optional[dict]:
        """Generate a reusable pattern from an error and its fix.

        Args:
            error: The error that was fixed
            fix_diff: The diff that fixed the error
            context: Optional additional context (e.g., file content)

        Returns:
            Pattern dict with fingerprint_pattern, safety_category, action
            or None if generation fails
        """
        if not self.available or not self._client:
            return None

        prompt = self._build_generation_prompt(error, fix_diff, context)

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text
            return self._parse_pattern_response(text)
        except Exception as e:
            logger.warning(f"Pattern generation failed: {e}")
            return None

    async def extract_from_transcript(
        self,
        transcript: str,
        errors: list["ErrorEvent"],
    ) -> list[dict]:
        """Find error→fix sequences in a conversation transcript.

        Args:
            transcript: The conversation history
            errors: Known errors from the session

        Returns:
            List of dicts with error_index, fix_description, suggested_pattern
        """
        if not self.available or not self._client:
            return []

        prompt = self._build_extraction_prompt(transcript, errors)

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text
            return self._parse_extraction_response(text)
        except Exception as e:
            logger.warning(f"Transcript extraction failed: {e}")
            return []

    def _build_generation_prompt(
        self,
        error: "ErrorEvent",
        fix_diff: str,
        context: Optional[str],
    ) -> str:
        """Build the prompt for pattern generation."""
        prompt = f"""Analyze this error and fix to create a reusable pattern.

ERROR:
Type: {error.error_type or 'Unknown'}
Description: {error.description}
File: {error.file_path or 'Unknown'}

FIX DIFF:
{fix_diff}
"""
        if context:
            prompt += f"""
CONTEXT:
{context}
"""

        prompt += """
Create a generalized fix pattern that could apply to similar errors.
Return JSON with:
- fingerprint_pattern: regex to match similar errors
- safety_category: "safe", "moderate", or "risky"
- action: the fix action object with action_type and relevant fields
- confidence: 0.0-1.0 how confident this pattern will work for similar errors

Respond ONLY with the JSON object, no other text."""

        return prompt

    def _build_extraction_prompt(
        self,
        transcript: str,
        errors: list["ErrorEvent"],
    ) -> str:
        """Build the prompt for transcript extraction."""
        error_list = "\n".join(
            f"{i}. {e.description[:100]}"
            for i, e in enumerate(errors)
        )

        return f"""Analyze this transcript to find error resolutions.

KNOWN ERRORS:
{error_list}

TRANSCRIPT:
{transcript[:4000]}

For each error that was fixed in the transcript, return JSON array with:
- error_index: which error was fixed (0-indexed from KNOWN ERRORS)
- fix_description: what was done to fix it
- suggested_pattern: if the fix is generalizable, include a pattern object

Respond ONLY with the JSON array, no other text.
If no errors were fixed, respond with an empty array: []"""

    def _parse_pattern_response(self, text: str) -> Optional[dict]:
        """Parse the LLM response into a pattern dict."""
        try:
            # Try to extract JSON from the response
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse pattern response: {e}")
            return None

    def _parse_extraction_response(self, text: str) -> list[dict]:
        """Parse the LLM response into a list of extractions."""
        try:
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction response: {e}")
            return []

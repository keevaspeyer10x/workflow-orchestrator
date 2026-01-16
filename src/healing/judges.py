"""Multi-model judging system for fix validation.

This module provides multi-model consensus for approving fixes.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .config import get_config
from .safety import SafetyCategory

if TYPE_CHECKING:
    from .models import ErrorEvent, FixAction


logger = logging.getLogger(__name__)


class JudgeModel(Enum):
    """Available judge models."""

    CLAUDE_OPUS = "claude-opus-4-5"
    GEMINI_PRO = "gemini-3-pro"
    GPT_5 = "gpt-5.2"
    GROK = "grok-4.1"


@dataclass
class JudgeVote:
    """A single judge's vote on a fix."""

    model: str
    approved: bool
    confidence: float
    reasoning: str
    issues: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class JudgeResult:
    """Combined result from all judges."""

    approved: bool
    votes: List[JudgeVote]
    consensus_score: float  # 0.0 to 1.0
    required_votes: int
    received_votes: int

    @property
    def approval_count(self) -> int:
        """Number of approvals."""
        return sum(1 for v in self.votes if v.approved)

    @property
    def rejection_count(self) -> int:
        """Number of rejections."""
        return sum(1 for v in self.votes if not v.approved)


@dataclass
class SuggestedFix:
    """A suggested fix for an error."""

    fix_id: str
    title: str
    action: "FixAction"
    safety_category: SafetyCategory
    pattern: Optional[Dict] = None
    diff: Optional[str] = None
    affected_files: List[str] = field(default_factory=list)
    lines_changed: int = 0


class MultiModelJudge:
    """Multi-model validation for fixes.

    This class coordinates multiple AI models to vote on whether
    a proposed fix should be applied. The number of judges used
    depends on the safety category:
    - SAFE: 1 judge
    - MODERATE: 2 judges
    - RISKY: 3 judges (majority required)
    """

    DEFAULT_MODELS = [
        JudgeModel.CLAUDE_OPUS,
        JudgeModel.GEMINI_PRO,
        JudgeModel.GPT_5,
        JudgeModel.GROK,
    ]

    def __init__(
        self,
        models: Optional[List[JudgeModel]] = None,
        api_keys: Optional[Dict[str, str]] = None,
    ):
        """Initialize the multi-model judge.

        Args:
            models: List of models to use (default: all available)
            api_keys: Dict mapping model names to API keys
        """
        self.models = models or self.DEFAULT_MODELS
        self._api_keys = api_keys or {}
        self._config = None

    @property
    def config(self):
        """Get configuration (lazy load)."""
        if self._config is None:
            self._config = get_config()
        return self._config

    def get_api_key(self, model: JudgeModel) -> Optional[str]:
        """Get API key for a model.

        Checks:
        1. Explicitly provided keys
        2. Environment variables
        """
        model_name = model.value

        # Check explicit keys
        if model_name in self._api_keys:
            return self._api_keys[model_name]

        # Check environment variables
        env_keys = {
            JudgeModel.CLAUDE_OPUS: "ANTHROPIC_API_KEY",
            JudgeModel.GEMINI_PRO: "GEMINI_API_KEY",
            JudgeModel.GPT_5: "OPENAI_API_KEY",
            JudgeModel.GROK: "XAI_API_KEY",
        }

        env_var = env_keys.get(model)
        if env_var:
            return os.environ.get(env_var)

        return None

    async def judge(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
        safety_category: SafetyCategory,
    ) -> JudgeResult:
        """Get votes from multiple models based on safety category.

        Args:
            fix: The suggested fix to evaluate
            error: The original error
            safety_category: The safety level of the fix

        Returns:
            JudgeResult with all votes and consensus
        """
        # Determine number of judges needed, clamped to available models
        judge_count = self._get_judge_count(safety_category)
        actual_judge_count = min(judge_count, len(self.models))
        selected_models = self.models[:actual_judge_count]

        # Create judge tasks with timeout
        timeout = self.config.judge_timeout_seconds

        async def judge_with_model(model: JudgeModel) -> JudgeVote:
            """Wrapper that preserves model info for error handling."""
            try:
                return await asyncio.wait_for(
                    self._get_vote(model, fix, error),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return JudgeVote(
                    model=model.value,
                    approved=False,
                    confidence=0.0,
                    reasoning="Judge timed out",
                    issues=["timeout"],
                    error="Timeout",
                )
            except Exception as e:
                logger.warning(f"Judge {model.value} failed: {e}")
                return JudgeVote(
                    model=model.value,
                    approved=False,
                    confidence=0.0,
                    reasoning=f"Judge error: {str(e)}",
                    issues=["error"],
                    error=str(e),
                )

        # Gather votes (allow partial failures)
        votes = await asyncio.gather(
            *[judge_with_model(model) for model in selected_models]
        )

        # Calculate consensus
        valid_votes = [v for v in votes if v.error is None]
        if valid_votes:
            approvals = sum(1 for v in valid_votes if v.approved)
            consensus = approvals / len(valid_votes)
        else:
            consensus = 0.0

        # Determine approval (majority required, based on actual judges)
        threshold = (actual_judge_count // 2) + 1
        approval_count = sum(1 for v in votes if v.approved)
        approved = approval_count >= threshold

        return JudgeResult(
            approved=approved,
            votes=list(votes),
            consensus_score=consensus,
            required_votes=threshold,
            received_votes=len(votes),
        )

    def _get_judge_count(self, safety: SafetyCategory) -> int:
        """Get number of judges for safety category."""
        if safety == SafetyCategory.SAFE:
            return 1
        elif safety == SafetyCategory.MODERATE:
            return 2
        else:  # RISKY
            return 3

    async def _get_vote(
        self,
        model: JudgeModel,
        fix: SuggestedFix,
        error: "ErrorEvent",
    ) -> JudgeVote:
        """Get a single model's vote.

        Args:
            model: The model to query
            fix: The suggested fix
            error: The original error

        Returns:
            JudgeVote with the model's decision
        """
        api_key = self.get_api_key(model)
        if not api_key:
            return JudgeVote(
                model=model.value,
                approved=False,
                confidence=0.0,
                reasoning="No API key available",
                issues=["missing_key"],
                error="Missing API key",
            )

        prompt = self._build_judge_prompt(fix, error)

        try:
            if model == JudgeModel.CLAUDE_OPUS:
                response = await self._call_anthropic(api_key, prompt)
            elif model == JudgeModel.GEMINI_PRO:
                response = await self._call_google(api_key, prompt)
            elif model == JudgeModel.GPT_5:
                response = await self._call_openai(api_key, prompt)
            elif model == JudgeModel.GROK:
                response = await self._call_xai(api_key, prompt)
            else:
                raise ValueError(f"Unknown model: {model}")

            return self._parse_vote(model.value, response)

        except Exception as e:
            logger.error(f"Error calling {model.value}: {e}")
            return JudgeVote(
                model=model.value,
                approved=False,
                confidence=0.0,
                reasoning=f"API call failed: {str(e)}",
                issues=["api_error"],
                error=str(e),
            )

    def _build_judge_prompt(
        self,
        fix: SuggestedFix,
        error: "ErrorEvent",
    ) -> str:
        """Build the judge prompt."""
        fix_content = fix.diff or str(fix.action.to_dict() if fix.action else "No action")

        return f"""You are reviewing an automated code fix. Evaluate whether this fix is safe to apply.

ERROR:
{error.description}

ERROR TYPE: {error.error_type or 'Unknown'}
FILE: {error.file_path or 'Unknown'}

PROPOSED FIX:
{fix_content}

SAFETY CATEGORY: {fix.safety_category.value}
AFFECTED FILES: {', '.join(fix.affected_files) if fix.affected_files else 'Unknown'}
LINES CHANGED: {fix.lines_changed}

Evaluate:
1. Does this fix address the actual error?
2. Could this fix introduce new bugs?
3. Are there any security concerns?
4. Is the fix minimal and focused?

Respond with JSON only:
{{
    "approved": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explanation",
    "issues": ["list", "of", "concerns"]
}}
"""

    def _parse_vote(self, model: str, response: str) -> JudgeVote:
        """Parse a model's response into a JudgeVote."""
        try:
            # Try to extract JSON from response
            json_match = response.strip()
            if "```json" in json_match:
                json_match = json_match.split("```json")[1].split("```")[0]
            elif "```" in json_match:
                json_match = json_match.split("```")[1].split("```")[0]

            data = json.loads(json_match)

            return JudgeVote(
                model=model,
                approved=bool(data.get("approved", False)),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=str(data.get("reasoning", "No reasoning provided")),
                issues=list(data.get("issues", [])),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse judge response from {model}: {e}")
            return JudgeVote(
                model=model,
                approved=False,
                confidence=0.0,
                reasoning=f"Failed to parse response: {response[:200]}",
                issues=["parse_error"],
                error=str(e),
            )

    async def _call_anthropic(self, api_key: str, prompt: str) -> str:
        """Call Anthropic API."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=api_key)
            message = await client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except ImportError:
            raise RuntimeError("anthropic package not installed")

    async def _call_google(self, api_key: str, prompt: str) -> str:
        """Call Google Gemini API."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3-pro")
            response = await asyncio.to_thread(
                model.generate_content, prompt
            )
            return response.text
        except ImportError:
            raise RuntimeError("google-generativeai package not installed")

    async def _call_openai(self, api_key: str, prompt: str) -> str:
        """Call OpenAI API."""
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-5.2",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except ImportError:
            raise RuntimeError("openai package not installed")

    async def _call_xai(self, api_key: str, prompt: str) -> str:
        """Call xAI/Grok API."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-4.1",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 1024,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except ImportError:
            raise RuntimeError("httpx package not installed")

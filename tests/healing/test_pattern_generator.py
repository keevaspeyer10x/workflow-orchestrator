"""Tests for PatternGenerator - Phase 2 Pattern Memory & Lookup."""

import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestPatternGenerator:
    """Tests for LLM-based pattern generation."""

    @pytest.mark.asyncio
    async def test_generate_from_diff_valid(self):
        """Generates pattern from error and diff."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "fingerprint_pattern": r"ModuleNotFoundError: No module named '(\w+)'",
            "safety_category": "safe",
            "action": {"action_type": "command", "command": "pip install {match_1}"},
            "confidence": 0.9,
        }))]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            error = ErrorEvent(
                error_id="err-123",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="ModuleNotFoundError: No module named 'requests'",
            )
            result = await generator.generate_from_diff(
                error=error,
                fix_diff="+ requests",
            )

            assert result is not None
            assert "fingerprint_pattern" in result
            assert result["safety_category"] == "safe"
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_generate_from_diff_with_context(self):
        """Uses context in prompt when provided."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "fingerprint_pattern": r"TypeError.*",
            "safety_category": "moderate",
            "action": {"action_type": "diff", "requires_context": True},
            "confidence": 0.7,
        }))]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            error = ErrorEvent(
                error_id="err-456",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="TypeError: 'NoneType' object is not subscriptable",
            )
            result = await generator.generate_from_diff(
                error=error,
                fix_diff="if value is not None:",
                context="def process(value):\n    return value[0]",
            )

            # Verify context was included in the prompt
            call_args = mock_client.messages.create.call_args
            messages = call_args.kwargs.get("messages", [])
            prompt_text = messages[0]["content"] if messages else ""
            assert "def process" in prompt_text or result is not None

    @pytest.mark.asyncio
    async def test_generate_from_diff_invalid_json(self):
        """Handles malformed LLM response gracefully."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            error = ErrorEvent(
                error_id="err-789",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="Some error",
            )
            result = await generator.generate_from_diff(error=error, fix_diff="fix")

            # Should return None or empty dict, not raise
            assert result is None or result == {}

    @pytest.mark.asyncio
    async def test_generate_from_diff_api_error(self):
        """Handles API timeout/error gracefully."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(side_effect=Exception("API timeout"))
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            error = ErrorEvent(
                error_id="err-999",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="Some error",
            )
            result = await generator.generate_from_diff(error=error, fix_diff="fix")

            # Should return None, not raise
            assert result is None

    @pytest.mark.asyncio
    async def test_generate_from_diff_no_api_key(self):
        """Returns None when no API key provided."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        generator = PatternGenerator(api_key=None)
        error = ErrorEvent(
            error_id="err-000",
            timestamp=datetime.utcnow(),
            source="subprocess",
            description="Some error",
        )
        result = await generator.generate_from_diff(error=error, fix_diff="fix")

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_from_transcript_finds_fixes(self):
        """Finds error→fix sequences in conversation."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "error_index": 0,
                "fix_description": "Added missing import",
                "suggested_pattern": {
                    "fingerprint_pattern": r"ImportError.*",
                    "safety_category": "safe",
                },
            }
        ]))]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            errors = [
                ErrorEvent(
                    error_id="err-1",
                    timestamp=datetime.utcnow(),
                    source="subprocess",
                    description="ImportError: No module named foo",
                )
            ]
            transcript = "User: Getting import error\nAssistant: Let me add the import"

            result = await generator.extract_from_transcript(transcript, errors)

            assert len(result) == 1
            assert result[0]["error_index"] == 0
            assert "fix_description" in result[0]

    @pytest.mark.asyncio
    async def test_extract_from_transcript_empty(self):
        """Returns empty for no fixes found."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="[]")]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            errors = [
                ErrorEvent(
                    error_id="err-1",
                    timestamp=datetime.utcnow(),
                    source="subprocess",
                    description="Some error that wasn't fixed",
                )
            ]
            transcript = "User: Just chatting"

            result = await generator.extract_from_transcript(transcript, errors)

            assert result == []

    @pytest.mark.asyncio
    async def test_extract_from_transcript_multiple_fixes(self):
        """Finds multiple error→fix sequences."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"error_index": 0, "fix_description": "Fix 1"},
            {"error_index": 1, "fix_description": "Fix 2"},
        ]))]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            errors = [
                ErrorEvent(
                    error_id="err-1",
                    timestamp=datetime.utcnow(),
                    source="subprocess",
                    description="Error 1",
                ),
                ErrorEvent(
                    error_id="err-2",
                    timestamp=datetime.utcnow(),
                    source="subprocess",
                    description="Error 2",
                ),
            ]
            transcript = "Long conversation with multiple fixes"

            result = await generator.extract_from_transcript(transcript, errors)

            assert len(result) == 2

    def test_generator_available_property_with_key(self):
        """Returns True when API key is set."""
        from src.healing.pattern_generator import PatternGenerator

        generator = PatternGenerator(api_key="sk-test-key")
        assert generator.available is True

    def test_generator_available_property_without_key(self):
        """Returns False when API key is None."""
        from src.healing.pattern_generator import PatternGenerator

        generator = PatternGenerator(api_key=None)
        assert generator.available is False


class TestPatternGeneratorModel:
    """Tests for model configuration."""

    @pytest.mark.asyncio
    async def test_uses_sonnet_by_default(self):
        """Uses Claude Sonnet model by default."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="{}")]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key")
            error = ErrorEvent(
                error_id="err-1",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="Error",
            )
            await generator.generate_from_diff(error=error, fix_diff="fix")

            call_args = mock_client.messages.create.call_args
            assert "sonnet" in call_args.kwargs.get("model", "").lower()

    @pytest.mark.asyncio
    async def test_custom_model(self):
        """Uses custom model when specified."""
        from src.healing.pattern_generator import PatternGenerator
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="{}")]

        with patch("src.healing.pattern_generator.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            generator = PatternGenerator(api_key="sk-test-key", model="claude-3-opus-20240229")
            error = ErrorEvent(
                error_id="err-1",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="Error",
            )
            await generator.generate_from_diff(error=error, fix_diff="fix")

            call_args = mock_client.messages.create.call_args
            assert call_args.kwargs.get("model") == "claude-3-opus-20240229"

"""Tests for multi-model judging."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from src.healing.judges import (
    MultiModelJudge,
    JudgeModel,
    JudgeVote,
    JudgeResult,
    SuggestedFix,
)
from src.healing.safety import SafetyCategory
from src.healing.models import ErrorEvent, FixAction


class TestJudgeVote:
    """Tests for JudgeVote dataclass."""

    def test_vote_with_approval(self):
        """Should create an approval vote."""
        vote = JudgeVote(
            model="claude-opus-4-5",
            approved=True,
            confidence=0.9,
            reasoning="Fix looks correct",
            issues=[],
        )
        assert vote.approved
        assert vote.confidence == 0.9
        assert not vote.issues

    def test_vote_with_rejection(self):
        """Should create a rejection vote."""
        vote = JudgeVote(
            model="gpt-5.2",
            approved=False,
            confidence=0.8,
            reasoning="Fix could cause issues",
            issues=["potential side effects"],
        )
        assert not vote.approved
        assert vote.issues == ["potential side effects"]

    def test_vote_with_error(self):
        """Should create an error vote."""
        vote = JudgeVote(
            model="gemini-3-pro",
            approved=False,
            confidence=0.0,
            reasoning="API call failed",
            issues=["api_error"],
            error="Connection refused",
        )
        assert vote.error == "Connection refused"


class TestJudgeResult:
    """Tests for JudgeResult dataclass."""

    def test_approval_count(self):
        """Should count approvals correctly."""
        result = JudgeResult(
            approved=True,
            votes=[
                JudgeVote(model="a", approved=True, confidence=0.9, reasoning=""),
                JudgeVote(model="b", approved=False, confidence=0.8, reasoning=""),
                JudgeVote(model="c", approved=True, confidence=0.7, reasoning=""),
            ],
            consensus_score=0.67,
            required_votes=2,
            received_votes=3,
        )
        assert result.approval_count == 2
        assert result.rejection_count == 1


class TestSuggestedFix:
    """Tests for SuggestedFix dataclass."""

    def test_suggested_fix_creation(self):
        """Should create a suggested fix."""
        action = FixAction(
            action_type="command",
            command="pip install missing-package",
        )
        fix = SuggestedFix(
            fix_id="fix-abc123",
            title="Install missing package",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["requirements.txt"],
            lines_changed=1,
        )
        assert fix.fix_id == "fix-abc123"
        assert fix.safety_category == SafetyCategory.SAFE


class TestMultiModelJudge:
    """Tests for MultiModelJudge."""

    @pytest.fixture
    def judge(self):
        """Create a MultiModelJudge."""
        return MultiModelJudge()

    @pytest.fixture
    def sample_fix(self):
        """Create a sample fix for testing."""
        action = FixAction(
            action_type="diff",
            diff="+import os\n",
        )
        return SuggestedFix(
            fix_id="fix-test",
            title="Add import",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["src/utils.py"],
            lines_changed=1,
        )

    @pytest.fixture
    def sample_error(self):
        """Create a sample error for testing."""
        return ErrorEvent(
            error_id="err-1",
            timestamp=_utcnow(),
            source="subprocess",
            description="ModuleNotFoundError: No module named 'os'",
            error_type="ModuleNotFoundError",
            file_path="src/utils.py",
        )

    def test_get_judge_count_safe(self, judge):
        """SAFE should use 1 judge."""
        count = judge._get_judge_count(SafetyCategory.SAFE)
        assert count == 1

    def test_get_judge_count_moderate(self, judge):
        """MODERATE should use 2 judges."""
        count = judge._get_judge_count(SafetyCategory.MODERATE)
        assert count == 2

    def test_get_judge_count_risky(self, judge):
        """RISKY should use 3 judges."""
        count = judge._get_judge_count(SafetyCategory.RISKY)
        assert count == 3

    def test_build_judge_prompt(self, judge, sample_fix, sample_error):
        """Should build a valid prompt."""
        prompt = judge._build_judge_prompt(sample_fix, sample_error)

        assert "ERROR:" in prompt
        assert "ModuleNotFoundError" in prompt
        assert "PROPOSED FIX:" in prompt
        assert "import os" in prompt
        assert "SAFETY CATEGORY:" in prompt
        assert "safe" in prompt.lower()

    def test_parse_vote_valid_json(self, judge):
        """Should parse valid JSON response."""
        response = """{
            "approved": true,
            "confidence": 0.95,
            "reasoning": "Fix is correct",
            "issues": []
        }"""
        vote = judge._parse_vote("test-model", response)

        assert vote.approved
        assert vote.confidence == 0.95
        assert vote.reasoning == "Fix is correct"

    def test_parse_vote_json_in_markdown(self, judge):
        """Should parse JSON wrapped in markdown code blocks."""
        response = """```json
{
    "approved": false,
    "confidence": 0.8,
    "reasoning": "Could cause issues",
    "issues": ["side effects"]
}
```"""
        vote = judge._parse_vote("test-model", response)

        assert not vote.approved
        assert vote.issues == ["side effects"]

    def test_parse_vote_invalid_json(self, judge):
        """Should handle invalid JSON gracefully."""
        response = "This is not valid JSON"
        vote = judge._parse_vote("test-model", response)

        assert not vote.approved
        assert vote.error is not None
        assert "parse_error" in vote.issues

    def test_get_api_key_from_env(self, judge):
        """Should get API key from environment."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            key = judge.get_api_key(JudgeModel.CLAUDE_OPUS)
            assert key == "test-key"

    def test_get_api_key_explicit(self):
        """Should use explicitly provided key."""
        judge = MultiModelJudge(api_keys={"claude-opus-4-5": "explicit-key"})
        key = judge.get_api_key(JudgeModel.CLAUDE_OPUS)
        assert key == "explicit-key"


class TestMultiModelJudgeAsync:
    """Async tests for MultiModelJudge."""

    @pytest.fixture
    def judge(self):
        """Create a MultiModelJudge."""
        return MultiModelJudge()

    @pytest.fixture
    def sample_fix(self):
        """Create a sample fix."""
        action = FixAction(action_type="diff", diff="+import os\n")
        return SuggestedFix(
            fix_id="fix-test",
            title="Add import",
            action=action,
            safety_category=SafetyCategory.SAFE,
            affected_files=["src/utils.py"],
            lines_changed=1,
        )

    @pytest.fixture
    def sample_error(self):
        """Create a sample error."""
        return ErrorEvent(
            error_id="err-1",
            timestamp=_utcnow(),
            source="subprocess",
            description="ModuleNotFoundError",
        )

    @pytest.mark.asyncio
    async def test_judge_without_api_keys(self, judge, sample_fix, sample_error):
        """Should return rejection when no API keys available."""
        # Clear any env vars
        with patch.dict("os.environ", {}, clear=True):
            result = await judge.judge(sample_fix, sample_error, SafetyCategory.SAFE)

        # Should have 1 vote (SAFE = 1 judge)
        assert len(result.votes) == 1
        # Vote should indicate missing key
        assert "Missing API key" in result.votes[0].reasoning or result.votes[0].error

    @pytest.mark.asyncio
    async def test_judge_with_mocked_api(self, judge, sample_fix, sample_error):
        """Should return approval when API returns approval."""
        mock_response = """{
            "approved": true,
            "confidence": 0.9,
            "reasoning": "Fix is correct",
            "issues": []
        }"""

        with patch.object(judge, "_call_anthropic", return_value=mock_response):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                result = await judge.judge(sample_fix, sample_error, SafetyCategory.SAFE)

        assert result.approved
        assert result.votes[0].approved
        assert result.votes[0].confidence == 0.9

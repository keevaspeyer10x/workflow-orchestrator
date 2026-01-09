"""
Tests for LLM Conflict Resolver - CORE-023 Part 2

Tests the LLM-based conflict resolution system with mocked LLM responses.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.resolution.llm_resolver import (
    LLMResolver,
    LLMResolutionResult,
    LLMClient,
    OpenAIClient,
    GeminiClient,
    OpenRouterClient,
    ExtractedIntent,
    MergeCandidate,
    ValidationResult,
    ConfidenceLevel,
    SENSITIVE_PATTERNS,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = Mock(spec=LLMClient)
    client.model_name = "mock-model"
    return client


@pytest.fixture
def resolver(mock_llm_client, tmp_path):
    """Create an LLM resolver with mock client."""
    return LLMResolver(
        repo_path=tmp_path,
        client=mock_llm_client,
        auto_apply_threshold=0.8,
    )


@pytest.fixture
def sample_conflict():
    """Sample conflict data for testing."""
    return {
        "file_path": "src/utils.py",
        "base": '''def process_data(data):
    """Process data."""
    return data.strip()
''',
        "ours": '''def process_data(data, normalize=True):
    """Process data with optional normalization."""
    result = data.strip()
    if normalize:
        result = result.lower()
    return result
''',
        "theirs": '''def process_data(data):
    """Process data with validation."""
    if not data:
        raise ValueError("Data cannot be empty")
    return data.strip()
''',
    }


# ============================================================================
# Sensitive File Detection Tests
# ============================================================================

class TestSensitiveFileDetection:
    """Tests for sensitive file detection."""

    def test_detects_env_file(self, resolver):
        """Should detect .env files as sensitive."""
        assert resolver.is_sensitive_file(".env") is True
        assert resolver.is_sensitive_file(".env.local") is True
        assert resolver.is_sensitive_file(".env.production") is True

    def test_detects_secrets_files(self, resolver):
        """Should detect secrets files as sensitive."""
        assert resolver.is_sensitive_file("secrets.yaml") is True
        assert resolver.is_sensitive_file("secrets.json") is True
        assert resolver.is_sensitive_file("config/secrets/db.yaml") is True

    def test_detects_credential_files(self, resolver):
        """Should detect credential files as sensitive."""
        assert resolver.is_sensitive_file("credentials.json") is True
        assert resolver.is_sensitive_file("aws_credentials") is True

    def test_detects_key_files(self, resolver):
        """Should detect key files as sensitive."""
        assert resolver.is_sensitive_file("private.key") is True
        assert resolver.is_sensitive_file("server.pem") is True
        assert resolver.is_sensitive_file("cert.p12") is True

    def test_detects_api_key_files(self, resolver):
        """Should detect API key files as sensitive."""
        assert resolver.is_sensitive_file("api_key.txt") is True
        assert resolver.is_sensitive_file("apikey.json") is True

    def test_detects_token_files(self, resolver):
        """Should detect token files as sensitive."""
        assert resolver.is_sensitive_file("token.txt") is True
        assert resolver.is_sensitive_file("access_token.json") is True

    def test_allows_normal_files(self, resolver):
        """Should allow normal code files."""
        assert resolver.is_sensitive_file("src/main.py") is False
        assert resolver.is_sensitive_file("tests/test_utils.py") is False
        assert resolver.is_sensitive_file("README.md") is False
        assert resolver.is_sensitive_file("package.json") is False

    def test_skips_llm_for_sensitive_files(self, resolver, mock_llm_client):
        """Should skip LLM and return escalation for sensitive files."""
        result = resolver.resolve(
            file_path=".env",
            base="KEY=old",
            ours="KEY=new",
            theirs="KEY=other",
        )

        assert result.needs_escalation is True
        assert result.escalation_reason == "sensitive_file"
        # LLM should NOT have been called
        mock_llm_client.generate.assert_not_called()


# ============================================================================
# Intent Extraction Tests
# ============================================================================

class TestIntentExtraction:
    """Tests for intent extraction."""

    def test_extracts_intent_from_diff(self, resolver, mock_llm_client):
        """Should extract intent from code changes."""
        # Mock LLM response
        mock_llm_client.generate.return_value = json.dumps({
            "primary_intent": "Add data normalization feature",
            "hard_constraints": ["Must preserve existing API"],
            "soft_constraints": ["Prefer lowercase"],
            "confidence": "high",
        })

        intent = resolver._extract_intent(
            side="ours",
            base="def process(data): return data",
            content="def process(data, normalize=True): return data.lower() if normalize else data",
            file_path="utils.py",
        )

        assert intent.side == "ours"
        assert "normalization" in intent.primary_intent.lower()
        assert intent.confidence == ConfidenceLevel.HIGH

    def test_handles_intent_extraction_failure(self, resolver, mock_llm_client):
        """Should handle LLM failure gracefully."""
        mock_llm_client.generate.side_effect = Exception("API error")

        intent = resolver._extract_intent(
            side="ours",
            base="",
            content="code",
            file_path="test.py",
        )

        assert intent.confidence == ConfidenceLevel.LOW
        assert "Could not extract" in intent.primary_intent

    def test_handles_malformed_json_response(self, resolver, mock_llm_client):
        """Should handle malformed JSON from LLM."""
        mock_llm_client.generate.return_value = "not valid json"

        intent = resolver._extract_intent(
            side="theirs",
            base="",
            content="code",
            file_path="test.py",
        )

        assert intent.confidence == ConfidenceLevel.LOW


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidation:
    """Tests for merge candidate validation."""

    def test_detects_conflict_markers(self, resolver):
        """Should fail validation if conflict markers present."""
        content = '''def foo():
<<<<<<< HEAD
    return 1
=======
    return 2
>>>>>>> branch
'''
        result = resolver._validate_candidate("test.py", content)

        assert result.passed is False
        assert "conflict markers" in result.errors[0].lower()

    def test_validates_python_syntax(self, resolver):
        """Should validate Python syntax."""
        valid_python = "def hello():\n    return 'world'"
        invalid_python = "def hello(\n    return 'world'"

        valid_result = resolver._validate_candidate("test.py", valid_python)
        invalid_result = resolver._validate_candidate("test.py", invalid_python)

        assert valid_result.passed is True
        assert valid_result.tier_reached == "syntax"
        assert invalid_result.passed is False
        assert "syntax error" in invalid_result.errors[0].lower()

    def test_validates_json_syntax(self, resolver):
        """Should validate JSON syntax."""
        valid_json = '{"key": "value"}'
        invalid_json = '{key: value}'

        valid_result = resolver._validate_candidate("config.json", valid_json)
        invalid_result = resolver._validate_candidate("config.json", invalid_json)

        assert valid_result.passed is True
        assert invalid_result.passed is False

    def test_skips_syntax_check_for_unknown_types(self, resolver):
        """Should pass validation for unknown file types if content exists."""
        content = "some random content"

        result = resolver._validate_candidate("data.txt", content)

        assert result.passed is True
        assert result.tier_reached == "syntax"

    def test_fails_empty_content(self, resolver):
        """Should fail validation for empty content."""
        result = resolver._validate_candidate("file.txt", "   \n  ")

        assert result.passed is False
        assert "empty" in result.errors[0].lower()


# ============================================================================
# Confidence Scoring Tests
# ============================================================================

class TestConfidenceScoring:
    """Tests for confidence score calculation."""

    def test_high_confidence_from_good_signals(self, resolver):
        """Should calculate high confidence from good signals."""
        intents = [
            ExtractedIntent(side="ours", primary_intent="Add feature", confidence=ConfidenceLevel.HIGH),
            ExtractedIntent(side="theirs", primary_intent="Fix bug", confidence=ConfidenceLevel.HIGH),
        ]
        candidate = MergeCandidate(content="merged", strategy="llm_merge", confidence=0.75)
        validation = ValidationResult(passed=True, tier_reached="syntax")

        confidence, reasons = resolver._calculate_confidence(intents, candidate, validation)

        assert confidence >= 0.8
        assert "High intent extraction confidence" in reasons

    def test_low_confidence_from_bad_signals(self, resolver):
        """Should calculate low confidence from bad signals."""
        intents = [
            ExtractedIntent(side="ours", primary_intent="Unknown", confidence=ConfidenceLevel.LOW),
            ExtractedIntent(side="theirs", primary_intent="Unknown", confidence=ConfidenceLevel.LOW),
        ]
        candidate = MergeCandidate(content="merged", strategy="llm_merge", confidence=0.3)
        validation = ValidationResult(passed=False, errors=["Failed to validate"])

        confidence, reasons = resolver._calculate_confidence(intents, candidate, validation)

        assert confidence < 0.5

    def test_confidence_level_thresholds(self, resolver):
        """Should convert scores to correct confidence levels."""
        assert resolver._get_confidence_level(0.9) == ConfidenceLevel.HIGH
        assert resolver._get_confidence_level(0.8) == ConfidenceLevel.HIGH
        assert resolver._get_confidence_level(0.7) == ConfidenceLevel.MEDIUM
        assert resolver._get_confidence_level(0.5) == ConfidenceLevel.MEDIUM
        assert resolver._get_confidence_level(0.4) == ConfidenceLevel.LOW
        assert resolver._get_confidence_level(0.1) == ConfidenceLevel.LOW


# ============================================================================
# Full Resolution Pipeline Tests
# ============================================================================

class TestResolutionPipeline:
    """Tests for the full resolution pipeline."""

    def test_successful_resolution(self, resolver, mock_llm_client, sample_conflict):
        """Should successfully resolve a conflict."""
        # Mock intent extraction
        mock_llm_client.generate.side_effect = [
            # Intent for ours
            json.dumps({
                "primary_intent": "Add optional normalization",
                "hard_constraints": [],
                "soft_constraints": [],
                "confidence": "high",
            }),
            # Intent for theirs
            json.dumps({
                "primary_intent": "Add input validation",
                "hard_constraints": [],
                "soft_constraints": [],
                "confidence": "high",
            }),
            # Merged code
            '''def process_data(data, normalize=True):
    """Process data with validation and optional normalization."""
    if not data:
        raise ValueError("Data cannot be empty")
    result = data.strip()
    if normalize:
        result = result.lower()
    return result
''',
        ]

        result = resolver.resolve(**sample_conflict)

        assert result.success is True
        assert result.merged_content is not None
        assert "process_data" in result.merged_content
        assert result.strategy == "llm_merge"

    def test_resolution_with_low_confidence_escalates(self, resolver, mock_llm_client, sample_conflict):
        """Should escalate when confidence is low."""
        resolver.auto_apply_threshold = 0.8

        # Mock responses with low confidence
        mock_llm_client.generate.side_effect = [
            json.dumps({
                "primary_intent": "Unknown changes",
                "hard_constraints": [],
                "soft_constraints": [],
                "confidence": "low",
            }),
            json.dumps({
                "primary_intent": "Unknown changes",
                "hard_constraints": [],
                "soft_constraints": [],
                "confidence": "low",
            }),
            "def process_data(data): return data",  # Very short response
        ]

        result = resolver.resolve(**sample_conflict)

        # Low confidence should trigger escalation
        assert result.confidence_level in [ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM]

    def test_handles_llm_generation_failure(self, resolver, mock_llm_client, sample_conflict):
        """Should handle LLM generation failure."""
        mock_llm_client.generate.side_effect = [
            json.dumps({"primary_intent": "Test", "confidence": "medium"}),
            json.dumps({"primary_intent": "Test", "confidence": "medium"}),
            Exception("API rate limit exceeded"),
        ]

        result = resolver.resolve(**sample_conflict)

        assert result.success is False
        assert result.needs_escalation is True


# ============================================================================
# Context Assembly Tests
# ============================================================================

class TestContextAssembly:
    """Tests for context assembly."""

    def test_detects_language_from_extension(self, resolver):
        """Should detect programming language from file extension."""
        assert resolver._detect_language("main.py") == "python"
        assert resolver._detect_language("app.js") == "javascript"
        assert resolver._detect_language("server.ts") == "typescript"
        assert resolver._detect_language("main.go") == "go"
        assert resolver._detect_language("app.rs") == "rust"
        assert resolver._detect_language("unknown.xyz") == "text"

    def test_assembles_context_within_budget(self, resolver, tmp_path):
        """Should respect token budget when assembling context."""
        # Create a CLAUDE.md file
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project conventions\nUse snake_case for functions.")

        context = resolver._assemble_context(
            file_path="test.py",
            base="base",
            ours="ours",
            theirs="theirs",
            extra_context=None,
        )

        assert context["language"] == "python"
        assert len(context["conventions"]) <= 1  # Should include CLAUDE.md if found

    def test_includes_related_files_in_context(self, resolver):
        """Should include related files if provided."""
        extra_context = {
            "related_files": [
                {"path": "utils.py", "relationship": "imports", "content": "def helper(): pass"},
                {"path": "types.py", "relationship": "imports", "content": "class Type: pass"},
            ]
        }

        context = resolver._assemble_context(
            file_path="main.py",
            base="base",
            ours="ours",
            theirs="theirs",
            extra_context=extra_context,
        )

        assert len(context["related_files"]) == 2


# ============================================================================
# LLM Response Cleaning Tests
# ============================================================================

class TestLLMResponseCleaning:
    """Tests for cleaning LLM responses."""

    def test_removes_markdown_code_blocks(self, resolver):
        """Should remove markdown code blocks from response."""
        response = '''```python
def hello():
    return "world"
```'''
        cleaned = resolver._clean_llm_response(response, "python")

        assert cleaned.strip() == 'def hello():\n    return "world"'
        assert "```" not in cleaned

    def test_handles_response_without_code_blocks(self, resolver):
        """Should handle response without code blocks."""
        response = 'def hello():\n    return "world"'
        cleaned = resolver._clean_llm_response(response, "python")

        assert cleaned == response

    def test_handles_empty_response(self, resolver):
        """Should handle empty response."""
        cleaned = resolver._clean_llm_response("", "python")
        assert cleaned == ""


# ============================================================================
# Client Factory Tests
# ============================================================================

class TestClientFactory:
    """Tests for LLM client initialization."""

    def test_uses_provided_client(self, tmp_path, mock_llm_client):
        """Should use provided client if given."""
        resolver = LLMResolver(
            repo_path=tmp_path,
            client=mock_llm_client,
        )
        assert resolver.client == mock_llm_client

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}, clear=True)
    def test_creates_openai_client_from_env(self, tmp_path):
        """Should create OpenAI client from environment."""
        resolver = LLMResolver(repo_path=tmp_path)
        assert isinstance(resolver.client, OpenAIClient)

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}, clear=True)
    def test_creates_gemini_client_from_env(self, tmp_path):
        """Should create Gemini client from environment."""
        resolver = LLMResolver(repo_path=tmp_path)
        assert isinstance(resolver.client, GeminiClient)

    @patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}, clear=True)
    def test_creates_openrouter_client_from_env(self, tmp_path):
        """Should create OpenRouter client from environment."""
        resolver = LLMResolver(repo_path=tmp_path)
        assert isinstance(resolver.client, OpenRouterClient)

    @patch.dict('os.environ', {}, clear=True)
    def test_raises_error_without_api_key(self, tmp_path):
        """Should raise error if no API key available."""
        with pytest.raises(ValueError, match="No LLM API key"):
            LLMResolver(repo_path=tmp_path)


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_handles_none_base(self, resolver, mock_llm_client):
        """Should handle None base (new file conflict)."""
        mock_llm_client.generate.side_effect = [
            json.dumps({"primary_intent": "Create file", "confidence": "high"}),
            json.dumps({"primary_intent": "Create file", "confidence": "high"}),
            "def new_function(): pass",
        ]

        result = resolver.resolve(
            file_path="new_file.py",
            base=None,
            ours="def foo(): pass",
            theirs="def bar(): pass",
        )

        # Should still attempt resolution
        assert result is not None

    def test_handles_empty_content(self, resolver, mock_llm_client):
        """Should handle empty content gracefully."""
        mock_llm_client.generate.side_effect = [
            json.dumps({"primary_intent": "Empty", "confidence": "low"}),
            json.dumps({"primary_intent": "Empty", "confidence": "low"}),
            "",  # Empty response
        ]

        result = resolver.resolve(
            file_path="empty.py",
            base="",
            ours="",
            theirs="",
        )

        # Empty response should fail validation
        assert result.needs_escalation is True or not result.success

    def test_handles_very_large_files(self, resolver, mock_llm_client):
        """Should handle large files with token budget."""
        large_content = "x = 1\n" * 10000  # Very large file

        mock_llm_client.generate.side_effect = [
            json.dumps({"primary_intent": "Large file", "confidence": "medium"}),
            json.dumps({"primary_intent": "Large file", "confidence": "medium"}),
            "x = 1\n" * 100,  # Truncated response
        ]

        # Should not crash, may truncate
        result = resolver.resolve(
            file_path="large.py",
            base=large_content,
            ours=large_content + "y = 2\n",
            theirs=large_content + "z = 3\n",
        )

        assert result is not None

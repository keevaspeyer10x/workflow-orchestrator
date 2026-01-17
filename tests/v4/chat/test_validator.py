"""Tests for SummaryValidator."""
import pytest
from datetime import datetime

from src.v4.chat.models import Message, MessageRole, ValidationResult
from src.v4.chat.validator import SummaryValidator


class TestEntityExtraction:
    """Tests for entity extraction patterns."""

    def setup_method(self):
        """Set up validator for tests."""
        self.validator = SummaryValidator()

    def test_extract_file_paths(self):
        """Test extracting file paths from text."""
        text = """
        We need to modify /home/user/project/main.py and
        also check ./src/utils.py for the helper functions.
        The config is at ../config/settings.json.
        """

        entities = self.validator.extract_entities(text)

        assert "/home/user/project/main.py" in entities
        assert "./src/utils.py" in entities
        assert "../config/settings.json" in entities

    def test_extract_function_names(self):
        """Test extracting function/method names."""
        text = """
        Call the process_data() function first, then
        use MyClass.validate() for verification.
        The helper function get_config() returns settings.
        """

        entities = self.validator.extract_entities(text)

        assert "process_data()" in entities
        assert "MyClass.validate()" in entities
        assert "get_config()" in entities

    def test_extract_urls(self):
        """Test extracting URLs."""
        text = """
        See the documentation at https://docs.example.com/api
        and the issue tracker at http://issues.test.org/123.
        """

        entities = self.validator.extract_entities(text)

        assert "https://docs.example.com/api" in entities
        assert "http://issues.test.org/123" in entities

    def test_extract_decision_keywords(self):
        """Test extracting decision keywords."""
        text = """
        We decided to use Python. The team chose React for the frontend.
        The proposal was approved by management.
        However, the old API was rejected in favor of the new design.
        """

        decisions = self.validator.extract_decisions(text)

        assert any("decided" in d.lower() for d in decisions)
        assert any("chose" in d.lower() for d in decisions)
        assert any("approved" in d.lower() for d in decisions)
        assert any("rejected" in d.lower() for d in decisions)


class TestValidation:
    """Tests for summary validation."""

    def setup_method(self):
        """Set up validator for tests."""
        self.validator = SummaryValidator()

    def test_validate_summary_success(self):
        """Test validating a summary that contains all entities."""
        messages = [
            Message(
                id="1",
                role=MessageRole.USER,
                content="Please update /src/main.py with the new API",
            ),
            Message(
                id="2",
                role=MessageRole.ASSISTANT,
                content="I'll modify the process_data() function. We decided to use async.",
            ),
        ]

        summary = """
        User requested updates to /src/main.py.
        Modified process_data() function.
        Decided to use async approach.
        """

        result = self.validator.validate(messages, summary)

        assert result.is_valid is True
        assert result.missing_entities == []
        assert result.missing_decisions == []

    def test_validate_summary_missing_entity(self):
        """Test validating summary with missing file path."""
        messages = [
            Message(
                id="1",
                role=MessageRole.USER,
                content="Update /src/config.py and /src/main.py",
            ),
        ]

        # Summary only mentions one file
        summary = "Updated /src/main.py with new configuration."

        result = self.validator.validate(messages, summary)

        assert result.is_valid is False
        assert "/src/config.py" in result.missing_entities

    def test_validate_summary_missing_decision(self):
        """Test validating summary with missing decision."""
        messages = [
            Message(
                id="1",
                role=MessageRole.ASSISTANT,
                content="We decided to use PostgreSQL. We also chose Redis for caching.",
            ),
        ]

        # Summary only mentions PostgreSQL decision
        summary = "Decision: Use PostgreSQL for the database."

        result = self.validator.validate(messages, summary)

        assert result.is_valid is False
        # Should flag missing decision about Redis/caching

    def test_validate_empty_messages(self):
        """Test validating with empty message list."""
        result = self.validator.validate([], "Any summary")

        # No entities to check, so should be valid
        assert result.is_valid is True

    def test_validate_empty_summary(self):
        """Test validating with empty summary."""
        messages = [
            Message(
                id="1",
                role=MessageRole.USER,
                content="Check /src/test.py",
            ),
        ]

        result = self.validator.validate(messages, "")

        assert result.is_valid is False
        assert "/src/test.py" in result.missing_entities

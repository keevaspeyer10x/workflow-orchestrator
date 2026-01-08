"""
Tests for src/validation.py - Input validation
"""

import pytest

from src.validation import (
    validate_constraint,
    validate_note,
    validate_constraints,
    MAX_CONSTRAINT_LENGTH,
    MAX_NOTE_LENGTH,
)


class TestValidateConstraint:
    """Tests for validate_constraint function."""

    def test_valid_constraint_under_limit(self):
        """TC-VAL-001: Constraints under limit accepted."""
        result = validate_constraint("short constraint")
        assert result == "short constraint"

    def test_valid_constraint_at_limit(self):
        """TC-VAL-002: Constraint exactly at limit accepted."""
        constraint = "a" * MAX_CONSTRAINT_LENGTH
        result = validate_constraint(constraint)
        assert result == constraint
        assert len(result) == MAX_CONSTRAINT_LENGTH

    def test_constraint_over_limit_rejected(self):
        """TC-VAL-003: Constraint over limit rejected."""
        constraint = "a" * (MAX_CONSTRAINT_LENGTH + 1)
        with pytest.raises(ValueError) as exc_info:
            validate_constraint(constraint)
        assert str(MAX_CONSTRAINT_LENGTH) in str(exc_info.value)
        assert "Constraint exceeds" in str(exc_info.value)

    def test_empty_constraint_accepted(self):
        """Empty constraints are valid."""
        assert validate_constraint("") == ""


class TestValidateNote:
    """Tests for validate_note function."""

    def test_valid_note_under_limit(self):
        """TC-VAL-004: Notes under limit accepted."""
        result = validate_note("short note")
        assert result == "short note"

    def test_note_at_limit(self):
        """TC-VAL-005: Note exactly at limit accepted."""
        note = "a" * MAX_NOTE_LENGTH
        result = validate_note(note)
        assert result == note
        assert len(result) == MAX_NOTE_LENGTH

    def test_note_over_limit_rejected(self):
        """TC-VAL-006: Note over limit rejected."""
        note = "a" * (MAX_NOTE_LENGTH + 1)
        with pytest.raises(ValueError) as exc_info:
            validate_note(note)
        assert str(MAX_NOTE_LENGTH) in str(exc_info.value)
        assert "Note exceeds" in str(exc_info.value)

    def test_none_note_accepted(self):
        """TC-VAL-007: None notes pass validation."""
        assert validate_note(None) is None

    def test_empty_note_accepted(self):
        """TC-VAL-007: Empty notes pass validation."""
        assert validate_note("") == ""


class TestValidateConstraints:
    """Tests for validate_constraints function."""

    def test_valid_constraints_list(self):
        """List of valid constraints accepted."""
        constraints = ["first", "second", "third"]
        result = validate_constraints(constraints)
        assert result == constraints

    def test_empty_list_accepted(self):
        """Empty list is valid."""
        assert validate_constraints([]) == []

    def test_one_invalid_constraint_rejects_all(self):
        """One constraint over limit rejects the whole list."""
        constraints = [
            "valid constraint",
            "a" * (MAX_CONSTRAINT_LENGTH + 1),
            "another valid one",
        ]
        with pytest.raises(ValueError) as exc_info:
            validate_constraints(constraints)
        assert "Constraint exceeds" in str(exc_info.value)


class TestConstants:
    """Tests for validation constants."""

    def test_constraint_length_is_1000(self):
        """MAX_CONSTRAINT_LENGTH is 1000 as specified in roadmap."""
        assert MAX_CONSTRAINT_LENGTH == 1000

    def test_note_length_is_500(self):
        """MAX_NOTE_LENGTH is 500 as specified in roadmap."""
        assert MAX_NOTE_LENGTH == 500

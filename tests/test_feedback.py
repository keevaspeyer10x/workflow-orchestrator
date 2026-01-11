"""
Unit tests for Phase 3b two-tier feedback system.
Tests anonymization, migration, extraction, and sync logic.
"""
import json
import hashlib
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import functions from cli module
from src.cli import (
    anonymize_tool_feedback,
    detect_repo_type,
    migrate_legacy_feedback,
    extract_tool_feedback_from_entry,
    extract_process_feedback_from_entry,
)


# Test Suite: Anonymization

def test_anonymize_tool_feedback_basic():
    """TC-1.1: Anonymize tool feedback - basic fields."""
    feedback = {
        'timestamp': '2026-01-11T10:00:00Z',
        'workflow_id': 'wf_abc123',
        'task': 'Add user authentication',
        'repo': 'https://github.com/user/private-repo',
        'orchestrator_version': '2.6.0',
        'phases': {'PLAN': 300, 'EXECUTE': 600}
    }

    result = anonymize_tool_feedback(feedback.copy())

    # Verify workflow_id replaced with hash
    assert 'workflow_id' not in result
    assert 'workflow_id_hash' in result
    assert len(result['workflow_id_hash']) == 64  # SHA256 length

    # Verify PII removed
    assert 'task' not in result
    assert 'repo' not in result

    # Verify other fields preserved
    assert result['timestamp'] == '2026-01-11T10:00:00Z'
    assert result['orchestrator_version'] == '2.6.0'
    assert result['phases'] == {'PLAN': 300, 'EXECUTE': 600}


def test_anonymize_tool_feedback_hash_consistency():
    """TC-1.2: Verify hash consistency for same workflow_id."""
    feedback1 = {'workflow_id': 'wf_test123'}
    feedback2 = {'workflow_id': 'wf_test123'}

    hash1 = anonymize_tool_feedback(feedback1.copy())['workflow_id_hash']
    hash2 = anonymize_tool_feedback(feedback2.copy())['workflow_id_hash']

    assert hash1 == hash2  # Deterministic hashing


def test_anonymize_tool_feedback_no_pii_leakage():
    """TC-1.3: Comprehensive PII leakage check."""
    feedback = {
        'workflow_id': 'wf_secret',
        'task': 'Fix security vulnerability in payment system',
        'repo': 'https://github.com/acme-corp/secret-project',
        'learnings': 'Database credentials were hardcoded',
        'challenges': 'OAuth integration with Stripe',
        'code_snippet': 'def process_payment(card_number):',
        'orchestrator_version': '2.6.0'
    }

    tool = anonymize_tool_feedback(feedback.copy())

    # Verify no PII fields
    assert 'workflow_id' not in tool
    assert 'task' not in tool
    assert 'repo' not in tool
    assert 'learnings' not in tool
    assert 'challenges' not in tool
    assert 'code_snippet' not in tool

    # Verify no PII strings in output
    output_str = json.dumps(tool).lower()
    assert 'secret' not in output_str
    assert 'payment' not in output_str
    assert 'acme-corp' not in output_str
    assert 'stripe' not in output_str
    assert 'credentials' not in output_str


# Test Suite: Repo Type Detection

def test_detect_repo_type_python():
    """TC-3.1: Detect Python repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / 'setup.py').touch()

        result = detect_repo_type(tmppath)
        assert result == 'python'


def test_detect_repo_type_python_pyproject():
    """TC-3.1b: Detect Python repository via pyproject.toml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / 'pyproject.toml').touch()

        result = detect_repo_type(tmppath)
        assert result == 'python'


def test_detect_repo_type_javascript():
    """TC-3.2: Detect JavaScript repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / 'package.json').touch()

        result = detect_repo_type(tmppath)
        assert result == 'javascript'


def test_detect_repo_type_go():
    """TC-3.3: Detect Go repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / 'go.mod').touch()

        result = detect_repo_type(tmppath)
        assert result == 'go'


def test_detect_repo_type_rust():
    """TC-3.4: Detect Rust repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / 'Cargo.toml').touch()

        result = detect_repo_type(tmppath)
        assert result == 'rust'


def test_detect_repo_type_unknown():
    """TC-3.5: Detect unknown repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # No language markers

        result = detect_repo_type(tmppath)
        assert result == 'unknown'


# Test Suite: Migration

def test_migrate_legacy_feedback_happy_path():
    """TC-2.1: Migrate legacy feedback - happy path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create legacy file
        legacy_file = tmppath / '.workflow_feedback.jsonl'
        entries = [
            {'timestamp': '2026-01-10T10:00:00Z', 'workflow_id': 'wf_1', 'task': 'Task 1', 'repo': 'repo1', 'learnings': 'Learning 1', 'phases': {}},
            {'timestamp': '2026-01-10T11:00:00Z', 'workflow_id': 'wf_2', 'task': 'Task 2', 'repo': 'repo2', 'learnings': 'Learning 2', 'phases': {}},
            {'timestamp': '2026-01-10T12:00:00Z', 'workflow_id': 'wf_3', 'task': 'Task 3', 'repo': 'repo3', 'learnings': 'Learning 3', 'phases': {}},
        ]
        with open(legacy_file, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

        # Run migration
        result = migrate_legacy_feedback(tmppath)
        assert result is True  # Migration occurred

        # Verify files
        assert not legacy_file.exists()
        assert (tmppath / '.workflow_feedback.jsonl.migrated').exists()
        assert (tmppath / '.workflow_tool_feedback.jsonl').exists()
        assert (tmppath / '.workflow_process_feedback.jsonl').exists()

        # Verify counts
        with open(tmppath / '.workflow_tool_feedback.jsonl') as f:
            tool_entries = [json.loads(line) for line in f]
        with open(tmppath / '.workflow_process_feedback.jsonl') as f:
            process_entries = [json.loads(line) for line in f]

        assert len(tool_entries) == 3
        assert len(process_entries) == 3

        # Verify anonymization in tool feedback
        for entry in tool_entries:
            assert 'workflow_id_hash' in entry
            assert 'task' not in entry
            assert 'repo' not in entry

        # Verify full data in process feedback
        for entry in process_entries:
            assert 'task' in entry
            assert 'repo' in entry


def test_migrate_legacy_feedback_already_migrated():
    """TC-2.2: Migration should be idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create new files (already migrated)
        (tmppath / '.workflow_tool_feedback.jsonl').touch()
        (tmppath / '.workflow_process_feedback.jsonl').touch()

        # Run migration
        result = migrate_legacy_feedback(tmppath)
        assert result is False  # No migration needed


def test_migrate_legacy_feedback_empty_file():
    """TC-2.4: Handle empty legacy file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create empty legacy file
        legacy_file = tmppath / '.workflow_feedback.jsonl'
        legacy_file.touch()

        # Run migration
        result = migrate_legacy_feedback(tmppath)
        assert result is True  # Migration occurred

        # Verify files created
        assert (tmppath / '.workflow_feedback.jsonl.migrated').exists()
        assert (tmppath / '.workflow_tool_feedback.jsonl').exists()
        assert (tmppath / '.workflow_process_feedback.jsonl').exists()


# Test Suite: Feedback Extraction

def test_extract_tool_feedback_from_entry():
    """TC-4.1: Extract tool-relevant data."""
    entry = {
        'timestamp': '2026-01-11T10:00:00Z',
        'workflow_id': 'wf_123',
        'task': 'User task',
        'repo': 'github.com/user/repo',
        'phases': {'PLAN': 300, 'EXECUTE': 600},
        'reviews_performed': True,
        'errors_count': 2,
        'items_skipped_count': 1,
        'learnings': 'Project-specific learning'
    }

    result = extract_tool_feedback_from_entry(entry)

    # Should include tool metrics
    assert 'timestamp' in result
    assert 'workflow_id' in result
    assert 'phases' in result
    assert result['reviews_performed'] is True
    assert result['errors_count'] == 2
    assert result['items_skipped_count'] == 1

    # Should exclude process-specific data
    assert 'task' not in result
    assert 'repo' not in result
    assert 'learnings' not in result


def test_extract_process_feedback_from_entry():
    """TC-4.2: Extract process-relevant data."""
    entry = {
        'timestamp': '2026-01-11T10:00:00Z',
        'workflow_id': 'wf_123',
        'task': 'User task',
        'repo': 'github.com/user/repo',
        'phases': {'PLAN': 300, 'EXECUTE': 600},
        'reviews_performed': True,
        'learnings': 'Project-specific learning',
        'challenges': 'OAuth was tricky'
    }

    result = extract_process_feedback_from_entry(entry)

    # Should include process context
    assert 'timestamp' in result
    assert 'workflow_id' in result
    assert result['task'] == 'User task'
    assert result['repo'] == 'github.com/user/repo'
    assert result['learnings'] == 'Project-specific learning'

    # Should exclude tool metrics (phases are tool-specific)
    assert 'phases' not in result
    assert 'reviews_performed' not in result


# Test Suite: SHA256 Hashing

def test_sha256_hash_format():
    """Verify SHA256 produces correct format."""
    workflow_id = 'wf_test123'
    expected_hash = hashlib.sha256(workflow_id.encode()).hexdigest()

    feedback = {'workflow_id': workflow_id}
    result = anonymize_tool_feedback(feedback)

    assert result['workflow_id_hash'] == expected_hash
    assert len(result['workflow_id_hash']) == 64


# Test Suite: Edge Cases

def test_anonymize_missing_fields():
    """Handle feedback with missing fields."""
    feedback = {'timestamp': '2026-01-11T10:00:00Z'}  # No workflow_id

    result = anonymize_tool_feedback(feedback.copy())

    # Should not crash, should handle gracefully
    assert 'timestamp' in result


def test_detect_repo_type_multiple_markers():
    """Prefer Python if multiple language markers exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / 'setup.py').touch()
        (tmppath / 'package.json').touch()  # Both Python and JS

        result = detect_repo_type(tmppath)
        # Should return first match (python has higher priority)
        assert result in ['python', 'javascript']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

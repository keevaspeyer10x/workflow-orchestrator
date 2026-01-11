import json
import os
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.cli import (
    detect_repo_type,
    anonymize_tool_feedback,
    extract_tool_feedback_from_entry,
    extract_process_feedback_from_entry,
    migrate_legacy_feedback,
    cmd_feedback_capture
)

# ============================================================================ 
# Unit Tests for Helper Functions
# ============================================================================ 

def test_detect_repo_type_python(tmp_path):
    (tmp_path / 'setup.py').touch()
    assert detect_repo_type(tmp_path) == 'python'
    (tmp_path / 'setup.py').unlink()
    
    (tmp_path / 'pyproject.toml').touch()
    assert detect_repo_type(tmp_path) == 'python'

def test_detect_repo_type_javascript(tmp_path):
    (tmp_path / 'package.json').touch()
    assert detect_repo_type(tmp_path) == 'javascript'

def test_detect_repo_type_go(tmp_path):
    (tmp_path / 'go.mod').touch()
    assert detect_repo_type(tmp_path) == 'go'

def test_detect_repo_type_rust(tmp_path):
    (tmp_path / 'Cargo.toml').touch()
    assert detect_repo_type(tmp_path) == 'rust'

def test_detect_repo_type_unknown(tmp_path):
    assert detect_repo_type(tmp_path) == 'unknown'

def test_anonymize_tool_feedback():
    feedback = {
        'workflow_id': 'wf_123',
        'task': 'Secret task',
        'repo': 'https://github.com/secret/repo',
        'timestamp': '2026-01-01T12:00:00Z',
        'phases': {'PLAN': 100},
        'learnings': 'Secret learning',
        'challenges': 'Secret challenge',
        'what_went_well': 'Secret success',
        'improvements': 'Secret improvement',
        'code_snippet': 'secret code',
        'errors_summary': ['error in secret_file.py'],
        'items_skipped_reasons': ['skipped secret item']
    }
    
    anonymized = anonymize_tool_feedback(feedback)
    
    # Check that PII is removed
    assert 'workflow_id' not in anonymized
    assert 'workflow_id_hash' in anonymized
    assert 'task' not in anonymized
    assert 'repo' not in anonymized
    assert 'learnings' not in anonymized
    assert 'challenges' not in anonymized
    assert 'what_went_well' not in anonymized
    assert 'improvements' not in anonymized
    assert 'code_snippet' not in anonymized
    assert 'errors_summary' not in anonymized
    assert 'items_skipped_reasons' not in anonymized
    
    # Check that allowed fields are kept
    assert anonymized['timestamp'] == '2026-01-01T12:00:00Z'
    assert anonymized['phases'] == {'PLAN': 100}

def test_extract_tool_feedback():
    entry = {
        'timestamp': '2026-01-01T12:00:00Z',
        'workflow_id': 'wf_123',
        'mode': 'auto',
        'orchestrator_version': '1.0.0',
        'repo_type': 'python',
        'duration_seconds': 120,
        'phases': {'PLAN': 100},
        'parallel_agents_used': True,
        'reviews_performed': True,
        'errors_count': 1,
        'items_skipped_count': 0,
        'task': 'Should be ignored',
        'learnings': 'Should be ignored'
    }
    
    tool = extract_tool_feedback_from_entry(entry)
    
    assert tool['workflow_id'] == 'wf_123'
    assert tool['repo_type'] == 'python'
    assert tool['duration_seconds'] == 120
    assert 'task' not in tool
    assert 'learnings' not in tool

def test_extract_process_feedback():
    entry = {
        'timestamp': '2026-01-01T12:00:00Z',
        'workflow_id': 'wf_123',
        'task': 'My Task',
        'repo': 'my-repo',
        'learnings': 'My Learning',
        'phases': {'PLAN': 100}, # Should be ignored
        'duration_seconds': 120 # Should be ignored
    }
    
    process = extract_process_feedback_from_entry(entry)
    
    assert process['task'] == 'My Task'
    assert process['repo'] == 'my-repo'
    assert process['learnings'] == 'My Learning'
    assert 'phases' not in process
    assert 'duration_seconds' not in process

def test_migrate_legacy_feedback(tmp_path):
    legacy_file = tmp_path / '.workflow_feedback.jsonl'
    tool_file = tmp_path / '.workflow_tool_feedback.jsonl'
    process_file = tmp_path / '.workflow_process_feedback.jsonl'
    
    # Create legacy file
    entry = {
        'timestamp': '2026-01-01T12:00:00Z',
        'workflow_id': 'wf_123',
        'task': 'My Task',
        'repo': 'my-repo',
        'learnings': 'My Learning',
        'phases': {'PLAN': 100}
    }
    with open(legacy_file, 'w') as f:
        f.write(json.dumps(entry) + '\n')
    
    # Run migration
    assert migrate_legacy_feedback(tmp_path) is True
    
    # Verify new files created
    assert tool_file.exists()
    assert process_file.exists()
    assert (tmp_path / '.workflow_feedback.jsonl.migrated').exists()
    assert not legacy_file.exists()
    
    # Verify content
    with open(tool_file) as f:
        tool_data = json.load(f)
        assert 'workflow_id_hash' in tool_data
        assert 'task' not in tool_data
    
    with open(process_file) as f:
        process_data = json.load(f)
        assert process_data['task'] == 'My Task'
        assert process_data['learnings'] == 'My Learning'

# ============================================================================ 
# Integration Test for Bug Reproduction (Notes Extraction)
# ============================================================================ 

def test_cmd_feedback_capture_extracts_notes_correctly(tmp_path, capsys):
    """
    Test that cmd_feedback_capture correctly extracts notes from 'details' field.
    This reproduces the bug where it was looking for 'notes' at the top level.
    """
    # Setup workflow files
    state_file = tmp_path / '.workflow_state.json'
    log_file = tmp_path / '.workflow_log.jsonl'
    process_feedback_file = tmp_path / '.workflow_process_feedback.jsonl'
    
    # Create valid state
    state = {
        "workflow_id": "wf_test",
        "task_description": "Test Task",
        "status": "completed"
    }
    with open(state_file, 'w') as f:
        json.dump(state, f)
        
    # Create log with document_learnings event
    # NOTE: The bug is that the code looks for event.get('notes'), but engine logs it in details={'notes': ...}
    log_event = {
        "type": "item_completed",
        "item_id": "document_learnings",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": {
            "notes": "These are the important learnings."
        }
    }
    with open(log_file, 'w') as f:
        f.write(json.dumps(log_event) + '\n')
        
    # Mock args
    args = MagicMock()
    args.dir = str(tmp_path)
    args.interactive = False
    args.feedback_command = None
    
    # Run command
    # We patch os.environ to avoid skipping feedback
    with patch.dict(os.environ, {}, clear=True):
        cmd_feedback_capture(args)
        
    # Check if learnings were extracted
    assert process_feedback_file.exists()
    with open(process_feedback_file) as f:
        feedback = json.load(f)
        
    # Assertion that fails if the bug is present
    assert feedback['learnings'] == "These are the important learnings."


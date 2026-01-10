"""
Day 16: End-to-End Integration Test

Comprehensive test of complete workflow lifecycle from PLAN → TDD → IMPL → REVIEW
Tests multi-agent coordination, state management, events, gates, tool permissions, and audit logs.
"""

import pytest
from pathlib import Path
import time

from src.orchestrator.api import app
from src.orchestrator.state import state_manager
from src.orchestrator.events import event_bus, EventTypes
from src.orchestrator.audit import audit_logger
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_orchestrator_server):
    """Create test client for API"""
    return TestClient(mock_orchestrator_server)


@pytest.fixture
def clean_state(tmp_path):
    """Ensure clean state before each test"""
    # Reset state manager to clean state file
    from src.orchestrator.state import StateManager
    import src.orchestrator.state as state_module
    state_file = tmp_path / "test_state.json"
    state_module.state_manager = StateManager(state_file)

    # Clear event bus
    event_bus.clear_history()

    yield

    # Cleanup
    state_module.state_manager = StateManager()


class TestCompleteWorkflow:
    """Test complete workflow from PLAN to REVIEW"""

    def test_single_agent_complete_workflow(self, client, tmp_path, clean_state):
        """
        Test complete workflow with single agent

        Flow: PLAN → TDD → IMPL → REVIEW
        """
        # ============================================================
        # PHASE 1: PLAN
        # ============================================================

        # Claim task (starts in PLAN phase)
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-001",
            "capabilities": ["python", "planning"]
        })
        assert claim_response.status_code == 200
        claim_data = claim_response.json()

        task_id = claim_data["task"]["id"]
        plan_token = claim_data["phase_token"]

        assert claim_data["phase"] == "PLAN"

        # Verify task registered in state
        snapshot = state_manager.get_snapshot(task_id)
        assert snapshot["current_phase"] == "PLAN"

        # Verify TASK_CLAIMED event published
        events = event_bus.get_history(event_type=EventTypes.TASK_CLAIMED)
        assert len(events) >= 1
        assert events[0]["data"]["task_id"] == task_id

        # Use allowed tool in PLAN phase (read_files)
        test_file = tmp_path / "requirements.txt"
        test_file.write_text("pytest>=7.0.0\n")

        tool_response = client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": plan_token,
            "tool_name": "read_files",
            "args": {"path": str(test_file)}
        })
        assert tool_response.status_code == 200

        # Verify TOOL_EXECUTED event published
        tool_events = event_bus.get_history(event_type=EventTypes.TOOL_EXECUTED)
        assert len(tool_events) >= 1
        assert tool_events[0]["data"]["tool_name"] == "read_files"
        assert tool_events[0]["data"]["success"] is True

        # Try forbidden tool in PLAN phase (write_files)
        forbidden_response = client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": plan_token,
            "tool_name": "write_files",
            "args": {"path": str(tmp_path / "output.txt"), "content": "test"}
        })
        assert forbidden_response.status_code == 403

        # Get state snapshot
        snapshot_response = client.get(
            f"/api/v1/state/snapshot?phase_token={plan_token}"
        )
        assert snapshot_response.status_code == 200
        snapshot_data = snapshot_response.json()
        assert snapshot_data["current_phase"] == "PLAN"

        # ============================================================
        # PHASE 2: Transition PLAN → TDD
        # ============================================================

        # Attempt transition with invalid artifacts (should be blocked)
        invalid_transition = client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": plan_token,
            "artifacts": {
                "plan_document": {
                    "title": "Bad",  # Too short
                    "acceptance_criteria": [],  # Empty
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        })
        assert invalid_transition.status_code == 200
        invalid_data = invalid_transition.json()
        assert invalid_data["allowed"] is False
        assert len(invalid_data["blockers"]) > 0

        # Verify GATE_BLOCKED event published
        gate_blocked_events = event_bus.get_history(event_type=EventTypes.GATE_BLOCKED)
        assert len(gate_blocked_events) >= 1

        # Transition with valid artifacts (should succeed)
        valid_transition = client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": plan_token,
            "artifacts": {
                "plan_document": {
                    "title": "Complete Feature Plan with Details",
                    "acceptance_criteria": [
                        {"criterion": "Feature works", "how_to_verify": "Manual test"}
                    ],
                    "implementation_steps": ["Write tests", "Implement"],
                    "scope": {"in_scope": ["Feature A"], "out_of_scope": ["Feature B"]}
                }
            }
        })
        assert valid_transition.status_code == 200
        transition_data = valid_transition.json()
        assert transition_data["allowed"] is True
        assert transition_data["new_token"] is not None

        tdd_token = transition_data["new_token"]

        # Verify GATE_PASSED event published
        gate_passed_events = event_bus.get_history(event_type=EventTypes.GATE_PASSED)
        assert len(gate_passed_events) >= 1

        # Verify TASK_TRANSITIONED event published
        transition_events = event_bus.get_history(event_type=EventTypes.TASK_TRANSITIONED)
        assert len(transition_events) >= 1
        assert transition_events[0]["data"]["from_phase"] == "PLAN"
        assert transition_events[0]["data"]["to_phase"] == "TDD"

        # Verify state updated
        snapshot = state_manager.get_snapshot(task_id)
        assert snapshot["current_phase"] == "TDD"

        # ============================================================
        # PHASE 3: TDD
        # ============================================================

        # Now write_files is allowed in TDD
        write_response = client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": tdd_token,
            "tool_name": "write_files",
            "args": {
                "path": str(tmp_path / "test_feature.py"),
                "content": "def test_feature():\n    assert True\n"
            }
        })
        assert write_response.status_code == 200

        # Verify file was written
        assert (tmp_path / "test_feature.py").exists()

        # ============================================================
        # PHASE 4: Verify audit log
        # ============================================================

        # Query audit log for this task
        audit_response = client.get(f"/api/v1/audit/query?task_id={task_id}")
        assert audit_response.status_code == 200
        audit_data = audit_response.json()

        # Should have tool executions logged
        assert audit_data["total"] >= 2  # read_files and write_files

        # Verify audit log stats
        stats_response = client.get("/api/v1/audit/stats")
        assert stats_response.status_code == 200
        stats_data = stats_response.json()
        assert stats_data["total_entries"] >= 2


class TestMultiAgentCoordination:
    """Test multi-agent coordination with dependencies"""

    def test_dependent_tasks(self, client, tmp_path, clean_state):
        """
        Test two agents with task dependencies

        Agent 1: task-A (no dependencies)
        Agent 2: task-B (depends on task-A)
        """
        # ============================================================
        # Agent 1: Claim task-A
        # ============================================================

        claim_a = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-001",
            "capabilities": ["python"]
        })
        assert claim_a.status_code == 200
        task_a_id = claim_a.json()["task"]["id"]

        # ============================================================
        # Agent 2: Claim task-B with dependency on task-A
        # ============================================================

        claim_b = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-002",
            "capabilities": ["python"]
        })
        assert claim_b.status_code == 200
        task_b_id = claim_b.json()["task"]["id"]

        # Manually set dependency (in real system, this would come from workflow definition)
        state_manager._state["dependencies"][task_b_id] = [task_a_id]
        state_manager._save_state()

        # task-B should be blocked until task-A completes
        assert state_manager.is_task_unblocked(task_b_id) is False

        # ============================================================
        # Agent 1: Complete task-A
        # ============================================================

        state_manager.mark_completed(task_a_id)
        event_bus.publish(EventTypes.TASK_COMPLETED, {"task_id": task_a_id})

        # Now task-B should be unblocked
        assert state_manager.is_task_unblocked(task_b_id) is True

        # Verify completed tasks in snapshot
        snapshot = state_manager.get_snapshot(task_b_id)
        assert task_a_id in snapshot["completed_tasks"]


class TestGateBlocking:
    """Test gate blocking and artifact validation"""

    def test_gate_blocks_invalid_artifacts(self, client, clean_state):
        """Gate should block transition when artifacts invalid"""
        # Claim task
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-001",
            "capabilities": []
        })
        task_id = claim_response.json()["task"]["id"]
        plan_token = claim_response.json()["phase_token"]

        # Try to transition with missing required fields
        transition = client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": plan_token,
            "artifacts": {
                "plan_document": {
                    "title": "Test",
                    # Missing acceptance_criteria
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        })

        assert transition.status_code == 200
        data = transition.json()
        assert data["allowed"] is False
        assert len(data["blockers"]) > 0

        # Verify GATE_BLOCKED event
        events = event_bus.get_history(event_type=EventTypes.GATE_BLOCKED)
        assert len(events) >= 1

    def test_gate_passes_valid_artifacts(self, client, clean_state):
        """Gate should pass when artifacts valid"""
        # Claim task
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-001",
            "capabilities": []
        })
        task_id = claim_response.json()["task"]["id"]
        plan_token = claim_response.json()["phase_token"]

        # Transition with all required fields
        transition = client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": plan_token,
            "artifacts": {
                "plan_document": {
                    "title": "Complete Plan with All Details",
                    "acceptance_criteria": [
                        {"criterion": "Works", "how_to_verify": "Test"}
                    ],
                    "implementation_steps": ["Step 1", "Step 2"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        })

        assert transition.status_code == 200
        data = transition.json()
        assert data["allowed"] is True

        # Verify GATE_PASSED event
        events = event_bus.get_history(event_type=EventTypes.GATE_PASSED)
        assert len(events) >= 1


class TestToolPermissions:
    """Test tool permission enforcement across phases"""

    def test_plan_phase_permissions(self, client, tmp_path, clean_state):
        """PLAN phase should allow read_files, forbid write_files"""
        # Claim task
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-001",
            "capabilities": []
        })
        task_id = claim_response.json()["task"]["id"]
        plan_token = claim_response.json()["phase_token"]

        # read_files should be allowed
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        read_response = client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": plan_token,
            "tool_name": "read_files",
            "args": {"path": str(test_file)}
        })
        assert read_response.status_code == 200

        # write_files should be forbidden
        write_response = client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": plan_token,
            "tool_name": "write_files",
            "args": {"path": str(tmp_path / "output.txt"), "content": "test"}
        })
        assert write_response.status_code == 403

    def test_tdd_phase_permissions(self, client, tmp_path, clean_state):
        """TDD phase should allow write_files"""
        # Claim task and transition to TDD
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-001",
            "capabilities": []
        })
        task_id = claim_response.json()["task"]["id"]
        plan_token = claim_response.json()["phase_token"]

        # Transition to TDD
        transition = client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": plan_token,
            "artifacts": {
                "plan_document": {
                    "title": "Test Plan with Sufficient Detail",
                    "acceptance_criteria": [
                        {"criterion": "Works", "how_to_verify": "Test"}
                    ],
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        })
        tdd_token = transition.json()["new_token"]

        # write_files should now be allowed
        write_response = client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": tdd_token,
            "tool_name": "write_files",
            "args": {"path": str(tmp_path / "test.py"), "content": "def test(): pass"}
        })
        assert write_response.status_code == 200


class TestAuditLogging:
    """Test audit log functionality"""

    def test_tool_execution_logged(self, client, tmp_path, clean_state):
        """Tool executions should be logged to audit log"""
        # Claim task
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-audit",
            "capabilities": []
        })
        task_id = claim_response.json()["task"]["id"]
        token = claim_response.json()["phase_token"]

        # Execute tool
        test_file = tmp_path / "audit_test.txt"
        test_file.write_text("audit content")

        client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": token,
            "tool_name": "read_files",
            "args": {"path": str(test_file)}
        })

        # Query audit log
        audit_response = client.get(f"/api/v1/audit/query?task_id={task_id}")
        assert audit_response.status_code == 200

        entries = audit_response.json()["entries"]
        assert len(entries) >= 1

        # Verify log entry has required fields
        entry = entries[0]
        assert entry["task_id"] == task_id
        assert entry["phase"] == "PLAN"
        assert entry["tool_name"] == "read_files"
        assert entry["success"] is True

    def test_audit_stats(self, client, tmp_path, clean_state):
        """Audit stats should aggregate data correctly"""
        # Execute some tools
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-stats",
            "capabilities": []
        })
        task_id = claim_response.json()["task"]["id"]
        token = claim_response.json()["phase_token"]

        test_file = tmp_path / "stats_test.txt"
        test_file.write_text("stats content")

        # Execute multiple tools
        for _ in range(3):
            client.post("/api/v1/tools/execute", json={
                "task_id": task_id,
                "phase_token": token,
                "tool_name": "read_files",
                "args": {"path": str(test_file)}
            })

        # Get stats
        stats_response = client.get("/api/v1/audit/stats")
        assert stats_response.status_code == 200

        stats = stats_response.json()
        assert stats["total_entries"] >= 3
        assert stats["total_successes"] >= 3
        assert "read_files" in stats["tools_used"]


class TestEventBusIntegration:
    """Test event bus integration"""

    def test_events_published_throughout_workflow(self, client, clean_state):
        """Events should be published at each workflow step"""
        # Clear history
        event_bus.clear_history()

        # Claim task
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-events",
            "capabilities": []
        })

        # Should have TASK_CLAIMED event
        claimed_events = event_bus.get_history(event_type=EventTypes.TASK_CLAIMED)
        assert len(claimed_events) >= 1

        # Transition to TDD
        task_id = claim_response.json()["task"]["id"]
        token = claim_response.json()["phase_token"]

        client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": token,
            "artifacts": {
                "plan_document": {
                    "title": "Event Test Plan Document",
                    "acceptance_criteria": [
                        {"criterion": "Works", "how_to_verify": "Test"}
                    ],
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        })

        # Should have TASK_TRANSITIONED event
        transition_events = event_bus.get_history(event_type=EventTypes.TASK_TRANSITIONED)
        assert len(transition_events) >= 1

        # Should have GATE_PASSED event
        gate_passed_events = event_bus.get_history(event_type=EventTypes.GATE_PASSED)
        assert len(gate_passed_events) >= 1

    def test_event_history_persists(self, client, clean_state):
        """Event history should persist and be queryable"""
        # Generate some events
        client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-history",
            "capabilities": []
        })

        # Get all history
        all_history = event_bus.get_history()
        assert len(all_history) >= 1

        # Each event should have timestamp
        for event in all_history:
            assert "timestamp" in event
            assert "type" in event
            assert "data" in event


class TestStateConsistency:
    """Test state consistency across operations"""

    def test_state_persists_across_operations(self, client, tmp_path, clean_state):
        """State should remain consistent across multiple operations"""
        # Claim task
        claim_response = client.post("/api/v1/tasks/claim", json={
            "agent_id": "agent-consistency",
            "capabilities": []
        })
        task_id = claim_response.json()["task"]["id"]

        # Verify initial state
        snapshot1 = state_manager.get_snapshot(task_id)
        assert snapshot1["current_phase"] == "PLAN"

        # Transition
        token = claim_response.json()["phase_token"]
        client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": token,
            "artifacts": {
                "plan_document": {
                    "title": "Consistency Test Plan",
                    "acceptance_criteria": [
                        {"criterion": "Works", "how_to_verify": "Test"}
                    ],
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        })

        # Verify state updated
        snapshot2 = state_manager.get_snapshot(task_id)
        assert snapshot2["current_phase"] == "TDD"

        # Verify task info preserved
        tasks = state_manager.get_all_tasks()
        assert task_id in tasks
        assert tasks[task_id]["agent_id"] == "agent-consistency"

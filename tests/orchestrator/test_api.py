"""
Day 6-7: API Endpoint Tests

Tests for FastAPI REST endpoints.
"""

import pytest
from fastapi.testclient import TestClient
import jwt as pyjwt
from datetime import datetime, timedelta, timezone


@pytest.fixture
def api_client(test_workflow_file, jwt_secret):
    """
    Create FastAPI test client with enforcement engine

    Args:
        test_workflow_file: Path to test workflow YAML
        jwt_secret: JWT secret for token generation

    Returns:
        FastAPI TestClient
    """
    from src.orchestrator.api import app
    from src.orchestrator.enforcement import WorkflowEnforcement

    # Import the global enforcement variable
    from src.orchestrator import api

    # Initialize enforcement with test workflow
    api.enforcement = WorkflowEnforcement(test_workflow_file)

    client = TestClient(app)
    return client


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_root_endpoint(self, api_client):
        """Should return service status"""
        response = api_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "workflow-orchestrator-api"

    def test_health_endpoint(self, api_client):
        """Should return health status"""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["workflow_loaded"] is True
        assert "enforcement_mode" in data


class TestClaimTaskEndpoint:
    """Tests for POST /api/v1/tasks/claim"""

    def test_claim_task_success(self, api_client):
        """Should successfully claim a task and receive token"""
        request_data = {
            "agent_id": "agent-001",
            "capabilities": ["python", "testing"]
        }

        response = api_client.post("/api/v1/tasks/claim", json=request_data)

        assert response.status_code == 200
        data = response.json()

        # Check task details
        assert "task" in data
        assert data["task"]["agent_id"] == "agent-001"
        assert data["task"]["capabilities"] == ["python", "testing"]
        assert "id" in data["task"]

        # Check phase token
        assert "phase_token" in data
        assert "phase" in data
        assert data["phase"] == "PLAN"  # Should start in first phase

    def test_claim_task_without_capabilities(self, api_client):
        """Should work without capabilities specified"""
        request_data = {
            "agent_id": "agent-002"
        }

        response = api_client.post("/api/v1/tasks/claim", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["task"]["capabilities"] == []

    def test_claimed_token_is_valid_jwt(self, api_client, jwt_secret):
        """Token should be a valid JWT"""
        request_data = {
            "agent_id": "agent-003"
        }

        response = api_client.post("/api/v1/tasks/claim", json=request_data)
        data = response.json()

        # Decode and verify token
        token = data["phase_token"]
        payload = pyjwt.decode(token, jwt_secret, algorithms=["HS256"])

        assert "task_id" in payload
        assert "phase" in payload
        assert "allowed_tools" in payload
        assert "exp" in payload
        assert payload["phase"] == "PLAN"


class TestTransitionEndpoint:
    """Tests for POST /api/v1/tasks/transition"""

    def test_valid_transition_with_valid_artifacts(self, api_client, jwt_secret):
        """Should approve transition with valid artifacts and passing gate"""
        # First claim a task to get initial token
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-004"})
        claim_data = claim_response.json()
        task_id = claim_data["task"]["id"]
        phase_token = claim_data["phase_token"]

        # Request transition from PLAN to TDD
        transition_request = {
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": phase_token,
            "artifacts": {
                "plan_document": {
                    "title": "Valid plan with 10+ characters",
                    "acceptance_criteria": [
                        {"criterion": "Feature works", "how_to_verify": "Test it"}
                    ],
                    "implementation_steps": ["Step 1", "Step 2"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        }

        response = api_client.post("/api/v1/tasks/transition", json=transition_request)

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert data["new_token"] is not None
        assert len(data["blockers"]) == 0

        # Verify new token is for TDD phase
        new_payload = pyjwt.decode(data["new_token"], jwt_secret, algorithms=["HS256"])
        assert new_payload["phase"] == "TDD"
        assert new_payload["task_id"] == task_id

    def test_transition_blocked_by_invalid_artifacts(self, api_client):
        """Should block transition when artifacts are invalid"""
        # Claim task
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-005"})
        claim_data = claim_response.json()
        task_id = claim_data["task"]["id"]
        phase_token = claim_data["phase_token"]

        # Request transition with invalid artifacts (empty acceptance_criteria)
        transition_request = {
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": phase_token,
            "artifacts": {
                "plan_document": {
                    "title": "Invalid plan",
                    "acceptance_criteria": [],  # Invalid!
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        }

        response = api_client.post("/api/v1/tasks/transition", json=transition_request)

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert data["new_token"] is None
        assert len(data["blockers"]) > 0

    def test_transition_blocked_by_gate(self, api_client):
        """Should block transition when gate blocker fails"""
        # Claim task
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-006"})
        claim_data = claim_response.json()
        task_id = claim_data["task"]["id"]
        phase_token = claim_data["phase_token"]

        # Request transition with plan missing acceptance criteria
        transition_request = {
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": phase_token,
            "artifacts": {
                "plan_document": {
                    "title": "Plan without criteria",
                    "acceptance_criteria": [],  # Will fail gate check
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        }

        response = api_client.post("/api/v1/tasks/transition", json=transition_request)

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert len(data["blockers"]) > 0

    def test_transition_with_invalid_token(self, api_client):
        """Should reject transition with invalid token"""
        transition_request = {
            "task_id": "fake-task",
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": "invalid.token.here",
            "artifacts": {}
        }

        response = api_client.post("/api/v1/tasks/transition", json=transition_request)

        assert response.status_code == 403
        assert "Invalid or expired phase token" in response.json()["detail"]

    def test_transition_with_expired_token(self, api_client, jwt_secret):
        """Should reject transition with expired token"""
        # Create expired token
        expired_payload = {
            "task_id": "task-123",
            "phase": "PLAN",
            "allowed_tools": ["read_files"],
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
        }
        expired_token = pyjwt.encode(expired_payload, jwt_secret, algorithm="HS256")

        transition_request = {
            "task_id": "task-123",
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": expired_token,
            "artifacts": {}
        }

        response = api_client.post("/api/v1/tasks/transition", json=transition_request)

        assert response.status_code == 403

    def test_transition_nonexistent_phases(self, api_client):
        """Should reject transition between nonexistent phases"""
        # Claim task
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-007"})
        claim_data = claim_response.json()
        task_id = claim_data["task"]["id"]
        phase_token = claim_data["phase_token"]

        transition_request = {
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "NONEXISTENT",
            "phase_token": phase_token,
            "artifacts": {}
        }

        response = api_client.post("/api/v1/tasks/transition", json=transition_request)

        assert response.status_code == 400
        assert "No transition defined" in response.json()["detail"]


class TestToolExecuteEndpoint:
    """Tests for POST /api/v1/tools/execute"""

    def test_execute_allowed_tool(self, api_client, tmp_path):
        """Should allow execution of tool allowed in current phase"""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        # Claim task (starts in PLAN phase)
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-008"})
        claim_data = claim_response.json()
        task_id = claim_data["task"]["id"]
        phase_token = claim_data["phase_token"]

        # PLAN phase allows "read_files" and "grep"
        tool_request = {
            "task_id": task_id,
            "phase_token": phase_token,
            "tool_name": "read_files",
            "args": {"path": str(test_file)}
        }

        response = api_client.post("/api/v1/tools/execute", json=tool_request)

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["status"] == "success"
        assert "hello" in data["result"]["content"]
        assert data["logged"] is True

    def test_execute_forbidden_tool(self, api_client):
        """Should block execution of forbidden tool"""
        # Claim task (starts in PLAN phase)
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-009"})
        claim_data = claim_response.json()
        task_id = claim_data["task"]["id"]
        phase_token = claim_data["phase_token"]

        # PLAN phase forbids "write_files"
        tool_request = {
            "task_id": task_id,
            "phase_token": phase_token,
            "tool_name": "write_files",
            "args": {"path": "/some/file.py", "content": "code"}
        }

        response = api_client.post("/api/v1/tools/execute", json=tool_request)

        assert response.status_code == 403
        assert "not allowed in phase" in response.json()["detail"]

    def test_execute_tool_with_invalid_token(self, api_client):
        """Should reject tool execution with invalid token"""
        tool_request = {
            "task_id": "fake-task",
            "phase_token": "invalid.token.here",
            "tool_name": "read_files",
            "args": {}
        }

        response = api_client.post("/api/v1/tools/execute", json=tool_request)

        assert response.status_code == 403

    def test_execute_tool_with_mismatched_task_id(self, api_client, jwt_secret):
        """Should reject tool execution when task_id doesn't match token"""
        # Create token for one task
        token_payload = {
            "task_id": "task-abc",
            "phase": "PLAN",
            "allowed_tools": ["read_files"],
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp())
        }
        token = pyjwt.encode(token_payload, jwt_secret, algorithm="HS256")

        # Try to use it for a different task
        tool_request = {
            "task_id": "task-xyz",  # Different task!
            "phase_token": token,
            "tool_name": "read_files",
            "args": {}
        }

        response = api_client.post("/api/v1/tools/execute", json=tool_request)

        assert response.status_code == 403
        assert "task_id does not match" in response.json()["detail"]


class TestStateSnapshotEndpoint:
    """Tests for GET /api/v1/state/snapshot"""

    def test_get_state_snapshot_with_valid_token(self, api_client):
        """Should return state snapshot with valid token"""
        # Claim task
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-010"})
        claim_data = claim_response.json()
        phase_token = claim_data["phase_token"]

        # Get state snapshot
        response = api_client.get(f"/api/v1/state/snapshot?phase_token={phase_token}")

        assert response.status_code == 200
        data = response.json()
        assert "task_dependencies" in data
        assert "completed_tasks" in data
        assert "current_phase" in data
        assert "blockers" in data
        assert data["current_phase"] == "PLAN"

    def test_get_state_snapshot_with_invalid_token(self, api_client):
        """Should reject snapshot request with invalid token"""
        response = api_client.get("/api/v1/state/snapshot?phase_token=invalid.token.here")

        assert response.status_code == 403
        assert "Invalid or expired" in response.json()["detail"]


class TestEndToEndWorkflow:
    """End-to-end workflow tests"""

    def test_complete_workflow_plan_to_tdd(self, api_client, jwt_secret, tmp_path):
        """Should successfully complete PLAN -> TDD transition"""
        # Create test files
        test_read_file = tmp_path / "requirements.txt"
        test_read_file.write_text("pytest>=7.0.0\n")

        # Step 1: Claim task
        claim_response = api_client.post("/api/v1/tasks/claim", json={"agent_id": "agent-e2e"})
        assert claim_response.status_code == 200
        claim_data = claim_response.json()
        task_id = claim_data["task"]["id"]
        plan_token = claim_data["phase_token"]

        # Step 2: Use allowed tool in PLAN phase
        tool_response = api_client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": plan_token,
            "tool_name": "read_files",
            "args": {"path": str(test_read_file)}
        })
        assert tool_response.status_code == 200

        # Step 3: Transition to TDD with valid artifacts
        transition_response = api_client.post("/api/v1/tasks/transition", json={
            "task_id": task_id,
            "current_phase": "PLAN",
            "target_phase": "TDD",
            "phase_token": plan_token,
            "artifacts": {
                "plan_document": {
                    "title": "Complete E2E test plan",
                    "acceptance_criteria": [
                        {"criterion": "Tests pass", "how_to_verify": "Run pytest"}
                    ],
                    "implementation_steps": ["Write tests", "Implement"],
                    "scope": {"in_scope": ["Testing"], "out_of_scope": ["Production"]}
                }
            }
        })
        assert transition_response.status_code == 200
        transition_data = transition_response.json()
        assert transition_data["allowed"] is True
        tdd_token = transition_data["new_token"]

        # Step 4: Verify new token works in TDD phase
        tdd_payload = pyjwt.decode(tdd_token, jwt_secret, algorithms=["HS256"])
        assert tdd_payload["phase"] == "TDD"

        # Step 5: Use tool allowed in TDD phase
        test_write_file = tmp_path / "test_feature.py"
        tdd_tool_response = api_client.post("/api/v1/tools/execute", json={
            "task_id": task_id,
            "phase_token": tdd_token,
            "tool_name": "write_files",  # Allowed in TDD but not PLAN
            "args": {"path": str(test_write_file), "content": "def test_feature(): pass"}
        })
        assert tdd_tool_response.status_code == 200

        # Verify file was actually written
        assert test_write_file.exists()
        assert "test_feature" in test_write_file.read_text()

"""
Days 10-12: Agent SDK Client Tests

Tests for agent SDK client implementation.
"""

import pytest
from pathlib import Path
import httpx

from src.agent_sdk.client import AgentClient


@pytest.fixture
def mock_orchestrator_server(tmp_path, test_workflow_yaml, jwt_secret):
    """
    Start mock orchestrator server for testing

    Uses the actual FastAPI app with test workflow
    """
    from src.orchestrator.api import app
    from src.orchestrator.enforcement import WorkflowEnforcement
    from src.orchestrator import api
    import yaml

    # Create test workflow file
    test_workflow_file = tmp_path / "test_workflow.yaml"
    with open(test_workflow_file, 'w') as f:
        yaml.dump(test_workflow_yaml, f)

    # Initialize enforcement with test workflow
    api.enforcement = WorkflowEnforcement(test_workflow_file)

    # Return app for test client
    return app


@pytest.fixture
def sdk_client(mock_orchestrator_server):
    """
    Create SDK client connected to mock server
    """
    from fastapi.testclient import TestClient

    # Create test client
    test_client = TestClient(mock_orchestrator_server)

    # Create SDK client with patched httpx client
    client = AgentClient(
        agent_id="test-agent-001",
        orchestrator_url="http://testserver"
    )

    # Replace httpx client with test client wrapper
    class TestClientWrapper:
        def __init__(self, test_client):
            self._client = test_client

        def post(self, path, json=None):
            return self._client.post(path, json=json)

        def get(self, path, params=None):
            return self._client.get(path, params=params)

        def close(self):
            pass

    client.client = TestClientWrapper(test_client)

    yield client

    client.close()


class TestAgentClientInit:
    """Tests for AgentClient initialization"""

    def test_init_with_defaults(self):
        """Should initialize with default orchestrator URL"""
        client = AgentClient(agent_id="agent-001")

        assert client.agent_id == "agent-001"
        assert client.orchestrator_url == "http://localhost:8000"
        assert client.phase_token is None
        assert client.current_phase is None
        assert client.task_id is None

        client.close()

    def test_init_with_custom_url(self):
        """Should accept custom orchestrator URL"""
        client = AgentClient(
            agent_id="agent-002",
            orchestrator_url="http://custom:9000/"
        )

        assert client.orchestrator_url == "http://custom:9000"

        client.close()

    def test_context_manager(self):
        """Should work as context manager"""
        with AgentClient(agent_id="agent-003") as client:
            assert client.agent_id == "agent-003"


class TestClaimTask:
    """Tests for claim_task()"""

    def test_claim_task_success(self, sdk_client):
        """Should successfully claim a task"""
        result = sdk_client.claim_task(capabilities=["python", "testing"])

        assert "task" in result
        assert "phase_token" in result
        assert "phase" in result
        assert result["phase"] == "PLAN"

        # Should store credentials
        assert sdk_client.task_id is not None
        assert sdk_client.phase_token is not None
        assert sdk_client.current_phase == "PLAN"

    def test_claim_task_without_capabilities(self, sdk_client):
        """Should work without capabilities"""
        result = sdk_client.claim_task()

        assert "task" in result
        assert sdk_client.task_id is not None

    def test_claim_task_stores_credentials(self, sdk_client):
        """Should store task credentials after claiming"""
        result = sdk_client.claim_task()

        task_id = result["task"]["id"]
        phase_token = result["phase_token"]

        assert sdk_client.task_id == task_id
        assert sdk_client.phase_token == phase_token


class TestRequestTransition:
    """Tests for request_transition()"""

    def test_transition_success(self, sdk_client, tmp_path):
        """Should successfully transition phases"""
        # First claim task
        sdk_client.claim_task()

        initial_token = sdk_client.phase_token
        initial_phase = sdk_client.current_phase

        # Transition from PLAN to TDD
        result = sdk_client.request_transition(
            target_phase="TDD",
            artifacts={
                "plan_document": {
                    "title": "Test plan with 10+ characters",
                    "acceptance_criteria": [
                        {"criterion": "Feature works", "how_to_verify": "Test it"}
                    ],
                    "implementation_steps": ["Step 1", "Step 2"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        )

        assert result["allowed"] is True
        assert result["new_token"] is not None

        # Should update credentials
        assert sdk_client.phase_token != initial_token
        assert sdk_client.current_phase == "TDD"

    def test_transition_blocked_by_invalid_artifacts(self, sdk_client):
        """Should raise error when artifacts invalid"""
        sdk_client.claim_task()

        with pytest.raises(PermissionError, match="Transition blocked"):
            sdk_client.request_transition(
                target_phase="TDD",
                artifacts={
                    "plan_document": {
                        "title": "Invalid",
                        "acceptance_criteria": [],  # Invalid!
                        "implementation_steps": ["Step 1"],
                        "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                    }
                }
            )

    def test_transition_without_claiming(self, sdk_client):
        """Should raise error if not claimed task first"""
        with pytest.raises(RuntimeError, match="Must claim task"):
            sdk_client.request_transition(
                target_phase="TDD",
                artifacts={}
            )


class TestUseTool:
    """Tests for use_tool()"""

    def test_use_tool_success(self, sdk_client, tmp_path):
        """Should successfully execute allowed tool"""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        # Claim task (starts in PLAN phase)
        sdk_client.claim_task()

        # Use allowed tool (read_files is allowed in PLAN)
        result = sdk_client.use_tool("read_files", path=str(test_file))

        assert result is not None
        assert "content" in result
        assert "Hello World" in result["content"]

    def test_use_tool_forbidden(self, sdk_client):
        """Should raise error for forbidden tool"""
        sdk_client.claim_task()

        # write_files is forbidden in PLAN phase
        with pytest.raises(PermissionError, match="not allowed"):
            sdk_client.use_tool("write_files", path="/test.txt", content="test")

    def test_use_tool_without_claiming(self, sdk_client):
        """Should raise error if not claimed task first"""
        with pytest.raises(RuntimeError, match="Must claim task"):
            sdk_client.use_tool("read_files", path="/test.txt")

    def test_use_tool_with_invalid_args(self, sdk_client):
        """Should raise ValueError for tool execution errors"""
        sdk_client.claim_task()

        # Try to read nonexistent file
        with pytest.raises(ValueError, match="execution failed"):
            sdk_client.use_tool("read_files", path="/nonexistent/file.txt")


class TestGetStateSnapshot:
    """Tests for get_state_snapshot()"""

    def test_get_snapshot_success(self, sdk_client):
        """Should get state snapshot"""
        sdk_client.claim_task()

        snapshot = sdk_client.get_state_snapshot()

        assert "task_dependencies" in snapshot
        assert "completed_tasks" in snapshot
        assert "current_phase" in snapshot
        assert "blockers" in snapshot
        assert snapshot["current_phase"] == "PLAN"

    def test_get_snapshot_without_claiming(self, sdk_client):
        """Should raise error if not claimed task first"""
        with pytest.raises(RuntimeError, match="Must claim task"):
            sdk_client.get_state_snapshot()


class TestConvenienceMethods:
    """Tests for convenience methods"""

    def test_read_file_convenience(self, sdk_client, tmp_path):
        """Should read file using convenience method"""
        test_file = tmp_path / "convenience.txt"
        test_file.write_text("Convenience test")

        sdk_client.claim_task()

        content = sdk_client.read_file(str(test_file))

        assert "Convenience test" in content

    def test_write_file_convenience(self, sdk_client, tmp_path):
        """Should write file using convenience method"""
        sdk_client.claim_task()

        # Transition to TDD where write_files is allowed
        sdk_client.request_transition(
            target_phase="TDD",
            artifacts={
                "plan_document": {
                    "title": "Test plan with 10+ characters",
                    "acceptance_criteria": [
                        {"criterion": "Test", "how_to_verify": "Manual"}
                    ],
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        )

        test_file = tmp_path / "written.txt"
        result = sdk_client.write_file(str(test_file), "Test content")

        assert result["status"] == "success"
        assert test_file.exists()
        assert test_file.read_text() == "Test content"

    def test_run_command_convenience(self, sdk_client):
        """Should run command using convenience method"""
        sdk_client.claim_task()

        # Transition to TDD where bash is allowed
        sdk_client.request_transition(
            target_phase="TDD",
            artifacts={
                "plan_document": {
                    "title": "Test plan with 10+ characters",
                    "acceptance_criteria": [
                        {"criterion": "Test", "how_to_verify": "Manual"}
                    ],
                    "implementation_steps": ["Step 1"],
                    "scope": {"in_scope": ["A"], "out_of_scope": ["B"]}
                }
            }
        )

        result = sdk_client.run_command("echo 'Hello'")

        assert result["status"] == "completed"
        assert "Hello" in result["stdout"]
        assert result["exit_code"] == 0

    def test_grep_convenience(self, sdk_client, tmp_path):
        """Should search files using convenience method"""
        test_file = tmp_path / "search.txt"
        test_file.write_text("def hello():\n    pass\n")

        sdk_client.claim_task()

        result = sdk_client.grep(r"def.*:", str(test_file))

        assert result["status"] == "success"
        assert result["total"] >= 1


class TestEndToEndWorkflow:
    """End-to-end workflow tests"""

    def test_complete_plan_to_tdd_workflow(self, sdk_client, tmp_path):
        """Should complete full workflow from PLAN to TDD"""
        # Step 1: Claim task
        claim_result = sdk_client.claim_task(capabilities=["python"])
        assert claim_result["phase"] == "PLAN"

        # Step 2: Use tools in PLAN phase
        test_read_file = tmp_path / "requirements.txt"
        test_read_file.write_text("pytest>=7.0.0\n")

        content = sdk_client.read_file(str(test_read_file))
        assert "pytest" in content

        # Step 3: Get state snapshot
        snapshot = sdk_client.get_state_snapshot()
        assert snapshot["current_phase"] == "PLAN"

        # Step 4: Transition to TDD
        transition_result = sdk_client.request_transition(
            target_phase="TDD",
            artifacts={
                "plan_document": {
                    "title": "Complete E2E workflow plan",
                    "acceptance_criteria": [
                        {"criterion": "Tests pass", "how_to_verify": "Run pytest"}
                    ],
                    "implementation_steps": ["Write tests", "Implement"],
                    "scope": {"in_scope": ["Testing"], "out_of_scope": ["Production"]}
                }
            }
        )

        assert transition_result["allowed"] is True
        assert sdk_client.current_phase == "TDD"

        # Step 5: Use tools in TDD phase
        test_write_file = tmp_path / "test_feature.py"
        write_result = sdk_client.write_file(
            str(test_write_file),
            "def test_feature():\n    assert True\n"
        )

        assert write_result["status"] == "success"
        assert test_write_file.exists()

    def test_workflow_with_context_manager(self, mock_orchestrator_server, tmp_path):
        """Should work with context manager"""
        from fastapi.testclient import TestClient

        test_client = TestClient(mock_orchestrator_server)

        with AgentClient(agent_id="ctx-agent", orchestrator_url="http://testserver") as client:
            # Patch client
            class TestClientWrapper:
                def __init__(self, test_client):
                    self._client = test_client

                def post(self, path, json=None):
                    return self._client.post(path, json=json)

                def get(self, path, params=None):
                    return self._client.get(path, params=params)

                def close(self):
                    pass

            client.client = TestClientWrapper(test_client)

            # Use client
            client.claim_task()
            assert client.task_id is not None

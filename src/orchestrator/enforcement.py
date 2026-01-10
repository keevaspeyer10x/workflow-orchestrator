"""
Workflow Enforcement Engine

Loads agent_workflow.yaml and enforces:
- Phase transitions with gates
- Tool access control (capability-scoped by phase)
- Artifact validation
- Cryptographic phase tokens (JWT)
"""

from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any
import yaml
import os
from datetime import datetime, timedelta, timezone

try:
    import jwt
except ImportError:
    jwt = None  # Installed on Day 3

try:
    import jsonschema
except ImportError:
    jsonschema = None  # Installed on Day 4


class WorkflowEnforcement:
    """
    Enforces workflow contract defined in agent_workflow.yaml

    Responsibilities:
    - Load and validate workflow YAML
    - Generate/verify phase tokens (JWT)
    - Validate phase transitions (artifacts + gates)
    - Enforce tool access control per phase
    """

    def __init__(self, workflow_path: Path = Path("agent_workflow.yaml")):
        """
        Initialize enforcement engine

        Args:
            workflow_path: Path to agent_workflow.yaml
        """
        self.workflow_path = workflow_path
        self.workflow = self._load_workflow()
        self.jwt_secret = os.getenv("ORCHESTRATOR_JWT_SECRET")

        if not self.jwt_secret:
            raise ValueError(
                "ORCHESTRATOR_JWT_SECRET environment variable not set. "
                "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )

    def _load_workflow(self) -> Dict[str, Any]:
        """
        Load agent_workflow.yaml and validate structure

        Performs comprehensive validation:
        - Required top-level keys present
        - Phases have required fields
        - Transitions reference valid phases
        - Enforcement section is valid

        Returns:
            Parsed workflow dict

        Raises:
            FileNotFoundError: If workflow file doesn't exist
            ValueError: If workflow structure is invalid
        """
        if not self.workflow_path.exists():
            raise FileNotFoundError(f"Workflow file not found: {self.workflow_path}")

        with open(self.workflow_path, 'r') as f:
            workflow = yaml.safe_load(f)

        if workflow is None:
            raise ValueError("Workflow file is empty")

        # Validate required top-level keys
        required_keys = ["phases", "transitions", "enforcement"]
        missing = [k for k in required_keys if k not in workflow]
        if missing:
            raise ValueError(f"Workflow missing required keys: {missing}")

        # Validate phases structure
        self._validate_phases(workflow.get("phases", []))

        # Validate transitions structure
        self._validate_transitions(
            workflow.get("transitions", []),
            workflow.get("phases", [])
        )

        # Validate enforcement section
        self._validate_enforcement(workflow.get("enforcement", {}))

        return workflow

    def _validate_phases(self, phases: List[Dict[str, Any]]) -> None:
        """
        Validate phases structure

        Args:
            phases: List of phase definitions

        Raises:
            ValueError: If phase structure is invalid
        """
        if not phases:
            raise ValueError("Workflow must define at least one phase")

        if not isinstance(phases, list):
            raise ValueError("Phases must be a list")

        phase_ids = set()
        for i, phase in enumerate(phases):
            # Check required fields
            required_fields = ["id", "name", "allowed_tools"]
            missing = [f for f in required_fields if f not in phase]
            if missing:
                raise ValueError(
                    f"Phase {i} missing required fields: {missing}"
                )

            # Check for duplicate phase IDs
            phase_id = phase["id"]
            if phase_id in phase_ids:
                raise ValueError(f"Duplicate phase ID: {phase_id}")
            phase_ids.add(phase_id)

            # Validate allowed_tools is a list
            if not isinstance(phase.get("allowed_tools"), list):
                raise ValueError(
                    f"Phase {phase_id}: allowed_tools must be a list"
                )

            # Validate forbidden_tools is a list (if present)
            if "forbidden_tools" in phase:
                if not isinstance(phase["forbidden_tools"], list):
                    raise ValueError(
                        f"Phase {phase_id}: forbidden_tools must be a list"
                    )

    def _validate_transitions(
        self,
        transitions: List[Dict[str, Any]],
        phases: List[Dict[str, Any]]
    ) -> None:
        """
        Validate transitions structure

        Args:
            transitions: List of transition definitions
            phases: List of phase definitions

        Raises:
            ValueError: If transition structure is invalid
        """
        if not isinstance(transitions, list):
            raise ValueError("Transitions must be a list")

        # Build set of valid phase IDs
        phase_ids = {p["id"] for p in phases}

        for i, transition in enumerate(transitions):
            # Check required fields
            required_fields = ["from", "to"]
            missing = [f for f in required_fields if f not in transition]
            if missing:
                raise ValueError(
                    f"Transition {i} missing required fields: {missing}"
                )

            # Validate from/to phases exist
            from_phase = transition["from"]
            to_phase = transition["to"]

            if from_phase not in phase_ids:
                raise ValueError(
                    f"Transition {i}: 'from' phase '{from_phase}' not defined"
                )

            if to_phase not in phase_ids:
                raise ValueError(
                    f"Transition {i}: 'to' phase '{to_phase}' not defined"
                )

    def _validate_enforcement(self, enforcement: Dict[str, Any]) -> None:
        """
        Validate enforcement section

        Args:
            enforcement: Enforcement configuration

        Raises:
            ValueError: If enforcement configuration is invalid
        """
        if not isinstance(enforcement, dict):
            raise ValueError("Enforcement must be a dict")

        # Check mode is valid
        valid_modes = ["strict", "permissive", "advisory"]
        mode = enforcement.get("mode")
        if mode and mode not in valid_modes:
            raise ValueError(
                f"Enforcement mode must be one of {valid_modes}, got: {mode}"
            )

        # Validate phase_tokens section if present
        if "phase_tokens" in enforcement:
            tokens = enforcement["phase_tokens"]
            if not isinstance(tokens, dict):
                raise ValueError("phase_tokens must be a dict")

            # Check required token fields
            if "enabled" in tokens and not isinstance(tokens["enabled"], bool):
                raise ValueError("phase_tokens.enabled must be a boolean")

            if "expiry_seconds" in tokens:
                if not isinstance(tokens["expiry_seconds"], int):
                    raise ValueError("phase_tokens.expiry_seconds must be an integer")
                if tokens["expiry_seconds"] <= 0:
                    raise ValueError("phase_tokens.expiry_seconds must be positive")

    def _get_phase(self, phase_id: str) -> Optional[Dict[str, Any]]:
        """
        Get phase definition by ID

        Args:
            phase_id: Phase identifier (e.g., "PLAN", "TDD")

        Returns:
            Phase definition dict, or None if not found
        """
        for phase in self.workflow.get("phases", []):
            if phase.get("id") == phase_id:
                return phase
        return None

    def _get_gate(self, gate_id: str) -> Optional[Dict[str, Any]]:
        """
        Get gate definition by ID

        Args:
            gate_id: Gate identifier (e.g., "plan_approval")

        Returns:
            Gate definition dict, or None if not found
        """
        for phase in self.workflow.get("phases", []):
            for gate in phase.get("gates", []):
                if gate.get("id") == gate_id:
                    return gate
        return None

    def _find_transition(
        self,
        from_phase: str,
        to_phase: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find transition definition between two phases

        Args:
            from_phase: Source phase ID
            to_phase: Target phase ID

        Returns:
            Transition definition, or None if not found
        """
        for transition in self.workflow.get("transitions", []):
            if (transition.get("from") == from_phase and
                transition.get("to") == to_phase):
                return transition
        return None

    def generate_phase_token(
        self,
        task_id: str,
        phase: str
    ) -> str:
        """
        Generate JWT phase token

        Token includes:
        - task_id: Which task this token is for
        - phase: Current phase
        - allowed_tools: Tools allowed in this phase
        - exp: Expiry timestamp (2 hours)

        Args:
            task_id: Task identifier
            phase: Phase identifier

        Returns:
            JWT token string

        Raises:
            ValueError: If jwt library not installed or phase not found
        """
        if jwt is None:
            raise ValueError("PyJWT not installed. Run: pip install pyjwt")

        phase_def = self._get_phase(phase)
        if not phase_def:
            raise ValueError(f"Phase not found: {phase}")

        # Calculate expiry as Unix timestamp (timezone-aware)
        expiry_seconds = self.workflow["enforcement"]["phase_tokens"]["expiry_seconds"]
        now_utc = datetime.now(timezone.utc)
        exp_time = now_utc + timedelta(seconds=expiry_seconds)
        exp_timestamp = int(exp_time.timestamp())

        payload = {
            "task_id": task_id,
            "phase": phase,
            "allowed_tools": phase_def.get("allowed_tools", []),
            "exp": exp_timestamp
        }

        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def _verify_phase_token(
        self,
        token: str,
        task_id: str,
        phase: str
    ) -> bool:
        """
        Verify phase token is valid

        Checks:
        - Signature is valid
        - Token not expired
        - task_id matches
        - phase matches

        Args:
            token: JWT token string
            task_id: Expected task ID
            phase: Expected phase

        Returns:
            True if valid, False otherwise
        """
        if jwt is None:
            return False

        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])

            # Verify claims
            if payload.get("task_id") != task_id:
                return False
            if payload.get("phase") != phase:
                return False

            return True

        except jwt.ExpiredSignatureError:
            return False
        except jwt.InvalidTokenError:
            return False

    def _validate_artifacts(
        self,
        artifacts: Dict[str, Any],
        required_artifacts: List[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Validate artifacts against JSON schemas

        Args:
            artifacts: Dict of artifact_type -> artifact_data
            required_artifacts: List of required artifact definitions from workflow

        Returns:
            Tuple of (valid: bool, errors: List[str])
        """
        if jsonschema is None:
            raise ValueError("jsonschema not installed. Run: pip install jsonschema")

        errors = []

        # Check all required artifacts are present
        required_types = {req["type"] for req in required_artifacts}
        provided_types = set(artifacts.keys())
        missing = required_types - provided_types

        if missing:
            errors.append(f"Missing required artifacts: {sorted(missing)}")
            return False, errors

        # Validate each artifact against its schema
        for req in required_artifacts:
            artifact_type = req["type"]
            artifact_data = artifacts.get(artifact_type)

            # Get schema path
            schema_file = req.get("schema")
            if not schema_file:
                continue  # No schema specified, skip validation

            # Load schema
            schema_path = Path(schema_file)
            if not schema_path.exists():
                # Try relative to orchestrator schemas dir
                schema_path = Path(".orchestrator") / "schemas" / schema_path.name

            if not schema_path.exists():
                errors.append(f"Schema file not found: {schema_file}")
                continue

            try:
                with open(schema_path, 'r') as f:
                    schema = yaml.safe_load(f)  # Schemas can be JSON or YAML
            except Exception as e:
                errors.append(f"Failed to load schema {schema_file}: {e}")
                continue

            # Validate artifact against schema
            try:
                jsonschema.validate(artifact_data, schema)
            except jsonschema.ValidationError as e:
                # Format error message to be more readable
                error_path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
                errors.append(
                    f"Artifact '{artifact_type}' validation failed at {error_path}: {e.message}"
                )
            except Exception as e:
                errors.append(f"Artifact '{artifact_type}' validation error: {e}")

        return len(errors) == 0, errors

    def _check_plan_has_acceptance_criteria(
        self,
        artifacts: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if plan artifact has acceptance criteria

        Args:
            artifacts: Dict of artifact_type -> artifact_data

        Returns:
            Tuple of (passes: bool, error_message: Optional[str])
        """
        plan = artifacts.get("plan_document")
        if not plan:
            return False, "Missing plan_document artifact"

        criteria = plan.get("acceptance_criteria", [])
        if not criteria or len(criteria) == 0:
            return False, "Plan must include at least one acceptance criterion"

        # Check each criterion has required fields
        for i, criterion in enumerate(criteria):
            if not criterion.get("criterion"):
                return False, f"Acceptance criterion {i} missing 'criterion' field"
            if not criterion.get("how_to_verify"):
                return False, f"Acceptance criterion {i} missing 'how_to_verify' field"

        return True, None

    def _check_tests_are_failing(
        self,
        artifacts: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if tests are failing (TDD RED phase)

        Args:
            artifacts: Dict of artifact_type -> artifact_data

        Returns:
            Tuple of (passes: bool, error_message: Optional[str])
        """
        test_result = artifacts.get("test_run_result")
        if not test_result:
            return False, "Missing test_run_result artifact"

        # Check exit code is non-zero (failure)
        exit_code = test_result.get("exit_code")
        if exit_code == 0:
            return False, "Tests must be failing for TDD RED phase (exit_code should be non-zero)"

        # Verify we have actual test failures
        failed = test_result.get("failed", 0)
        if failed == 0:
            return False, "No failing tests detected - TDD requires failing tests initially"

        return True, None

    def _check_all_tests_pass(
        self,
        artifacts: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if all tests pass (TDD GREEN phase)

        Args:
            artifacts: Dict of artifact_type -> artifact_data

        Returns:
            Tuple of (passes: bool, error_message: Optional[str])
        """
        test_result = artifacts.get("test_run_result")
        if not test_result:
            return False, "Missing test_run_result artifact"

        # Check no failures (more specific error message)
        failed = test_result.get("failed", 0)
        if failed > 0:
            return False, f"{failed} test(s) failed - all tests must pass"

        # Check exit code is zero (success)
        exit_code = test_result.get("exit_code")
        if exit_code != 0:
            return False, f"Tests failed with exit code {exit_code}"

        # Check we have some passing tests
        passed = test_result.get("passed", 0)
        if passed == 0:
            return False, "No tests passed - must have at least one passing test"

        return True, None

    def _check_no_blocking_issues(
        self,
        artifacts: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if review has no blocking issues

        Args:
            artifacts: Dict of artifact_type -> artifact_data

        Returns:
            Tuple of (passes: bool, error_message: Optional[str])
        """
        review = artifacts.get("review_results")
        if not review:
            return False, "Missing review_results artifact"

        # Check blocking_issues array
        blocking_issues = review.get("blocking_issues", [])
        if len(blocking_issues) > 0:
            issue_descriptions = [issue.get("description", "Unknown issue") for issue in blocking_issues]
            return False, f"Found {len(blocking_issues)} blocking issue(s): {'; '.join(issue_descriptions)}"

        return True, None

    def _validate_gate(
        self,
        gate_id: str,
        artifacts: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate gate blockers pass

        Args:
            gate_id: Gate identifier (e.g., "plan_approval")
            artifacts: Artifacts submitted for gate validation

        Returns:
            Tuple of (passes: bool, blockers: List[str])
        """
        gate = self._get_gate(gate_id)
        if not gate:
            return False, [f"Gate not found: {gate_id}"]

        blockers = []

        # Check each gate blocker
        for blocker in gate.get("blockers", []):
            check_name = blocker.get("check")
            severity = blocker.get("severity", "blocking")
            message = blocker.get("message", f"Gate check failed: {check_name}")

            # Map check names to checker methods
            checker_map = {
                "plan_has_acceptance_criteria": self._check_plan_has_acceptance_criteria,
                "tests_are_failing": self._check_tests_are_failing,
                "all_tests_pass": self._check_all_tests_pass,
                "no_blocking_issues": self._check_no_blocking_issues,
            }

            checker = checker_map.get(check_name)
            if not checker:
                # Unknown check - skip for now (will implement more checks in later days)
                continue

            # Run the checker
            passes, error = checker(artifacts)

            # If check fails and is blocking, add to blockers list
            if not passes and severity == "blocking":
                blockers.append(f"{message} - {error}" if error else message)

        return len(blockers) == 0, blockers

    def validate_phase_transition(
        self,
        task_id: str,
        current_phase: str,
        target_phase: str,
        phase_token: str,
        artifacts: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate phase transition

        Checks:
        1. Phase token is valid for current phase
        2. Transition exists in workflow
        3. Required artifacts present and valid
        4. Gate blockers pass

        Args:
            task_id: Task identifier
            current_phase: Current phase ID
            target_phase: Target phase ID
            phase_token: JWT token for current phase
            artifacts: Artifacts submitted for transition

        Returns:
            Tuple of (allowed: bool, blockers: List[str])
        """
        # TODO: Implement on Day 5
        # For now, return basic validation
        return True, []

    def get_allowed_tools(self, phase: str) -> List[str]:
        """
        Get list of tools allowed in a phase

        Args:
            phase: Phase identifier

        Returns:
            List of allowed tool names
        """
        phase_def = self._get_phase(phase)
        if not phase_def:
            return []
        return phase_def.get("allowed_tools", [])

    def is_tool_forbidden(self, phase: str, tool: str) -> bool:
        """
        Check if tool is forbidden in phase

        Args:
            phase: Phase identifier
            tool: Tool name

        Returns:
            True if forbidden, False if allowed
        """
        phase_def = self._get_phase(phase)
        if not phase_def:
            return True  # Default deny

        # Check forbidden list
        if tool in phase_def.get("forbidden_tools", []):
            return True

        # Check allowed list (deny by default)
        if tool not in phase_def.get("allowed_tools", []):
            return True

        return False

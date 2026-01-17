"""
Programmatic gate validation.
Gates are checked by CODE, not by LLM self-report.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import List

from .models import (
    GateSpec, GateResult, GateStatus,
    FileExistsGate, CommandGate, NoPatternGate, JsonValidGate
)


class GateEngine:
    """
    Validates gates programmatically.
    LLM cannot bypass these checks.
    """

    def __init__(self, working_dir: Path):
        self.working_dir = Path(working_dir)

    def validate_all(self, gates: List[GateSpec]) -> List[GateResult]:
        """
        Validate all gates for a phase.
        Returns list of results (one per gate).
        """
        results = []
        for gate in gates:
            result = self._validate_gate(gate)
            results.append(result)
        return results

    def all_passed(self, results: List[GateResult]) -> bool:
        """Check if all gate results passed"""
        return all(r.passed for r in results)

    def _validate_gate(self, gate: GateSpec) -> GateResult:
        """Dispatch to appropriate validator"""
        if isinstance(gate, FileExistsGate):
            return self._validate_file_exists(gate)
        elif isinstance(gate, CommandGate):
            return self._validate_command(gate)
        elif isinstance(gate, NoPatternGate):
            return self._validate_no_pattern(gate)
        elif isinstance(gate, JsonValidGate):
            return self._validate_json_valid(gate)
        else:
            return GateResult(
                gate_type=str(type(gate)),
                status=GateStatus.FAILED,
                reason=f"Unknown gate type: {type(gate)}"
            )

    def _validate_file_exists(self, gate: FileExistsGate) -> GateResult:
        """Check if a file exists"""
        path = self.working_dir / gate.path

        if path.exists():
            return GateResult(
                gate_type="file_exists",
                status=GateStatus.PASSED,
                details={"path": str(path)}
            )
        else:
            return GateResult(
                gate_type="file_exists",
                status=GateStatus.FAILED,
                reason=f"File not found: {gate.path}",
                details={"path": str(path)}
            )

    def _validate_command(self, gate: CommandGate) -> GateResult:
        """Run a command and check exit code"""
        try:
            result = subprocess.run(
                gate.cmd,
                shell=True,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=gate.timeout
            )

            # Check exit code
            if result.returncode != gate.exit_code:
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Command exited with {result.returncode}, expected {gate.exit_code}",
                    details={
                        "cmd": gate.cmd,
                        "returncode": result.returncode,
                        "stdout": result.stdout[:1000] if result.stdout else "",
                        "stderr": result.stderr[:1000] if result.stderr else ""
                    }
                )

            # Check empty output if required
            if gate.expect_empty and result.stdout.strip():
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Expected empty output but got: {result.stdout[:200]}",
                    details={"stdout": result.stdout[:1000]}
                )

            return GateResult(
                gate_type="command",
                status=GateStatus.PASSED,
                details={"cmd": gate.cmd, "returncode": result.returncode}
            )

        except subprocess.TimeoutExpired:
            return GateResult(
                gate_type="command",
                status=GateStatus.FAILED,
                reason=f"Command timed out after {gate.timeout}s",
                details={"cmd": gate.cmd, "timeout": gate.timeout}
            )
        except Exception as e:
            return GateResult(
                gate_type="command",
                status=GateStatus.FAILED,
                reason=f"Command execution error: {str(e)}",
                details={"cmd": gate.cmd, "error": str(e)}
            )

    def _validate_no_pattern(self, gate: NoPatternGate) -> GateResult:
        """Check that files don't contain a pattern"""
        try:
            pattern = re.compile(gate.pattern)
        except re.error as e:
            return GateResult(
                gate_type="no_pattern",
                status=GateStatus.FAILED,
                reason=f"Invalid regex pattern: {e}"
            )

        matches_found = []

        for glob_pattern in gate.paths:
            for file_path in self.working_dir.glob(glob_pattern):
                if file_path.is_file():
                    try:
                        content = file_path.read_text()
                        matches = pattern.findall(content)
                        if matches:
                            matches_found.append({
                                "file": str(file_path.relative_to(self.working_dir)),
                                "matches": matches[:5]  # Limit to first 5
                            })
                    except (UnicodeDecodeError, PermissionError):
                        continue  # Skip binary or inaccessible files

        if matches_found:
            return GateResult(
                gate_type="no_pattern",
                status=GateStatus.FAILED,
                reason=f"Pattern '{gate.pattern}' found in {len(matches_found)} file(s)",
                details={"matches": matches_found}
            )

        return GateResult(
            gate_type="no_pattern",
            status=GateStatus.PASSED,
            details={"pattern": gate.pattern, "paths_checked": gate.paths}
        )

    def _validate_json_valid(self, gate: JsonValidGate) -> GateResult:
        """Check that a file contains valid JSON"""
        path = self.working_dir / gate.path

        if not path.exists():
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.FAILED,
                reason=f"File not found: {gate.path}"
            )

        try:
            content = path.read_text()
            json.loads(content)
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.PASSED,
                details={"path": gate.path}
            )
        except json.JSONDecodeError as e:
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.FAILED,
                reason=f"Invalid JSON: {e}",
                details={"path": gate.path, "error": str(e)}
            )

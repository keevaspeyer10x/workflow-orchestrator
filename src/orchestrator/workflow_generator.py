"""
Workflow YAML generation based on repo analysis.

Analyzes repository structure and generates appropriate agent_workflow.yaml.
"""

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional


class WorkflowGeneratorError(Exception):
    """Raised when workflow generation fails."""
    pass


@dataclass
class RepoAnalysis:
    """Results of repository analysis."""
    language: str
    test_framework: str
    test_command: str
    has_tests: bool
    project_structure: Dict[str, bool]


def analyze_repo(repo_path: Path) -> RepoAnalysis:
    """
    Analyze repository to determine language, test framework, and structure.

    Args:
        repo_path: Path to repository root

    Returns:
        RepoAnalysis with detected project information

    Raises:
        WorkflowGeneratorError: If path is invalid
    """
    if not repo_path.exists():
        raise WorkflowGeneratorError(f"Repository path not found: {repo_path}")

    if not repo_path.is_dir():
        raise WorkflowGeneratorError(f"Path is not a directory: {repo_path}")

    # Detect language and test framework
    language = "unknown"
    test_framework = "unknown"
    test_command = ""
    has_tests = False
    project_structure = {}

    # Check for Python
    if (repo_path / "requirements.txt").exists() or \
       (repo_path / "setup.py").exists() or \
       (repo_path / "pyproject.toml").exists():
        language = "python"

        # Default to pytest for Python projects
        test_framework = "pytest"
        test_command = "pytest"

        # Check for tests directory
        if (repo_path / "tests").exists():
            has_tests = True
            project_structure["tests"] = True

        # Check for src directory
        if (repo_path / "src").exists():
            project_structure["src"] = True

    # Check for JavaScript/Node.js
    elif (repo_path / "package.json").exists():
        language = "javascript"

        try:
            package_json = json.loads((repo_path / "package.json").read_text())

            # Check for test frameworks in order of specificity
            dev_deps = package_json.get("devDependencies", {})
            deps = package_json.get("dependencies", {})

            # Check for Mocha first (more specific)
            if "mocha" in dev_deps or "mocha" in deps:
                test_framework = "mocha"
                test_command = "npm test"
            # Check for Jest
            elif "jest" in dev_deps or "jest" in deps:
                test_framework = "jest"
                test_command = "npm test"
            else:
                # Default to jest for JavaScript projects
                test_framework = "jest"
                test_command = "npm test"

        except (json.JSONDecodeError, KeyError):
            test_framework = "jest"
            test_command = "npm test"

        # Check for test directories
        if (repo_path / "__tests__").exists():
            has_tests = True
            project_structure["__tests__"] = True
        if (repo_path / "test").exists():
            has_tests = True
            project_structure["test"] = True

        # Check for src directory
        if (repo_path / "src").exists():
            project_structure["src"] = True

    # Check for Go
    elif (repo_path / "go.mod").exists():
        language = "go"
        test_framework = "go test"
        test_command = "go test ./..."

        # Check for test files
        has_tests = len(list(repo_path.glob("*_test.go"))) > 0

    # Check for Rust
    elif (repo_path / "Cargo.toml").exists():
        language = "rust"
        test_framework = "cargo test"
        test_command = "cargo test"

        # Check for tests directory
        if (repo_path / "tests").exists():
            has_tests = True
            project_structure["tests"] = True

        # Check for src directory
        if (repo_path / "src").exists():
            project_structure["src"] = True

    return RepoAnalysis(
        language=language,
        test_framework=test_framework,
        test_command=test_command,
        has_tests=has_tests,
        project_structure=project_structure
    )


def generate_workflow_yaml(task_description: str, analysis: RepoAnalysis) -> str:
    """
    Generate workflow YAML from template and repo analysis.

    Args:
        task_description: Description of the task
        analysis: Results of repo analysis

    Returns:
        Generated workflow YAML as string
    """
    # Load template
    template_path = Path(__file__).parent / "templates" / "workflow_template.yaml"
    template_content = template_path.read_text()

    # Replace placeholders
    workflow_yaml = template_content.format(
        task_description=task_description,
        language=analysis.language,
        test_framework=analysis.test_framework,
        test_command=analysis.test_command
    )

    return workflow_yaml


def save_workflow_yaml(content: str, repo_path: Path) -> Path:
    """
    Save workflow YAML to .orchestrator directory.

    Args:
        content: Workflow YAML content
        repo_path: Repository root path

    Returns:
        Path to saved workflow file

    Raises:
        WorkflowGeneratorError: If save fails
    """
    # Create .orchestrator directory
    orchestrator_dir = repo_path / ".orchestrator"

    try:
        orchestrator_dir.mkdir(exist_ok=True)
    except PermissionError:
        raise WorkflowGeneratorError(
            f"Permission denied: Cannot create {orchestrator_dir}"
        )

    # Create .gitignore if it doesn't exist
    gitignore_path = orchestrator_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_content = """# Orchestrator runtime files
*.pid
*.log
server.log
enforce.log
"""
        gitignore_path.write_text(gitignore_content)

    # Save workflow YAML
    workflow_path = orchestrator_dir / "agent_workflow.yaml"

    try:
        workflow_path.write_text(content)
    except PermissionError:
        raise WorkflowGeneratorError(
            f"Permission denied: Cannot write to {workflow_path}"
        )

    return workflow_path

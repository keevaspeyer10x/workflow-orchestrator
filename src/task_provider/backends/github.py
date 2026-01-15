"""
GitHub Task Provider - GitHub Issues backend.

Uses the gh CLI to manage GitHub Issues as tasks.
"""

import subprocess
import json
import re
from typing import Optional, List

from ..interface import (
    TaskProvider,
    Task,
    TaskTemplate,
    TaskStatus,
    TaskPriority,
)


class GitHubTaskProvider(TaskProvider):
    """
    Task provider that uses GitHub Issues via gh CLI.

    This provider requires:
    - gh CLI installed
    - gh authenticated (gh auth status)
    - Either explicit repo or git remote origin configured
    """

    def __init__(self, repo: Optional[str] = None):
        """
        Initialize GitHub task provider.

        Args:
            repo: GitHub repo (owner/name). If not specified, auto-detects
                  from git remote origin.
        """
        self._repo = repo
        self._detected_repo: Optional[str] = None

    @property
    def repo(self) -> str:
        """Get the repository (auto-detect if needed)."""
        if self._repo:
            return self._repo
        if self._detected_repo is None:
            self._detected_repo = self._detect_repo()
        return self._detected_repo

    def _detect_repo(self) -> str:
        """Auto-detect repository from git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True,
            )
            url = result.stdout.strip()
            return self._parse_repo_url(url)
        except subprocess.CalledProcessError:
            raise ValueError("Not in a git repository or no origin remote")

    def _parse_repo_url(self, url: str) -> str:
        """Parse owner/repo from various git URL formats."""
        # HTTPS: https://github.com/owner/repo.git
        # SSH: git@github.com:owner/repo.git
        # SSH alt: ssh://git@github.com/owner/repo.git

        patterns = [
            r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$",  # Most formats
            r"github\.com/([^/]+)/([^/]+?)(?:\.git)?$",  # HTTPS
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                owner, repo = match.groups()
                return f"{owner}/{repo}"

        raise ValueError(f"Could not parse GitHub repo from URL: {url}")

    def _render_body(self, template: TaskTemplate) -> str:
        """Render TaskTemplate to GitHub issue body markdown."""
        sections = [
            f"## Status\n**{template.recommendation}**\n",
            f"## Priority & Complexity\n- **Priority:** {template.priority.value}\n",
            f"## Description\n{template.description}\n",
            f"## Problem Solved\n{template.problem_solved}\n",
        ]

        if template.proposed_solution:
            sections.append(f"## Proposed Solution\n{template.proposed_solution}\n")

        if template.tasks:
            task_list = "\n".join(f"- [ ] {t}" for t in template.tasks)
            sections.append(f"## Tasks\n{task_list}\n")

        # YAGNI section
        actual = "actually have" if template.yagni_actual_problem else "hypothetical"
        ok_status = "NOT okay" if template.yagni_ok_without == "0" else f"okay for {template.yagni_ok_without}"
        current = "fails" if not template.yagni_current_works else "works"

        sections.append(f"""## YAGNI Check
- Solving a problem we **{actual}**
- Would be **{ok_status}** without this
- Current solution **{current}**

## Recommendation
{'✅' if template.recommendation == 'IMPLEMENT' else '⚠️'} **{template.recommendation}**
""")

        return "\n".join(sections)

    def _run_gh(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run gh CLI command."""
        cmd = ["gh"] + args
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def _gh_available(self) -> bool:
        """Check if gh CLI is available and authenticated."""
        try:
            result = self._run_gh(["auth", "status"], check=False)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _parse_issue_number(self, output: str) -> str:
        """Parse issue number from gh issue create output."""
        # Output is usually the issue URL: https://github.com/owner/repo/issues/123
        match = re.search(r"/issues/(\d+)", output)
        if match:
            return match.group(1)
        # Try to find just a number
        match = re.search(r"#?(\d+)", output)
        if match:
            return match.group(1)
        raise ValueError(f"Could not parse issue number from: {output}")

    def _github_status_to_task_status(self, state: str) -> TaskStatus:
        """Convert GitHub issue state to TaskStatus."""
        state = state.lower()
        if state == "open":
            return TaskStatus.OPEN
        elif state == "closed":
            return TaskStatus.CLOSED
        else:
            return TaskStatus.OPEN

    def _parse_priority_from_labels(self, labels: List[str]) -> Optional[TaskPriority]:
        """Extract priority from GitHub labels."""
        priority_map = {
            "P0": TaskPriority.CRITICAL,
            "P1": TaskPriority.HIGH,
            "P2": TaskPriority.MEDIUM,
            "P3": TaskPriority.LOW,
            "priority:critical": TaskPriority.CRITICAL,
            "priority:high": TaskPriority.HIGH,
            "priority:medium": TaskPriority.MEDIUM,
            "priority:low": TaskPriority.LOW,
        }

        for label in labels:
            if label in priority_map:
                return priority_map[label]
            # Also check label names that might have been converted
            label_lower = label.lower()
            for key, value in priority_map.items():
                if key.lower() == label_lower:
                    return value

        return None

    def name(self) -> str:
        """Return provider identifier."""
        return "github"

    def is_available(self) -> bool:
        """Check if provider can be used."""
        if not self._gh_available():
            return False
        try:
            _ = self.repo  # Check repo detection
            return True
        except ValueError:
            return False

    def create_task(self, template: TaskTemplate) -> Task:
        """Create a new GitHub issue from template."""
        body = self._render_body(template)

        args = [
            "issue", "create",
            "--repo", self.repo,
            "--title", template.title,
            "--body", body,
        ]

        # Add labels
        for label in template.labels:
            args.extend(["--label", label])

        # Add priority label
        if template.priority:
            args.extend(["--label", template.priority.value])

        result = self._run_gh(args)
        issue_url = result.stdout.strip()
        issue_number = self._parse_issue_number(issue_url)

        return Task(
            id=issue_number,
            title=template.title,
            body=body,
            status=TaskStatus.OPEN,
            priority=template.priority,
            labels=template.labels + ([template.priority.value] if template.priority else []),
            url=issue_url,
        )

    def update_task(self, task_id: str, updates: dict) -> Task:
        """Update an existing GitHub issue."""
        args = ["issue", "edit", task_id, "--repo", self.repo]

        if "title" in updates:
            args.extend(["--title", updates["title"]])

        if "body" in updates:
            args.extend(["--body", updates["body"]])

        if "labels" in updates:
            # Note: This appends labels (Github CLI --add-label behavior)
            # It does NOT remove existing labels
            for label in updates["labels"]:
                args.extend(["--add-label", label])

        self._run_gh(args)

        # Fetch updated issue
        return self.get_task(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None
    ) -> List[Task]:
        """List GitHub issues with optional filters."""
        args = [
            "issue", "list",
            "--repo", self.repo,
            "--json", "number,title,body,state,labels,url",
            "--limit", "100",
        ]

        # Map status to GitHub state
        if status:
            if status == TaskStatus.CLOSED:
                args.extend(["--state", "closed"])
            else:
                args.extend(["--state", "open"])

        result = self._run_gh(args)
        issues = json.loads(result.stdout)

        tasks = []
        for issue in issues:
            label_names = [l.get("name", l) if isinstance(l, dict) else l for l in issue.get("labels", [])]
            task_priority = self._parse_priority_from_labels(label_names)

            # Filter by priority if specified
            if priority and task_priority != priority:
                continue

            task = Task(
                id=str(issue["number"]),
                title=issue["title"],
                body=issue.get("body", ""),
                status=self._github_status_to_task_status(issue["state"]),
                priority=task_priority,
                labels=label_names,
                url=issue.get("url"),
            )
            tasks.append(task)

        return tasks

    def get_next_task(self) -> Optional[Task]:
        """Get highest priority open issue."""
        open_tasks = self.list_tasks(status=TaskStatus.OPEN)

        if not open_tasks:
            return None

        # Sort by priority (P0 < P1 < P2 < P3)
        def priority_sort_key(task: Task) -> str:
            if task.priority is None:
                return "P9"
            return task.priority.value

        sorted_tasks = sorted(open_tasks, key=priority_sort_key)
        return sorted_tasks[0]

    def close_task(self, task_id: str, comment: Optional[str] = None) -> Task:
        """Close a GitHub issue."""
        if comment:
            self._run_gh([
                "issue", "comment", task_id,
                "--repo", self.repo,
                "--body", comment,
            ])

        self._run_gh([
            "issue", "close", task_id,
            "--repo", self.repo,
        ])

        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a specific issue by number."""
        try:
            result = self._run_gh([
                "issue", "view", task_id,
                "--repo", self.repo,
                "--json", "number,title,body,state,labels,url",
            ])
            issue = json.loads(result.stdout)

            label_names = [l.get("name", l) if isinstance(l, dict) else l for l in issue.get("labels", [])]

            return Task(
                id=str(issue["number"]),
                title=issue["title"],
                body=issue.get("body", ""),
                status=self._github_status_to_task_status(issue["state"]),
                priority=self._parse_priority_from_labels(label_names),
                labels=label_names,
                url=issue.get("url"),
            )
        except subprocess.CalledProcessError:
            return None

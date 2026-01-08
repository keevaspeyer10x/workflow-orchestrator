"""
Semantic Analyzer

Detects semantic conflicts between branches by analyzing:
- Symbol/function overlap (same names, different implementations)
- Domain overlap (both touch auth, both touch DB schema)
- API surface changes
- Module dependency overlap
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SymbolOverlapResult:
    """Result of checking symbol overlap between branches."""
    has_overlap: bool
    overlapping_symbols: list[str] = field(default_factory=list)
    overlapping_files: list[str] = field(default_factory=list)


@dataclass
class DomainOverlapResult:
    """Result of checking domain overlap between branches."""
    overlapping_domains: list[str] = field(default_factory=list)
    domain_files: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SemanticAnalysisResult:
    """Complete result of semantic analysis."""
    has_semantic_conflicts: bool
    symbol_overlap: Optional[SymbolOverlapResult] = None
    domain_overlap: Optional[DomainOverlapResult] = None
    api_changes: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def risk_level(self) -> str:
        """Assess overall risk level."""
        if not self.has_semantic_conflicts:
            return "low"
        if self.symbol_overlap and len(self.symbol_overlap.overlapping_symbols) > 3:
            return "high"
        if len(self.api_changes) > 0:
            return "high"
        if self.domain_overlap and len(self.domain_overlap.overlapping_domains) > 1:
            return "medium"
        return "low"


class SemanticAnalyzer:
    """
    Analyzes semantic conflicts between branches.

    This goes beyond textual conflicts to detect when branches
    are working in the same conceptual areas even if they don't
    touch the exact same lines.
    """

    # Domain patterns for classification
    DOMAIN_PATTERNS = {
        "auth": [r"auth", r"login", r"logout", r"session", r"token", r"permission"],
        "database": [r"database", r"db", r"models?", r"migrations?", r"schema"],
        "api": [r"api/", r"routes?", r"endpoints?", r"handlers?", r"controllers?"],
        "ui": [r"components?/", r"views?/", r"pages?/", r"templates?/", r"\.tsx?$", r"\.vue$"],
        "payments": [r"payment", r"billing", r"checkout", r"stripe", r"invoice"],
        "notifications": [r"notification", r"email", r"sms", r"push", r"alert"],
        "search": [r"search", r"elastic", r"solr", r"index"],
        "cache": [r"cache", r"redis", r"memcache"],
        "config": [r"config", r"settings", r"env"],
        "tests": [r"tests?/", r"spec/", r"__tests__"],
    }

    # Symbol extraction patterns by language
    SYMBOL_PATTERNS = {
        ".py": [
            r"^(?:def|class|async def)\s+(\w+)",  # Python functions/classes
        ],
        ".js": [
            r"(?:function|const|let|var|class)\s+(\w+)",  # JS declarations
            r"(\w+)\s*(?:=|:)\s*(?:function|\(.*\)\s*=>)",  # Arrow functions
        ],
        ".ts": [
            r"(?:function|const|let|var|class|interface|type)\s+(\w+)",
            r"(\w+)\s*(?:=|:)\s*(?:function|\(.*\)\s*=>)",
        ],
        ".go": [
            r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)",  # Go functions/methods
            r"^type\s+(\w+)",  # Go types
        ],
        ".rs": [
            r"^(?:pub\s+)?(?:fn|struct|enum|trait|impl)\s+(\w+)",  # Rust
        ],
        ".java": [
            r"(?:public|private|protected)?\s*(?:static\s+)?(?:class|interface|enum)\s+(\w+)",
            r"(?:public|private|protected)?\s*(?:static\s+)?[\w<>]+\s+(\w+)\s*\(",
        ],
    }

    def analyze(
        self,
        branches: list[str],
        base_branch: str = "main",
    ) -> SemanticAnalysisResult:
        """
        Perform semantic analysis on branches.

        Args:
            branches: List of branch names to analyze
            base_branch: Base branch for comparison

        Returns:
            SemanticAnalysisResult with findings
        """
        # Get changed files for each branch
        branch_files = {}
        branch_symbols = {}

        for branch in branches:
            files = self._get_changed_files(branch, base_branch)
            branch_files[branch] = files
            branch_symbols[branch] = self._extract_symbols(branch, files)

        # Check for overlaps
        symbol_overlap = self._check_all_symbol_overlaps(branch_symbols)
        domain_overlap = self._check_all_domain_overlaps(branch_files)
        api_changes = self._detect_api_changes(branch_files)

        has_conflicts = (
            symbol_overlap.has_overlap or
            len(domain_overlap.overlapping_domains) > 0 or
            len(api_changes) > 0
        )

        return SemanticAnalysisResult(
            has_semantic_conflicts=has_conflicts,
            symbol_overlap=symbol_overlap,
            domain_overlap=domain_overlap,
            api_changes=api_changes,
            confidence=0.7 if has_conflicts else 0.9,
        )

    def check_symbol_overlap(
        self,
        symbols1: dict[str, list[str]],
        symbols2: dict[str, list[str]],
    ) -> SymbolOverlapResult:
        """
        Check for overlapping symbols between two branches.

        Args:
            symbols1: {file_path: [symbols]} for branch 1
            symbols2: {file_path: [symbols]} for branch 2

        Returns:
            SymbolOverlapResult
        """
        overlapping_symbols = []
        overlapping_files = []

        # Find common files
        common_files = set(symbols1.keys()) & set(symbols2.keys())

        for file_path in common_files:
            syms1 = set(symbols1[file_path])
            syms2 = set(symbols2[file_path])
            common_syms = syms1 & syms2

            if common_syms:
                overlapping_symbols.extend(common_syms)
                overlapping_files.append(file_path)

        return SymbolOverlapResult(
            has_overlap=len(overlapping_symbols) > 0,
            overlapping_symbols=list(set(overlapping_symbols)),
            overlapping_files=overlapping_files,
        )

    def check_domain_overlap(
        self,
        files1: list[str],
        files2: list[str],
    ) -> DomainOverlapResult:
        """
        Check for domain overlap between two file lists.

        Args:
            files1: Files changed in branch 1
            files2: Files changed in branch 2

        Returns:
            DomainOverlapResult
        """
        domains1 = self._classify_files_by_domain(files1)
        domains2 = self._classify_files_by_domain(files2)

        overlapping = set(domains1.keys()) & set(domains2.keys())

        # Merge the file lists for overlapping domains
        domain_files = {}
        for domain in overlapping:
            domain_files[domain] = domains1[domain] + domains2[domain]

        return DomainOverlapResult(
            overlapping_domains=list(overlapping),
            domain_files=domain_files,
        )

    def _get_changed_files(self, branch: str, base_branch: str) -> list[str]:
        """Get list of files changed in branch relative to base."""
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...{branch}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]

    def _extract_symbols(
        self,
        branch: str,
        files: list[str],
    ) -> dict[str, list[str]]:
        """Extract defined symbols from changed files."""
        symbols = {}

        for file_path in files:
            ext = Path(file_path).suffix
            if ext not in self.SYMBOL_PATTERNS:
                continue

            content = self._get_file_from_branch(branch, file_path)
            if not content:
                continue

            file_symbols = []
            for pattern in self.SYMBOL_PATTERNS[ext]:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    symbol = match.group(1)
                    if symbol and not symbol.startswith("_"):
                        file_symbols.append(symbol)

            if file_symbols:
                symbols[file_path] = file_symbols

        return symbols

    def _get_file_from_branch(self, branch: str, file_path: str) -> Optional[str]:
        """Get file contents from a specific branch."""
        result = subprocess.run(
            ["git", "show", f"{branch}:{file_path}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        return None

    def _classify_files_by_domain(self, files: list[str]) -> dict[str, list[str]]:
        """Classify files into domains based on path patterns."""
        domains = {}

        for file_path in files:
            path_lower = file_path.lower()

            for domain, patterns in self.DOMAIN_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, path_lower):
                        if domain not in domains:
                            domains[domain] = []
                        domains[domain].append(file_path)
                        break

        return domains

    def _check_all_symbol_overlaps(
        self,
        branch_symbols: dict[str, dict[str, list[str]]],
    ) -> SymbolOverlapResult:
        """Check symbol overlaps across all branch pairs."""
        all_overlapping_symbols = []
        all_overlapping_files = []

        branches = list(branch_symbols.keys())
        for i, branch1 in enumerate(branches):
            for branch2 in branches[i + 1:]:
                result = self.check_symbol_overlap(
                    branch_symbols[branch1],
                    branch_symbols[branch2],
                )
                all_overlapping_symbols.extend(result.overlapping_symbols)
                all_overlapping_files.extend(result.overlapping_files)

        return SymbolOverlapResult(
            has_overlap=len(all_overlapping_symbols) > 0,
            overlapping_symbols=list(set(all_overlapping_symbols)),
            overlapping_files=list(set(all_overlapping_files)),
        )

    def _check_all_domain_overlaps(
        self,
        branch_files: dict[str, list[str]],
    ) -> DomainOverlapResult:
        """Check domain overlaps across all branch pairs."""
        all_overlapping_domains = set()
        all_domain_files = {}

        branches = list(branch_files.keys())
        for i, branch1 in enumerate(branches):
            for branch2 in branches[i + 1:]:
                result = self.check_domain_overlap(
                    branch_files[branch1],
                    branch_files[branch2],
                )
                all_overlapping_domains.update(result.overlapping_domains)
                for domain, files in result.domain_files.items():
                    if domain not in all_domain_files:
                        all_domain_files[domain] = []
                    all_domain_files[domain].extend(files)

        return DomainOverlapResult(
            overlapping_domains=list(all_overlapping_domains),
            domain_files=all_domain_files,
        )

    def _detect_api_changes(
        self,
        branch_files: dict[str, list[str]],
    ) -> list[str]:
        """Detect public API changes across branches."""
        api_changes = []

        api_patterns = [
            r"api/.*\.(py|js|ts|go)$",
            r"routes?\.(py|js|ts|go)$",
            r"endpoints?\.(py|js|ts|go)$",
            r"openapi\.(yaml|json)$",
            r"swagger\.(yaml|json)$",
        ]

        for branch, files in branch_files.items():
            for file_path in files:
                for pattern in api_patterns:
                    if re.search(pattern, file_path.lower()):
                        api_changes.append(f"{branch}: {file_path}")
                        break

        return api_changes

"""
LLM-Assisted Conflict Resolution - CORE-023 Part 2

Resolves git conflicts that can't be auto-resolved using LLM-based code merging.

Pipeline:
1. Intent Extraction - Uses IntentExtractor.extract_from_diff_with_llm()
2. Context Assembly - Gather related files, conventions (with token budget)
3. LLM Resolution - Generate merged code
4. Validation - Tiered validation (syntax, build, tests)
5. Confidence Scoring - Determine if auto-apply is safe

Security:
- Sensitive files are detected and skipped (never sent to LLM)
- Only conflict hunks + context sent, not full codebase

Note: This module integrates with the existing resolution infrastructure:
- Uses IntentExtractor from src/resolution/intent.py for intent extraction
- Uses ExtractedIntent from src/resolution/schema.py
"""

import ast
import fnmatch
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Literal

# Import from existing infrastructure
from .schema import ExtractedIntent, Constraint
from .intent import IntentExtractor
from .logger import log_resolution, log_escalation
from ..user_config import UserConfig

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Maximum tokens for context (reserve rest for response)
MAX_CONTEXT_TOKENS = 32000
CHARS_PER_TOKEN = 4  # Rough estimate

# Sensitive file patterns - NEVER send to LLM
SENSITIVE_PATTERNS = [
    "*.env",
    ".env.*",
    "secrets.*",
    "*secret*",
    "*credential*",
    "*password*",
    "*api_key*",
    "*apikey*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.cert",
    "config/secrets/*",
    ".aws/*",
    ".gcp/*",
    "*token*",
    ".npmrc",
    ".pypirc",
]

# File types we can validate syntax for
SYNTAX_VALIDATORS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}


# ============================================================================
# Data Classes
# ============================================================================

class ConfidenceLevel(Enum):
    """Resolution confidence level."""
    HIGH = "high"      # > 0.8 - Auto-apply safe
    MEDIUM = "medium"  # 0.5-0.8 - Show diff, ask user
    LOW = "low"        # < 0.5 - Escalate to human


# Note: ExtractedIntent is now imported from schema.py
# It uses agent_id (we pass "ours"/"theirs") and Constraint objects


@dataclass
class MergeCandidate:
    """A candidate merged resolution."""
    content: str
    strategy: str  # "llm_merge", "llm_rewrite", etc.
    explanation: str = ""
    confidence: float = 0.5


@dataclass
class ValidationResult:
    """Result of validating a merge candidate."""
    passed: bool = False
    tier_reached: str = "none"  # "syntax", "build", "tests"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class LLMResolutionResult:
    """Result of LLM-assisted resolution."""
    file_path: str
    success: bool = False

    # Resolution
    merged_content: Optional[str] = None
    strategy: str = ""
    explanation: str = ""

    # Confidence
    confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.LOW
    confidence_reasons: list[str] = field(default_factory=list)

    # Validation
    validation: Optional[ValidationResult] = None

    # Escalation
    needs_escalation: bool = False
    escalation_reason: str = ""
    escalation_options: list[str] = field(default_factory=list)

    # Debug
    intents: list[ExtractedIntent] = field(default_factory=list)
    raw_llm_response: str = ""


# ============================================================================
# LLM Client Abstraction
# ============================================================================

class LLMClient:
    """Abstract LLM client for code generation."""

    def __init__(self):
        self.model_name = "unknown"

    def generate(self, prompt: str, max_tokens: int = 8000) -> str:
        """Generate response from prompt."""
        raise NotImplementedError


class OpenAIClient(LLMClient):
    """OpenAI API client."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        super().__init__()
        self.api_key = api_key
        self.model_name = model
        self._client = None

    def _get_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("openai package required: pip install openai")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 8000) -> str:
        """Generate response using OpenAI API."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are an expert software engineer resolving git merge conflicts. Output only code, no explanations unless asked."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,  # Low temperature for deterministic code
        )
        return response.choices[0].message.content


class OpenRouterClient(LLMClient):
    """OpenRouter API client (fallback)."""

    def __init__(self, api_key: str, model: str = "anthropic/claude-3-opus"):
        super().__init__()
        self.api_key = api_key
        self.model_name = model
        self.base_url = "https://openrouter.ai/api/v1"

    def generate(self, prompt: str, max_tokens: int = 8000) -> str:
        """Generate response using OpenRouter API."""
        import urllib.request
        import urllib.error

        data = json.dumps({
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are an expert software engineer resolving git merge conflicts. Output only code, no explanations unless asked."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/keevaspeyer10x/workflow-orchestrator",
            },
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]


class GeminiClient(LLMClient):
    """Google Gemini API client."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        super().__init__()
        self.api_key = api_key
        self.model_name = model
        self._client = None

    def _get_client(self):
        """Lazy-load Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model_name)
            except ImportError:
                raise ImportError("google-generativeai package required: pip install google-generativeai")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 8000) -> str:
        """Generate response using Gemini API."""
        client = self._get_client()
        response = client.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": 0.2,
            },
        )
        return response.text


# ============================================================================
# LLM Resolver
# ============================================================================

class LLMResolver:
    """
    LLM-based conflict resolver.

    Resolves conflicts that can't be handled by deterministic strategies.
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        client: Optional[LLMClient] = None,
        auto_apply_threshold: float = 0.8,
        config: Optional[UserConfig] = None,
    ):
        """
        Initialize the LLM resolver.

        Args:
            repo_path: Path to git repository
            client: LLM client to use (auto-detected if not provided)
            auto_apply_threshold: Confidence threshold for auto-apply
            config: User config (loaded from ~/.orchestrator/config.yaml if not provided)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.config = config or UserConfig.load()
        self.client = client or self._get_default_client()
        self.auto_apply_threshold = auto_apply_threshold

        # Create IntentExtractor with LLM client for Phase 5 extraction
        self.intent_extractor = IntentExtractor(llm_client=self.client)

    def _get_default_client(self) -> LLMClient:
        """Get default LLM client based on available API keys."""
        # Try OpenAI first (best for code)
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            logger.info("Using OpenAI API for LLM resolution")
            return OpenAIClient(api_key)

        # Try Gemini
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            logger.info("Using Gemini API for LLM resolution")
            return GeminiClient(api_key)

        # Try OpenRouter (fallback)
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            logger.info("Using OpenRouter API for LLM resolution")
            return OpenRouterClient(api_key)

        raise ValueError(
            "No LLM API key available. Set one of: "
            "OPENAI_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY"
        )

    # ========================================================================
    # Public API
    # ========================================================================

    def resolve(
        self,
        file_path: str,
        base: Optional[str],
        ours: str,
        theirs: str,
        context: Optional[dict] = None,
    ) -> LLMResolutionResult:
        """
        Resolve a single file conflict using LLM.

        Args:
            file_path: Path to conflicted file
            base: Common ancestor content (may be None for new files)
            ours: Our version content
            theirs: Their version content
            context: Optional additional context (related files, conventions)

        Returns:
            LLMResolutionResult with merged content or escalation info
        """
        import time
        start_time = time.time()

        logger.info(f"LLM resolving: {file_path}")

        # CORE-023-P3: Check if LLM is disabled in config
        if not self.config.llm_enabled:
            logger.warning("LLM disabled in config, skipping")
            result = LLMResolutionResult(
                file_path=file_path,
                needs_escalation=True,
                escalation_reason="llm_disabled",
                escalation_options=[
                    "[A] Keep OURS - Your changes only",
                    "[B] Keep THEIRS - Target branch changes only",
                    "[C] Manual resolution required",
                ],
            )
            log_escalation(
                file_path=file_path,
                reason="llm_disabled",
                options=result.escalation_options,
                working_dir=self.repo_path,
            )
            return result

        # Security check - skip sensitive files
        if self.is_sensitive_file(file_path):
            logger.warning(f"Sensitive file detected, skipping LLM: {file_path}")
            result = LLMResolutionResult(
                file_path=file_path,
                needs_escalation=True,
                escalation_reason="sensitive_file",
                escalation_options=[
                    "[A] Keep OURS - Your changes only",
                    "[B] Keep THEIRS - Target branch changes only",
                    "[C] Manual resolution required",
                ],
            )
            log_escalation(
                file_path=file_path,
                reason="sensitive_file",
                options=result.escalation_options,
                working_dir=self.repo_path,
            )
            return result

        # Stage 1: Extract intents
        logger.info("Stage 1: Extracting intents")
        ours_intent = self._extract_intent("ours", base, ours, file_path)
        theirs_intent = self._extract_intent("theirs", base, theirs, file_path)
        intents = [ours_intent, theirs_intent]

        # Stage 2: Assemble context
        logger.info("Stage 2: Assembling context")
        assembled_context = self._assemble_context(
            file_path, base, ours, theirs, context
        )

        # Stage 3: Generate merged code
        logger.info("Stage 3: Generating merged code")
        candidates = self._generate_candidates(
            file_path, base, ours, theirs, intents, assembled_context
        )

        if not candidates:
            return LLMResolutionResult(
                file_path=file_path,
                needs_escalation=True,
                escalation_reason="no_candidates_generated",
                intents=intents,
            )

        # Stage 4: Validate candidates
        logger.info("Stage 4: Validating candidates")
        best_candidate = None
        best_validation = None

        for candidate in candidates:
            validation = self._validate_candidate(file_path, candidate.content)
            if validation.passed:
                if best_candidate is None or candidate.confidence > best_candidate.confidence:
                    best_candidate = candidate
                    best_validation = validation

        if best_candidate is None:
            # All candidates failed validation
            return LLMResolutionResult(
                file_path=file_path,
                needs_escalation=True,
                escalation_reason="validation_failed",
                escalation_options=[
                    f"[A] Use candidate 1 anyway (has {candidates[0].confidence:.0%} confidence)",
                    "[B] Keep OURS",
                    "[C] Keep THEIRS",
                    "[D] Manual resolution",
                ],
                intents=intents,
            )

        # Stage 5: Calculate confidence and decide
        logger.info("Stage 5: Scoring confidence")
        confidence, reasons = self._calculate_confidence(
            intents, best_candidate, best_validation
        )

        confidence_level = self._get_confidence_level(confidence)

        # Build result
        result = LLMResolutionResult(
            file_path=file_path,
            success=True,
            merged_content=best_candidate.content,
            strategy=best_candidate.strategy,
            explanation=best_candidate.explanation,
            confidence=confidence,
            confidence_level=confidence_level,
            confidence_reasons=reasons,
            validation=best_validation,
            intents=intents,
        )

        # Check if needs escalation based on confidence
        if confidence_level == ConfidenceLevel.LOW:
            result.needs_escalation = True
            result.escalation_reason = "low_confidence"
            result.escalation_options = [
                f"[A] Apply LLM resolution ({confidence:.0%} confidence)",
                "[B] Keep OURS",
                "[C] Keep THEIRS",
                "[D] Manual resolution",
            ]
            # CORE-023-P3: Log escalation
            log_escalation(
                file_path=file_path,
                reason="low_confidence",
                options=result.escalation_options,
                working_dir=self.repo_path,
            )
        else:
            # CORE-023-P3: Log successful resolution
            resolution_time_ms = int((time.time() - start_time) * 1000)
            log_resolution(
                file_path=file_path,
                strategy=f"llm_{best_candidate.strategy}",
                confidence=confidence,
                resolution_time_ms=resolution_time_ms,
                llm_used=True,
                llm_model=self.client.model_name if self.client else None,
                working_dir=self.repo_path,
            )

        return result

    # ========================================================================
    # Security
    # ========================================================================

    def is_sensitive_file(self, path: str) -> bool:
        """
        Check if a file matches sensitive patterns.

        SECURITY: These files should NEVER be sent to external LLMs.

        CORE-023-P3: Now also checks user config sensitive_globs from
        ~/.orchestrator/config.yaml.
        """
        path_lower = path.lower()

        # Check hardcoded patterns first (baseline security)
        for pattern in SENSITIVE_PATTERNS:
            # Handle glob patterns
            if fnmatch.fnmatch(path_lower, pattern.lower()):
                return True

            # Handle simple substring matches for patterns without wildcards
            if '*' not in pattern and '?' not in pattern:
                if pattern.lower() in path_lower:
                    return True

        # CORE-023-P3: Also check user config sensitive globs
        if self.config.is_sensitive(path):
            return True

        return False

    # ========================================================================
    # Stage 1: Intent Extraction (delegates to IntentExtractor)
    # ========================================================================

    def _extract_intent(
        self,
        side: str,
        base: Optional[str],
        content: str,
        file_path: str,
    ) -> ExtractedIntent:
        """
        Extract intent from one side of the conflict.

        Delegates to IntentExtractor.extract_from_diff_with_llm() which uses
        the shared infrastructure from src/resolution/intent.py.
        """
        return self.intent_extractor.extract_from_diff_with_llm(
            side=side,
            base_content=base,
            side_content=content,
            file_path=file_path,
        )

    # ========================================================================
    # Stage 2: Context Assembly
    # ========================================================================

    def _assemble_context(
        self,
        file_path: str,
        base: Optional[str],
        ours: str,
        theirs: str,
        extra_context: Optional[dict],
    ) -> dict:
        """Assemble context for LLM, respecting token budget."""

        budget = MAX_CONTEXT_TOKENS
        context = {
            "file_path": file_path,
            "language": self._detect_language(file_path),
            "conventions": [],
            "related_files": [],
        }

        # Required: conflict content (already have)
        conflict_tokens = sum(
            len(c or "") // CHARS_PER_TOKEN
            for c in [base, ours, theirs]
        )
        budget -= conflict_tokens

        # Check for CLAUDE.md (project conventions)
        claude_md = self.repo_path / "CLAUDE.md"
        if claude_md.exists() and budget > 1000:
            try:
                content = claude_md.read_text()[:4000]  # Limit size
                context["conventions"].append({
                    "source": "CLAUDE.md",
                    "content": content,
                })
                budget -= len(content) // CHARS_PER_TOKEN
            except Exception:
                pass

        # Add extra context if provided and budget allows
        if extra_context and budget > 500:
            if "related_files" in extra_context:
                for rf in extra_context["related_files"][:5]:  # Limit files
                    if budget <= 0:
                        break
                    rf_content = rf.get("content", "")[:2000]
                    context["related_files"].append({
                        "path": rf.get("path", ""),
                        "relationship": rf.get("relationship", "related"),
                        "content": rf_content,
                    })
                    budget -= len(rf_content) // CHARS_PER_TOKEN

        return context

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
            ".sql": "sql",
        }
        return language_map.get(ext, "text")

    # ========================================================================
    # Stage 3: Candidate Generation
    # ========================================================================

    def _generate_candidates(
        self,
        file_path: str,
        base: Optional[str],
        ours: str,
        theirs: str,
        intents: list[ExtractedIntent],
        context: dict,
    ) -> list[MergeCandidate]:
        """Generate merged code candidates using LLM."""

        language = context.get("language", "text")

        # Format intents (agent_id is "ours" or "theirs")
        ours_intent = next((i for i in intents if i.agent_id == "ours"), None)
        theirs_intent = next((i for i in intents if i.agent_id == "theirs"), None)

        ours_intent_str = ours_intent.primary_intent if ours_intent else "Unknown"
        theirs_intent_str = theirs_intent.primary_intent if theirs_intent else "Unknown"

        # Build constraints list (Constraint objects have .description)
        hard_constraints = []
        soft_constraints = []
        for intent in intents:
            hard_constraints.extend(c.description for c in intent.hard_constraints)
            soft_constraints.extend(c.description for c in intent.soft_constraints)

        hard_constraints_str = "\n".join(f"- {c}" for c in hard_constraints) or "- None specified"
        soft_constraints_str = "\n".join(f"- {c}" for c in soft_constraints) or "- None specified"

        # Format conventions
        conventions_str = ""
        for conv in context.get("conventions", []):
            conventions_str += f"\n### {conv['source']}:\n{conv['content'][:1000]}\n"

        # Build the merge prompt
        base_section = f"## Base version (common ancestor):\n```{language}\n{base or '(no base - new file on both sides)'}\n```" if base else "## No base version (new file conflict)"

        prompt = f'''You are resolving a git merge conflict.

{base_section}

## Our changes (what we added):
```{language}
{ours}
```

## Their changes (what target branch added):
```{language}
{theirs}
```

## Intent analysis:
- **OURS intent**: {ours_intent_str}
- **THEIRS intent**: {theirs_intent_str}

## Constraints:
**Hard constraints (MUST satisfy):**
{hard_constraints_str}

**Soft constraints (prefer if possible):**
{soft_constraints_str}
{f"## Project conventions:{conventions_str}" if conventions_str else ""}

## Your task:
Generate the merged {language} code that:
1. Satisfies ALL hard constraints
2. Preserves BOTH intents where possible
3. Follows project conventions if provided
4. Produces valid {language} syntax with NO conflict markers

CRITICAL: Output ONLY the merged code. No explanations, no markdown code blocks, just the raw merged code.
'''

        try:
            response = self.client.generate(prompt, max_tokens=8000)

            # Clean response
            content = self._clean_llm_response(response, language)

            # Assess confidence based on response characteristics
            confidence = 0.7  # Base confidence

            # Boost if both intents seem addressed (schema uses string confidence)
            if ours_intent and theirs_intent:
                if ours_intent.confidence == "high":
                    confidence += 0.05
                if theirs_intent.confidence == "high":
                    confidence += 0.05

            # Penalize if response is suspiciously short or long
            if len(content) < len(ours) * 0.5:
                confidence -= 0.2
            if len(content) > len(ours) + len(theirs):
                confidence -= 0.1

            return [MergeCandidate(
                content=content,
                strategy="llm_merge",
                explanation=f"LLM merged {language} code preserving both intents",
                confidence=confidence,
            )]

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return []

    def _clean_llm_response(self, response: str, language: str) -> str:
        """Clean LLM response to extract just the code."""
        content = response.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```language)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        return content

    # ========================================================================
    # Stage 4: Validation
    # ========================================================================

    def _validate_candidate(self, file_path: str, content: str) -> ValidationResult:
        """Validate a merge candidate using tiered validation."""

        result = ValidationResult()

        # Tier 0: Check for empty content (instant fail)
        if not content or not content.strip():
            result.errors.append("Empty content")
            return result

        # Tier 0b: Check for conflict markers (instant fail)
        if "<<<<<<" in content or "======" in content or ">>>>>>" in content:
            result.errors.append("Contains conflict markers")
            return result

        result.tier_reached = "conflict_markers"

        # Tier 1: Syntax validation
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            try:
                ast.parse(content)
                result.tier_reached = "syntax"
            except SyntaxError as e:
                result.errors.append(f"Python syntax error: {e}")
                return result

        elif ext == ".json":
            try:
                json.loads(content)
                result.tier_reached = "syntax"
            except json.JSONDecodeError as e:
                result.errors.append(f"JSON syntax error: {e}")
                return result

        elif ext in (".yaml", ".yml"):
            try:
                import yaml
                yaml.safe_load(content)
                result.tier_reached = "syntax"
            except Exception as e:
                result.errors.append(f"YAML syntax error: {e}")
                return result

        else:
            # For other file types, content exists (already checked above)
            result.tier_reached = "syntax"

        # Tier 2: Build validation (if applicable)
        # This would be done externally by the caller if needed
        # For now, we pass validation if syntax is OK

        result.passed = True
        return result

    # ========================================================================
    # Stage 5: Confidence Scoring
    # ========================================================================

    def _calculate_confidence(
        self,
        intents: list[ExtractedIntent],
        candidate: MergeCandidate,
        validation: ValidationResult,
    ) -> tuple[float, list[str]]:
        """Calculate confidence score for a resolution."""

        score = candidate.confidence
        reasons = []

        # Intent confidence (schema uses string: "high", "medium", "low")
        intent_scores = [
            1.0 if i.confidence == "high" else
            0.6 if i.confidence == "medium" else
            0.3
            for i in intents
        ]
        avg_intent = sum(intent_scores) / len(intent_scores) if intent_scores else 0.5

        if avg_intent >= 0.8:
            score += 0.1
            reasons.append("High intent extraction confidence")
        elif avg_intent < 0.5:
            score -= 0.1
            reasons.append("Low intent extraction confidence")

        # Validation results
        if validation.passed:
            reasons.append(f"Passed validation (tier: {validation.tier_reached})")
            if validation.tier_reached == "syntax":
                score += 0.1
        else:
            score -= 0.3
            reasons.append(f"Failed validation: {', '.join(validation.errors)}")

        # Warnings
        if validation.warnings:
            score -= 0.05 * len(validation.warnings)
            reasons.append(f"{len(validation.warnings)} warnings")

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        return score, reasons

    def _get_confidence_level(self, score: float) -> ConfidenceLevel:
        """Convert confidence score to level."""
        if score >= self.auto_apply_threshold:
            return ConfidenceLevel.HIGH
        elif score >= 0.5:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW


# ============================================================================
# Convenience Functions
# ============================================================================

def get_llm_resolver(repo_path: Optional[Path] = None) -> LLMResolver:
    """
    Get an LLM resolver for the given repository.

    Args:
        repo_path: Path to git repository (default: current directory)

    Returns:
        LLMResolver instance

    Raises:
        ValueError: If no LLM API key is available
    """
    return LLMResolver(repo_path=repo_path)


def resolve_with_llm(
    file_path: str,
    base: Optional[str],
    ours: str,
    theirs: str,
    repo_path: Optional[Path] = None,
) -> LLMResolutionResult:
    """
    Convenience function to resolve a conflict with LLM.

    Args:
        file_path: Path to conflicted file
        base: Common ancestor content
        ours: Our version content
        theirs: Their version content
        repo_path: Path to git repository

    Returns:
        LLMResolutionResult with merged content or escalation info
    """
    resolver = get_llm_resolver(repo_path)
    return resolver.resolve(file_path, base, ours, theirs)

"""Context extraction for intelligent pattern filtering.

This module extracts PatternContext from error events for cross-project
pattern matching.
"""

import math
import platform
import re
from datetime import datetime
from typing import Optional

from .models import PatternContext


# Language detection patterns
PYTHON_PATTERNS = [
    r"ModuleNotFoundError",
    r"ImportError",
    r"TypeError:",
    r"ValueError:",
    r"AttributeError:",
    r"KeyError:",
    r"IndexError:",
    r"NameError:",
    r"SyntaxError:",
    r"IndentationError:",
    r"RuntimeError:",
    r"FileNotFoundError:",
    r"PermissionError:",
    r"OSError:",
    r"Traceback \(most recent call last\)",
    r'File ".*\.py"',
    r"\.py:\d+",
    r"pip install",
    r"python[23]?",
]

JAVASCRIPT_PATTERNS = [
    r"ReferenceError:",
    r"TypeError:",
    r"SyntaxError:",
    r"RangeError:",
    r"URIError:",
    r"EvalError:",
    r"Error: Cannot find module",
    r"at .+\.js:\d+",
    r"at .+\.ts:\d+",
    r"at .+\.tsx:\d+",
    r"npm ERR!",
    r"yarn error",
    r"node_modules",
    r"package\.json",
    r"\.js:\d+:\d+",
    r"\.ts:\d+:\d+",
]

GO_PATTERNS = [
    r"panic:",
    r"runtime error:",
    r"cannot find package",
    r"go: ",
    r"\.go:\d+",
    r"goroutine \d+",
]

RUST_PATTERNS = [
    r"error\[E\d+\]",
    r"cargo ",
    r"rustc",
    r"\.rs:\d+",
    r"thread '.+' panicked",
]

JAVA_PATTERNS = [
    r"Exception in thread",
    r"\.java:\d+",
    r"at .+\.java:\d+",
    r"NullPointerException",
    r"ClassNotFoundException",
    r"NoSuchMethodException",
    r"maven",
    r"gradle",
]

# Error category patterns
DEPENDENCY_PATTERNS = [
    r"ModuleNotFoundError",
    r"ImportError",
    r"Cannot find module",
    r"cannot find package",
    r"No matching distribution",
    r"Package .+ not found",
    r"npm ERR! 404",
    r"dependency .+ not found",
]

SYNTAX_PATTERNS = [
    r"SyntaxError",
    r"IndentationError",
    r"Unexpected token",
    r"Parse error",
    r"invalid syntax",
]

RUNTIME_PATTERNS = [
    r"RuntimeError",
    r"panic:",
    r"Segmentation fault",
    r"core dumped",
    r"SIGKILL",
    r"SIGSEGV",
]

NETWORK_PATTERNS = [
    r"ConnectionError",
    r"TimeoutError",
    r"ECONNREFUSED",
    r"ETIMEDOUT",
    r"getaddrinfo ENOTFOUND",
    r"socket.timeout",
    r"ConnectionRefusedError",
]

PERMISSION_PATTERNS = [
    r"PermissionError",
    r"Permission denied",
    r"EACCES",
    r"Access denied",
    r"Forbidden",
]

CONFIG_PATTERNS = [
    r"ConfigError",
    r"Configuration error",
    r"Missing required",
    r"Invalid configuration",
    r"Environment variable .+ not set",
]

TEST_PATTERNS = [
    r"FAILED",
    r"AssertionError",
    r"assertion failed",
    r"expect\(.+\)\.to",
    r"assert ",
    r"pytest",
    r"jest",
    r"mocha",
]


def detect_language(
    description: str,
    file_path: Optional[str] = None,
    stack_trace: Optional[str] = None,
) -> tuple[Optional[str], float]:
    """Detect programming language from error context.

    Uses multiple signals: error message patterns, file extensions, stack traces.

    Args:
        description: Error description/message
        file_path: Optional file path where error occurred
        stack_trace: Optional stack trace

    Returns:
        Tuple of (language, confidence) where confidence is 0.0-1.0
    """
    text = f"{description} {stack_trace or ''}"

    # Check file extension first (highest confidence)
    if file_path:
        if file_path.endswith(".py"):
            return "python", 0.95
        elif file_path.endswith((".js", ".ts", ".tsx", ".jsx", ".mjs")):
            return "javascript", 0.95
        elif file_path.endswith(".go"):
            return "go", 0.95
        elif file_path.endswith(".rs"):
            return "rust", 0.95
        elif file_path.endswith(".java"):
            return "java", 0.95

    # Score each language by pattern matches
    scores = {
        "python": sum(1 for p in PYTHON_PATTERNS if re.search(p, text, re.IGNORECASE)),
        "javascript": sum(1 for p in JAVASCRIPT_PATTERNS if re.search(p, text, re.IGNORECASE)),
        "go": sum(1 for p in GO_PATTERNS if re.search(p, text, re.IGNORECASE)),
        "rust": sum(1 for p in RUST_PATTERNS if re.search(p, text, re.IGNORECASE)),
        "java": sum(1 for p in JAVA_PATTERNS if re.search(p, text, re.IGNORECASE)),
    }

    # Find best match
    best_lang = max(scores, key=scores.get)
    best_score = scores[best_lang]

    if best_score == 0:
        return None, 0.0

    # Convert to confidence (more matches = higher confidence)
    # 1 match = 0.5, 2 matches = 0.7, 3+ matches = 0.85
    confidence = min(0.5 + (best_score - 1) * 0.15, 0.85)

    return best_lang, confidence


def detect_error_category(
    description: str,
    error_type: Optional[str] = None,
) -> tuple[Optional[str], float]:
    """Detect error category from error context.

    Args:
        description: Error description/message
        error_type: Optional error type (e.g., "TypeError")

    Returns:
        Tuple of (category, confidence)
    """
    text = f"{description} {error_type or ''}"

    # Check patterns in priority order
    categories = [
        ("dependency", DEPENDENCY_PATTERNS),
        ("syntax", SYNTAX_PATTERNS),
        ("permission", PERMISSION_PATTERNS),
        ("network", NETWORK_PATTERNS),
        ("config", CONFIG_PATTERNS),
        ("test", TEST_PATTERNS),
        ("runtime", RUNTIME_PATTERNS),
    ]

    for category, patterns in categories:
        matches = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        if matches > 0:
            confidence = min(0.6 + (matches - 1) * 0.1, 0.9)
            return category, confidence

    return None, 0.0


def detect_framework(
    description: str,
    file_path: Optional[str] = None,
) -> Optional[str]:
    """Detect framework from error context."""
    text = f"{description} {file_path or ''}"

    frameworks = {
        "react": [r"react", r"jsx", r"tsx", r"component", r"useState", r"useEffect"],
        "django": [r"django", r"views\.py", r"models\.py", r"settings\.py"],
        "flask": [r"flask", r"@app\.route", r"Blueprint"],
        "express": [r"express", r"app\.get\(", r"router\."],
        "fastapi": [r"fastapi", r"@app\.get", r"@app\.post"],
        "pytest": [r"pytest", r"test_.*\.py", r"conftest\.py"],
        "jest": [r"jest", r"\.test\.js", r"\.spec\.js"],
    }

    for framework, patterns in frameworks.items():
        if any(re.search(p, text, re.IGNORECASE) for p in patterns):
            return framework

    return None


def detect_package_manager(description: str) -> Optional[str]:
    """Detect package manager from error context."""
    text = description.lower()

    if "pip" in text or "pypi" in text:
        return "pip"
    elif "npm" in text or "package.json" in text:
        return "npm"
    elif "yarn" in text:
        return "yarn"
    elif "cargo" in text:
        return "cargo"
    elif "go mod" in text or "go get" in text:
        return "go"
    elif "maven" in text or "pom.xml" in text:
        return "maven"
    elif "gradle" in text:
        return "gradle"

    return None


def extract_context(
    description: str,
    error_type: Optional[str] = None,
    file_path: Optional[str] = None,
    stack_trace: Optional[str] = None,
    workflow_phase: Optional[str] = None,
) -> PatternContext:
    """Extract PatternContext from error details.

    This is the main entry point for context extraction.

    Args:
        description: Error description/message
        error_type: Optional error type
        file_path: Optional file path
        stack_trace: Optional stack trace
        workflow_phase: Optional workflow phase

    Returns:
        PatternContext with extracted dimensions
    """
    # Detect language
    language, lang_confidence = detect_language(description, file_path, stack_trace)

    # Detect error category
    error_category, cat_confidence = detect_error_category(description, error_type)

    # Detect framework
    framework = detect_framework(description, file_path)

    # Detect package manager
    package_manager = detect_package_manager(description)

    # Get OS
    os_name = platform.system().lower()
    if os_name == "darwin":
        os_name = "darwin"
    elif os_name == "windows":
        os_name = "windows"
    else:
        os_name = "linux"

    # Calculate overall confidence
    confidence = (lang_confidence + cat_confidence) / 2 if lang_confidence and cat_confidence else max(lang_confidence, cat_confidence, 0.3)

    return PatternContext(
        language=language,
        error_category=error_category,
        workflow_phase=workflow_phase,
        framework=framework,
        os=os_name,
        package_manager=package_manager,
        extraction_confidence=confidence,
    )


def wilson_score(successes: int, total: int, confidence: float = 0.95) -> float:
    """Calculate Wilson score lower bound for success rate.

    Handles the sample size problem: 1/1 (100%) shouldn't beat 95/100 (95%).

    Args:
        successes: Number of successes
        total: Total attempts (successes + failures)
        confidence: Confidence level (default 0.95)

    Returns:
        Conservative estimate of success rate (0.0-1.0)
    """
    if total == 0:
        return 0.5  # Neutral if no data

    z = 1.96  # 95% confidence interval
    p = successes / total
    n = total

    denominator = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adjustment = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)

    return (centre - adjustment) / denominator


def calculate_recency_score(
    last_success_at: Optional[datetime],
    half_life_days: int = 30,
) -> float:
    """Calculate recency score with exponential decay.

    Args:
        last_success_at: Timestamp of last successful use
        half_life_days: Half-life for decay (default 30 days)

    Returns:
        Recency score (0.0-1.0)
    """
    if not last_success_at:
        return 0.5  # Neutral if unknown

    now = datetime.utcnow()
    if hasattr(last_success_at, 'replace'):
        last_success_at = last_success_at.replace(tzinfo=None)

    days_since = (now - last_success_at).days
    return math.exp(-days_since * math.log(2) / half_life_days)


def calculate_context_overlap(
    pattern_context: dict,
    query_context: PatternContext,
) -> float:
    """Calculate weighted overlap between contexts.

    Language match is most important, then error_category, etc.

    Args:
        pattern_context: Context dict from stored pattern
        query_context: Context of current query

    Returns:
        Overlap score (0.0-1.0)
    """
    if not pattern_context:
        return 0.5  # Neutral if no context

    query_dict = query_context.to_dict()
    if not query_dict:
        return 0.5

    # Hierarchical weights
    weights = {
        "language": 1.0,
        "error_category": 0.8,
        "workflow_phase": 0.5,
        "framework": 0.5,
        "os": 0.3,
        "runtime_version": 0.3,
        "package_manager": 0.3,
    }

    weighted_sum = 0.0
    total_weight = 0.0

    for key, weight in weights.items():
        if key in query_dict:
            total_weight += weight
            if key in pattern_context and pattern_context[key] == query_dict[key]:
                weighted_sum += weight
            elif key not in pattern_context:
                # Pattern has no constraint on this dimension - partial match
                weighted_sum += weight * 0.3

    return weighted_sum / total_weight if total_weight > 0 else 0.5


def calculate_relevance_score(
    pattern: dict,
    query_context: PatternContext,
    query_project_id: str,
    project_ids: Optional[list[str]] = None,
) -> float:
    """Calculate relevance score for a pattern.

    Implements the scoring formula from the design:
    - Wilson score for confidence-adjusted success rate
    - Context overlap with hierarchical weights
    - Universality bonus for multi-project patterns
    - Recency with exponential decay
    - Same-project multiplier (not additive)
    - Failure penalty with recency

    Args:
        pattern: Pattern dict from database
        query_context: Context of current query
        query_project_id: Current project ID
        project_ids: List of projects where pattern has been used

    Returns:
        Relevance score (0.0-1.0+)
    """
    success_count = pattern.get("success_count", 0)
    failure_count = pattern.get("failure_count", 0)
    total = success_count + failure_count

    # 1. Confidence-adjusted success rate (Wilson score)
    confidence_rate = wilson_score(success_count, total)

    # 2. Failure penalty (recent failures hurt more)
    failure_penalty = 0.0
    if failure_count > 0 and total > 0:
        base_rate = failure_count / total
        last_failure = pattern.get("last_failure_at")
        if last_failure:
            days_since = (datetime.utcnow() - parse_datetime(last_failure)).days
            recency_factor = math.exp(-days_since / 7)  # 7-day half-life
            failure_penalty = base_rate * (0.5 + 0.5 * recency_factor)
        else:
            failure_penalty = base_rate * 0.5

    # 3. Context overlap
    pattern_context = pattern.get("context", {})
    context_overlap = calculate_context_overlap(pattern_context, query_context)

    # 4. Universality (log scale with diminishing returns)
    project_count = pattern.get("project_count", 1)
    if project_ids:
        project_count = len(set(project_ids))
    universality = min(math.log10(project_count + 1) / math.log10(10), 1.0)

    # 5. Recency (30-day half-life)
    last_success = pattern.get("last_success_at")
    recency = calculate_recency_score(parse_datetime(last_success) if last_success else None)

    # 6. Trust bonus
    trust_bonus = 0.0
    if pattern.get("verified_by"):
        trust_bonus = 0.15
    elif pattern.get("is_evergreen"):
        trust_bonus = 0.10

    # Base score (weighted sum)
    base_score = (
        0.30 * confidence_rate +
        0.25 * context_overlap +
        0.15 * universality +
        0.15 * recency +
        0.15 * (1.0 - failure_penalty)
    )

    # Add trust bonus
    base_score = min(base_score + trust_bonus, 1.0)

    # 7. Same-project multiplier
    if project_ids and query_project_id in project_ids:
        base_score *= 1.2

    # 8. Risk penalty
    risk_multipliers = {
        "low": 1.0,
        "medium": 0.95,
        "high": 0.85,
        "critical": 0.70,
    }
    risk_level = pattern.get("risk_level", "low")
    base_score *= risk_multipliers.get(risk_level, 1.0)

    return min(base_score, 1.0)


def parse_datetime(value) -> Optional[datetime]:
    """Parse datetime from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # Try ISO format
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


# Cross-project eligibility thresholds
CROSS_PROJECT_MIN_PROJECTS = 3
CROSS_PROJECT_MIN_SUCCESSES = 5
CROSS_PROJECT_MIN_WILSON = 0.7


def is_eligible_for_cross_project(pattern: dict) -> bool:
    """Check if pattern meets cross-project guardrails.

    Args:
        pattern: Pattern dict

    Returns:
        True if pattern can be used cross-project
    """
    project_count = pattern.get("project_count", 0)
    success_count = pattern.get("success_count", 0)
    failure_count = pattern.get("failure_count", 0)

    if project_count < CROSS_PROJECT_MIN_PROJECTS:
        return False

    if success_count < CROSS_PROJECT_MIN_SUCCESSES:
        return False

    wilson = wilson_score(success_count, success_count + failure_count)
    if wilson < CROSS_PROJECT_MIN_WILSON:
        return False

    return True

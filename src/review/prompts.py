"""
Review prompt templates for each review type.

Prompts are optimized for reviewing AI-generated code in a "vibe coding"
workflow where there is minimal/no human review.
"""

SECURITY_REVIEW_PROMPT = """
Review this AI-generated code for security vulnerabilities.

AI coding agents often introduce these issues without realizing:

- **Injection**: SQL, command, XSS, template injection
- **Authentication/Authorization**: Bypasses, missing checks, privilege escalation
- **Secrets**: Hardcoded credentials, API keys, tokens in code
- **SSRF/CSRF**: Server-side request forgery, cross-site request forgery
- **Path Traversal**: Directory traversal, arbitrary file access
- **Insecure Deserialization**: Unsafe object deserialization
- **Input Validation**: Missing or insufficient validation at boundaries
- **Cryptography**: Weak algorithms, improper key handling

**IMPORTANT**: This code has had ZERO human review. Be thorough.

## Changed Files
{changed_files}

## Git Diff
```diff
{git_diff}
```

## Output Format
For each finding:

### [CRITICAL|HIGH|MEDIUM|LOW]
**Issue:** <clear description of the vulnerability>
**Location:** <file:line>
**Evidence:** <relevant code snippet>
**Fix:** <specific recommendation>

If no security issues found, state:
"No security vulnerabilities identified. Reviewed for: [list what you checked]"
"""

CONSISTENCY_REVIEW_PROMPT = """
You have access to the ENTIRE codebase. Review if this new AI-generated code fits.

AI coding agents solve problems in isolation. They often:
- Write new code instead of using existing utilities
- Ignore established patterns in the codebase
- Create inconsistent naming, structure, or error handling
- Duplicate logic that already exists elsewhere

## Your Task
Check if the new code:

1. **DUPLICATES existing code**
   - Is there already a utility/helper for this?
   - "There's already `src/utils/dates.ts` for date formatting"

2. **FOLLOWS established patterns**
   - How are similar problems solved elsewhere?
   - "Other API handlers use the `errorHandler` middleware"

3. **USES existing abstractions**
   - Are there base classes or utilities being ignored?
   - "The `BaseRepository` class already handles this"

4. **MATCHES conventions**
   - Naming (camelCase vs snake_case)
   - File structure
   - Error handling patterns
   - Import organization

## Changed Files
{changed_files}

## Related Files (for pattern reference)
{related_files}

## Output Format

### Overall Assessment: [APPROVED|APPROVED_WITH_NOTES|CHANGES_REQUESTED]

**Summary:** <1-2 sentence overall assessment>

**Existing Code That Should Be Used:**
- <file:function that already does X>

**Pattern Violations:**
- <where it deviates from established patterns>

**Suggestions:**
- <non-blocking improvements>
"""

QUALITY_REVIEW_PROMPT = """
Review this AI-generated code for production readiness.

## Project Context
{project_context}

AI coding agents often focus on the "happy path" and miss:

- **Edge Cases**: What inputs weren't considered? Empty arrays, null values, boundary conditions
- **Error Handling**: What can fail? Network, filesystem, parsing - is it handled?
- **Resource Cleanup**: File handles, database connections, event listeners - are they cleaned up?
- **Input Validation**: Is user/external input validated at system boundaries?
- **Complexity**: Is there a simpler solution? Over-engineering is common in AI code
- **Test Coverage**: Are tests meaningful? What scenarios are missing?
- **Performance**: Any obvious N+1 queries, unnecessary loops, memory leaks?

**IMPORTANT**: This code has had ZERO human review. Find the unhappy paths.
**IMPORTANT**: Only check for build tools/configs that match this project type (e.g., don't check for package.json in Python projects).

## Changed Files
{changed_files}

## Git Diff
```diff
{git_diff}
```

## Output Format

### Quality Score: [1-10]

**Summary:** <overall assessment>

**Issues:**
1. [CRITICAL|HIGH|MEDIUM|LOW] <issue> at <location>
   Recommendation: <fix>

**Missing Error Handling:**
- <what can fail that isn't handled>

**Missing Tests:**
- <scenarios that aren't covered>

**Positive Notes:**
- <things done well>
"""

HOLISTIC_REVIEW_PROMPT = """
Review this AI-generated code with fresh eyes.

The security, consistency, and quality reviews have already run.
You are the final check - the skeptical senior engineer this code hasn't had.

## Consider

- **Would you approve this PR?** What would make you hesitate?
- **What questions would you ask?** In a real code review, what would you want clarified?
- **What feels "off"?** Even if you can't pinpoint why, trust your instincts
- **What would YOU do differently?** Is there a better approach?
- **What did the AI likely miss?** Think about the blind spots of coding agents
- **Is this the right solution?** Or is it solving the wrong problem?

## Changed Files
{changed_files}

## Context (if available)
{context}

## Output Format

### Overall Impression
<your gut reaction to this code>

### Concerns
- <things that worry you, even small ones>

### Questions I'd Ask
- <what you'd want clarified before approving>

### What I'd Do Differently
- <alternative approaches worth considering>

### Verdict
[APPROVE|REQUEST_CHANGES|NEEDS_DISCUSSION]
<brief justification>
"""

# Vibe-coding specific review - catches AI-generation blindspots
VIBE_CODING_REVIEW_PROMPT = """
This code was written by an AI with ZERO human review ("vibe coding").

AI-generated code has specific failure modes that traditional reviews miss.
Your job is to catch these AI-specific issues.

KEY INSIGHT: AI agents optimize locally without seeing the big picture.
They write code that makes sense in isolation but may duplicate existing
utilities, violate architectural patterns, or miss opportunities for reuse.

## Check For

1. **HALLUCINATED APIs**
   - Does the code call methods/functions that don't exist?
   - Are imports referencing real packages with correct APIs?
   - "This uses `requests.fetch()` but requests doesn't have a fetch method"

2. **PLAUSIBLE BUT WRONG**
   - Code that looks correct but has subtle logic errors
   - Off-by-one errors, wrong operators, inverted conditions
   - "The loop condition should be `<` not `<=`"

3. **TESTS THAT DON'T TEST**
   - Tests that pass but don't verify actual behavior
   - Mocks that make tests tautological
   - "This test mocks the function it's testing - it will always pass"

4. **COMMENT/CODE DRIFT**
   - Comments that describe something different than the code does
   - Docstrings with wrong parameter descriptions
   - "Comment says 'returns user ID' but code returns username"

5. **TRAINING DATA ARTIFACTS**
   - Deprecated APIs from older code in training data
   - Patterns that were common in 2020 but not now
   - "Uses `componentWillMount` which is deprecated since React 16.3"

6. **CARGO CULT CODE**
   - Code copied without understanding
   - Unnecessary complexity, dead branches, vestigial parameters
   - "This null check can never trigger given the type signature"

## Output Format

### Vibe-Coding Issues Found

For each issue:
- **[CRITICAL|HIGH|MEDIUM|LOW]** <title>
- **Evidence:** <the problematic code>
- **Why AI Wrote This:** <likely reason the AI made this mistake>
- **Fix:** <specific correction>

If no issues: "No vibe-coding issues found. Verified: [list what you checked]"
"""

# Mapping of review types to their prompts
REVIEW_PROMPTS = {
    "security_review": SECURITY_REVIEW_PROMPT,
    "security": SECURITY_REVIEW_PROMPT,
    "consistency_review": CONSISTENCY_REVIEW_PROMPT,
    "consistency": CONSISTENCY_REVIEW_PROMPT,
    "quality_review": QUALITY_REVIEW_PROMPT,
    "quality": QUALITY_REVIEW_PROMPT,
    "holistic_review": HOLISTIC_REVIEW_PROMPT,
    "holistic": HOLISTIC_REVIEW_PROMPT,
    "vibe_coding_review": VIBE_CODING_REVIEW_PROMPT,
    "vibe_coding": VIBE_CODING_REVIEW_PROMPT,
    "vibe": VIBE_CODING_REVIEW_PROMPT,
}

# ============================================================================
# REVIEW_TOOLS - DEPRECATED
# ============================================================================
# Tool assignments are now read from workflow.yaml settings.reviews.types
# This dict is kept for reference only - DO NOT MODIFY
# See: src/review/config.py for the single source of truth
# ============================================================================
_LEGACY_REVIEW_TOOLS = {
    "security_review": "codex",
    "quality_review": "codex",
    "consistency_review": "gemini",
    "holistic_review": "gemini",
    "vibe_coding_review": "grok",
}

# For backward compatibility, export REVIEW_TOOLS (but it now reads from config)
# Code should use get_tool() instead of accessing REVIEW_TOOLS directly


def get_prompt(review_type: str) -> str:
    """Get the prompt template for a review type."""
    return REVIEW_PROMPTS.get(review_type, HOLISTIC_REVIEW_PROMPT)


def get_tool(review_type: str) -> str:
    """
    Get the recommended tool for a review type.

    Reads from workflow.yaml settings.reviews.types (single source of truth).
    Falls back to defaults if not configured.

    Args:
        review_type: Review type (e.g., "security_review" or "security")

    Returns:
        Tool name: "codex", "gemini", or "grok"
    """
    from .config import get_tool_for_review
    return get_tool_for_review(review_type)


# Backward compatibility: REVIEW_TOOLS property that reads from config
class _ReviewToolsProxy:
    """Proxy that reads REVIEW_TOOLS from config for backward compatibility."""

    def get(self, key: str, default: str = "gemini") -> str:
        from .config import get_tool_for_review
        return get_tool_for_review(key)

    def __getitem__(self, key: str) -> str:
        return self.get(key)

    def __contains__(self, key: str) -> bool:
        # All keys are valid (config provides defaults)
        return True


REVIEW_TOOLS = _ReviewToolsProxy()

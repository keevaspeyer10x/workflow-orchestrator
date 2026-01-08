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
}

# Which tool to use for each review
REVIEW_TOOLS = {
    "security_review": "codex",
    "security": "codex",
    "consistency_review": "gemini",
    "consistency": "gemini",
    "quality_review": "codex",
    "quality": "codex",
    "holistic_review": "gemini",
    "holistic": "gemini",
}


def get_prompt(review_type: str) -> str:
    """Get the prompt template for a review type."""
    return REVIEW_PROMPTS.get(review_type, HOLISTIC_REVIEW_PROMPT)


def get_tool(review_type: str) -> str:
    """Get the recommended tool for a review type."""
    return REVIEW_TOOLS.get(review_type, "gemini")

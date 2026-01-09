# CORE-023-P2: LLM-Assisted Conflict Resolution - Implementation Plan

## Overview

Part 2 adds LLM-based resolution for git conflicts that can't be auto-resolved by Part 1's deterministic strategies (rerere, 3-way merge, ours/theirs).

## Design Principles (from AI Synthesis)

1. **Intent as structured constraints**, not prose - Extract hard/soft constraints with priority ordering
2. **Evidence-grounded intent** - Citations to tests/tasks/code, not hallucinated
3. **Tiered validation** - Fast filters first (syntax, conflict markers), expensive tests only for promising candidates
4. **Confidence-based escalation** - High → auto-apply, Medium → show diff, Low → escalate to human
5. **Security-first** - Detect sensitive files, don't send secrets to LLM

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    orchestrator resolve --use-llm               │
└─────────────────────────────┬──────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────┐
│                   GitConflictResolver.resolve_with_llm()       │
│                                                                 │
│  1. Check sensitive files → Skip LLM if secrets detected        │
│  2. Try Part 1 strategies first (rerere, 3way, ours/theirs)    │
│  3. If escalation needed → invoke LLMResolver                  │
└─────────────────────────────┬──────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────┐
│                     LLMResolver Pipeline                        │
│                                                                 │
│  Stage 1: Intent Extraction (per side)                         │
│  ├── What was ours trying to do?                               │
│  ├── What was theirs trying to do?                             │
│  └── Output: ExtractedIntent with constraints + confidence     │
│                                                                 │
│  Stage 2: Context Assembly                                      │
│  ├── Related files (imports, callers)                          │
│  ├── Project conventions (from CLAUDE.md, patterns)            │
│  └── Token budget management (prioritize most relevant)        │
│                                                                 │
│  Stage 3: LLM Resolution                                        │
│  ├── Build structured prompt with constraints                   │
│  ├── Generate merged code                                       │
│  └── If low confidence: generate multiple candidates            │
│                                                                 │
│  Stage 4: Validation                                            │
│  ├── Tier 1: No conflict markers (fast)                        │
│  ├── Tier 2: Syntax valid (fast)                               │
│  ├── Tier 3: Build passes (slower)                             │
│  └── Tier 4: Tests pass (slowest, only for high-stakes)        │
│                                                                 │
│  Stage 5: Confidence Scoring & Decision                         │
│  ├── High (>0.8) → Auto-apply                                  │
│  ├── Medium (0.5-0.8) → Show diff, ask user                    │
│  └── Low (<0.5) → Escalate with explanation                    │
└────────────────────────────────────────────────────────────────┘
```

## Implementation Files

### New Files

1. **`src/resolution/llm_resolver.py`** - Core LLM resolution logic
   - `LLMResolver` class with staged pipeline
   - Intent extraction with LLM
   - Merge code generation
   - Confidence scoring

2. **`tests/test_llm_resolver.py`** - Tests for LLM resolver
   - Mock LLM responses for deterministic tests
   - Golden file tests for known conflict patterns
   - Property-based tests for validation

### Modified Files

1. **`src/cli.py`**
   - Add `--use-llm` flag to `resolve` subcommand
   - Call `resolve_with_llm()` when flag is set

2. **`src/git_conflict_resolver.py`**
   - Add `resolve_with_llm()` method
   - Add sensitive file detection
   - Integration with `LLMResolver`

3. **`src/resolution/intent.py`**
   - Add `extract_with_llm()` method for LLM-enhanced intent extraction
   - Keep heuristic method as fallback

## Key Implementation Details

### 1. Sensitive File Detection

```python
SENSITIVE_PATTERNS = [
    "*.env", ".env.*", "secrets.*", "*secret*",
    "*credential*", "*password*", "*key*",
    "*.pem", "*.key", "*.p12", "*.pfx",
    "config/secrets/*", ".aws/*", ".gcp/*",
]

def is_sensitive_file(path: str) -> bool:
    """Check if file matches sensitive patterns."""
    for pattern in SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False
```

### 2. Token Budget Management

```python
MAX_CONTEXT_TOKENS = 32000  # Reserve 8k for response

def assemble_context_with_budget(conflict, related_files, conventions):
    """Assemble context within token budget, prioritizing relevance."""
    budget = MAX_CONTEXT_TOKENS
    context = []

    # Priority 1: Conflicting file content (required)
    context.append(conflict.base)
    context.append(conflict.ours)
    context.append(conflict.theirs)
    budget -= estimate_tokens(conflict)

    # Priority 2: Directly imported files
    for f in related_files:
        if f.relationship == "imports" and budget > 0:
            context.append(f)
            budget -= estimate_tokens(f)

    # Priority 3: Project conventions (compact)
    # ... etc

    return context
```

### 3. Confidence Scoring

Confidence is based on multiple signals:
- **Intent clarity**: How clear are the constraints? (from extraction)
- **Conflict complexity**: Overlap size, number of conflicting regions
- **Validation results**: Did generated code pass all tiers?
- **Model confidence**: Self-reported uncertainty (if available)

```python
def calculate_confidence(
    intent_confidence: str,
    validation_passed: list[str],  # ["syntax", "build", "tests"]
    conflict_complexity: str,  # "simple", "moderate", "complex"
) -> float:
    score = 0.5

    if intent_confidence == "high":
        score += 0.2
    elif intent_confidence == "low":
        score -= 0.2

    if "syntax" in validation_passed:
        score += 0.1
    if "build" in validation_passed:
        score += 0.1
    if "tests" in validation_passed:
        score += 0.1

    if conflict_complexity == "simple":
        score += 0.1
    elif conflict_complexity == "complex":
        score -= 0.1

    return max(0.0, min(1.0, score))
```

### 4. LLM Prompt Structure

```python
MERGE_PROMPT = '''You are resolving a git merge conflict.

## Base version (before both changes):
```{language}
{base_content}
```

## Our changes (what we added):
```{language}
{ours_content}
```

## Their changes (what target branch added):
```{language}
{theirs_content}
```

## Intent analysis:
- OURS intent: {ours_intent}
- THEIRS intent: {theirs_intent}
- Relationship: {relationship}

## Constraints:
Hard constraints (MUST satisfy):
{hard_constraints}

Soft constraints (prefer):
{soft_constraints}

## Project conventions:
{conventions}

## Task:
Generate the merged code that:
1. Satisfies all hard constraints
2. Preserves both intents where possible
3. Follows project conventions
4. Produces valid {language} syntax

Output ONLY the merged code, no explanation.
'''
```

## API Integration

Uses existing secrets infrastructure:
- `OPENAI_API_KEY` for GPT models
- `GEMINI_API_KEY` for Gemini (fallback)
- `OPENROUTER_API_KEY` for OpenRouter (fallback)

```python
from src.secrets import get_secrets_manager

def get_llm_client():
    secrets = get_secrets_manager()

    # Try OpenAI first (best for code)
    api_key = secrets.get_secret("OPENAI_API_KEY")
    if api_key:
        return OpenAIClient(api_key)

    # Fallback to OpenRouter
    api_key = secrets.get_secret("OPENROUTER_API_KEY")
    if api_key:
        return OpenRouterClient(api_key)

    raise ValueError("No LLM API key available")
```

## CLI Usage

```bash
# Preview LLM resolution (default: preview only)
orchestrator resolve --use-llm

# Apply LLM resolutions with auto-apply for high confidence
orchestrator resolve --use-llm --apply

# Force user confirmation for all resolutions
orchestrator resolve --use-llm --apply --confirm-all

# Set confidence threshold for auto-apply
orchestrator resolve --use-llm --apply --auto-apply-threshold 0.9
```

## Success Criteria

1. **Functional**: `--use-llm` flag triggers LLM-based resolution
2. **Safe**: Sensitive files are detected and skipped
3. **Validated**: Generated code passes syntax and conflict marker checks
4. **Transparent**: User sees confidence scores and can review before apply
5. **Tested**: Unit tests, integration tests, golden file tests

## Risk Mitigation

1. **Hallucination**: Tiered validation catches invalid code
2. **Security**: Sensitive file detection + no secrets to LLM
3. **API Failures**: Graceful degradation to Part 1 strategies
4. **Cost**: Token budget management limits API costs

## Out of Scope (Part 3)

- Learning from resolutions (pattern database)
- Configuration file for policies
- LEARN phase integration

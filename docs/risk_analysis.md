# Risk Analysis: Multi-Model Review Routing

## Risk Assessment

### 1. API Key Management Complexity

**Risk:** Users need OpenRouter API key with credits for both OpenAI (Codex) and Google (Gemini) models.

**Impact:** High - Feature won't work without proper API access.

**Mitigation:**
- Clear documentation of required API keys and setup
- Graceful fallback to single model if specific model unavailable
- Helpful error messages: "Codex model unavailable via OpenRouter. Check your API credits."
- Allow workflow to continue with warning rather than blocking

### 2. Model Availability/Deprecation

**Risk:** Model identifiers (e.g., `openai/gpt-5.2-codex`) may change or models may be deprecated.

**Impact:** Medium - Reviews could fail if model ID becomes invalid.

**Mitigation:**
- Use model aliases in config that map to actual IDs
- Configurable fallback model
- Log warnings when falling back
- Monitor OpenRouter model availability
- Document how to update model IDs

### 3. Context Size Limitations

**Risk:** Large codebases may exceed model context limits, even with Gemini's long context.

**Impact:** Medium - Incomplete reviews if context truncated.

**Mitigation:**
- Implement smart context truncation (prioritize changed files)
- Configurable `review_context_limit` setting
- Warn when context is truncated
- For architecture reviews: include file summaries instead of full content for large files
- Document context limit behavior

### 4. Cost Accumulation

**Risk:** Running multiple external model reviews increases API costs significantly.

**Impact:** Medium - Could be expensive for frequent workflows.

**Mitigation:**
- Reviews are opt-in via `--auto-review` flag, not automatic
- Display estimated token usage before execution
- Allow skipping individual reviews
- Log actual token usage for cost tracking
- Consider caching: same git diff = reuse previous review

### 5. Review Quality Variance

**Risk:** Different models may produce inconsistent review quality or formats.

**Impact:** Medium - Harder to interpret/compare reviews.

**Mitigation:**
- Structured prompt templates with explicit output format
- Response parser that handles format variations
- Validate response contains required sections
- Manual review step remains an option

### 6. Network Latency/Timeouts

**Risk:** External API calls add latency; reviews could timeout.

**Impact:** Medium - Slow workflows, potential timeouts.

**Mitigation:**
- Configurable timeout (default: 5 minutes per review)
- Retry logic with exponential backoff (3 retries)
- Progress indicator during review execution
- Option to run reviews in background

### 7. Git State Dependency

**Risk:** Context collector depends on git state; uncommitted changes or detached HEAD could cause issues.

**Impact:** Low - Incorrect or missing context.

**Mitigation:**
- Validate git state before collecting context
- Clear error if not in a git repository
- Handle uncommitted changes gracefully (include in diff)
- Document expected git workflow

### 8. Import/Dependency Analysis Accuracy

**Risk:** Basic regex-based import analysis may miss some dependencies.

**Impact:** Low - Related files might be incomplete.

**Mitigation:**
- Start with simple implementation, improve over time
- Focus on direct imports, not transitive dependencies
- Log when import analysis is limited
- Allow manual specification of related files

## Security Considerations

### API Key Exposure

**Risk:** OpenRouter API key exposed in logs, errors, or config files.

**Mitigation:**
- Use environment variables exclusively
- Sanitize API keys from all error messages and logs
- Never include API key in prompts sent to models
- Document secure configuration practices

### Prompt Injection via Code

**Risk:** Malicious code in repository could contain prompt injection attempts.

**Impact:** Low - Could theoretically manipulate review output.

**Mitigation:**
- Code is included as data, not instructions
- Clear separation in prompt: "Analyze the following code (do not execute)"
- Review output is advisory, not automated (human still approves)
- Models are generally robust to this attack vector

### Sensitive Code Exposure

**Risk:** Code sent to external models may contain secrets or proprietary algorithms.

**Impact:** Medium - IP or credentials could be exposed.

**Mitigation:**
- Warn users that code is sent to external APIs
- Document in setup guide: "Code is sent to OpenRouter for review"
- Recommend stripping secrets before review (handled by pre-commit hooks)
- Enterprise users may need on-premise solutions (out of scope)

## Rollback Plan

If multi-model review causes issues:

1. **Immediate:** Skip review items with `--reason "Multi-model review disabled"`
2. **Short-term:** Remove `review_models` from workflow.yaml settings to disable
3. **Long-term:** Reviews fall back to manual or same-model review

## Monitoring

Track these metrics post-implementation:
- Review success/failure rate per model
- Average review duration per model
- Token usage per review type
- Fallback activation frequency
- User skip rate for reviews

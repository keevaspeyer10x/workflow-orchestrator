# Specification: [Feature Name]

> Generated via `/spec` protocol on [DATE]

## Outcome

[One sentence: the job-to-be-done this feature accomplishes]

## Success Criteria

- [ ] [Measurable criterion 1]
- [ ] [Measurable criterion 2]
- [ ] [Measurable criterion 3]

## User Journey

### Trigger
[What initiates this journey - the event or need that starts it]

### Actor
[Who performs this journey - their role and context]

### Context
[What the user knows/feels when starting - prior knowledge, mental state]

### Core Flow

| Step | User Action | Sees | Decides |
|------|-------------|------|---------|
| 1 | [Action] | [Information displayed] | [Decision made] |
| 2 | [Action] | [Information displayed] | [Decision made] |
| 3 | [Action] | [Information displayed] | [Decision made] |
| 4 | [Action] | [Information displayed] | [Decision made] |
| 5 | [Action] | [Information displayed] | [Decision made] |

### Success State
[How the user knows they've succeeded - what they see/have when done]

### Next Action
[What typically happens after this journey completes]

---

## Approved Design

[The concrete artifact the user approved - mockup, API spec, CLI transcript, etc.]

```
[INSERT ARTIFACT HERE]

For UI: ASCII mockup with annotations
For API: Example request/response pairs
For CLI: Example session transcript
For Data: Input → Output transformation example
```

---

## Data Requirements

| Journey Step | Required Data | Source | Validation | If Missing |
|--------------|---------------|--------|------------|------------|
| Step 1 | | | | |
| Step 2 | | | | |
| Step 3 | | | | |

---

## Edge Cases & Failure Modes

| Scenario | Trigger | Handling | Recovery Path |
|----------|---------|----------|---------------|
| Empty state | [When] | [What user sees] | [How to proceed] |
| Invalid input | [When] | [What user sees] | [How to correct] |
| Permission denied | [When] | [What user sees] | [How to resolve] |
| System error | [When] | [What user sees] | [How to retry] |
| [Other edge case] | | | |

---

## Out of Scope

Explicitly NOT included in this specification:

- [Feature/capability 1] - [Reason / deferred to when]
- [Feature/capability 2] - [Reason / deferred to when]
- [Feature/capability 3] - [Reason / deferred to when]

---

## Research References

Patterns and products that informed this design:

| Source | What We Borrowed | Why |
|--------|------------------|-----|
| [Product/Pattern] | [Specific element] | [Rationale] |
| [Product/Pattern] | [Specific element] | [Rationale] |

---

## Stakeholder Critique Summary

Issues identified and resolved during adversarial review:

### Critical Issues Addressed

| Issue | Identified By | Resolution |
|-------|---------------|------------|
| [Issue 1] | [Senior Engineer / PM / User / QA] | [How it was resolved] |
| [Issue 2] | [Role] | [Resolution] |

### Accepted Risks

| Risk | Identified By | Rationale for Accepting |
|------|---------------|------------------------|
| [Risk 1] | [Role] | [Why we're proceeding anyway] |

### Deferred Concerns

| Concern | Identified By | Deferred To |
|---------|---------------|-------------|
| [Concern 1] | [Role] | [When/where it will be addressed] |

---

## Acceptance Criteria

### Happy Path

```gherkin
Feature: [Feature name]

  Scenario: [Primary success scenario]
    Given [initial context]
    And [additional context]
    When [user action]
    Then [expected outcome]
    And [additional outcome]
```

### Key Variations

```gherkin
  Scenario: [Variation 1 - e.g., first-time user]
    Given [context]
    When [action]
    Then [outcome]

  Scenario: [Variation 2 - e.g., returning user]
    Given [context]
    When [action]
    Then [outcome]
```

### Error Handling

```gherkin
  Scenario: [Error scenario 1]
    Given [error context]
    When [user action]
    Then [graceful handling]
    And [recovery option shown]

  Scenario: [Error scenario 2]
    Given [error context]
    When [user action]
    Then [graceful handling]
```

---

## Implementation Notes

[Any additional context for implementation - technical constraints, dependencies, etc.]

---

## Approval

- [ ] Outcome validated with stakeholder
- [ ] Journey map confirmed accurate
- [ ] Design artifact approved
- [ ] Edge cases reviewed
- [ ] Stakeholder critique completed
- [ ] Critical issues resolved
- [ ] Acceptance criteria agreed

**Approved by:** [Name/Role]
**Date:** [Date]

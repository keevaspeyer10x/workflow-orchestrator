# Visual UAT Test: {{feature_name}}

## Test URL
{{base_url}}/path/to/feature

## Pre-conditions
- User is logged in
- [Other setup requirements]

## Actions to Perform
1. Navigate to the page
2. [Action 2]
3. [Action 3]

## Specific Checks
- [ ] [Specific element] is visible
- [ ] [Specific functionality] works
- [ ] [Expected state] is achieved

## Open-Ended Evaluation (Mandatory)

These questions will be evaluated by AI for both desktop and mobile viewports:

1. **Functional Verification**: Does this feature work as specified? Can the user complete the intended action?

2. **Style Guide Consistency**: Is the design consistent with our style guide? Are colors, typography, spacing, and components used correctly?

3. **User Journey**: Is the user journey intuitive? Would a first-time user understand what to do next?

4. **Edge Case Handling**: How does it handle edge cases (errors, empty states, unexpected input, loading states)?

5. **Mobile Responsiveness**: Does it work well on mobile? Are there any responsive design issues, touch targets too small, or content overflow?

## Open-Ended Evaluation (Optional)

Include these for more thorough evaluation:

- [ ] **Accessibility**: Are there any obvious accessibility concerns (contrast, focus states, screen reader compatibility)?
- [ ] **Visual Hierarchy**: Does the layout guide the user appropriately? Is the most important content prominent?
- [ ] **Performance Perception**: Do loading states feel responsive? Are there any jarring layout shifts?
- [ ] **Error States**: Are error messages clear and helpful? Do they guide the user to resolution?
- [ ] **Empty States**: Are empty states handled gracefully with helpful guidance?

## Notes

- This test will be run against both desktop (1280x720) and mobile (375x812) viewports
- The style guide at `{{style_guide_path}}` will be included in the evaluation context
- All issues must be fixed before proceeding (no "pass with notes")

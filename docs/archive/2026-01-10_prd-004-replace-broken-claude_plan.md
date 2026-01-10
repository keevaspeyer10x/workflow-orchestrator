# Implementation Plan: Multi-Model Review Fixes

## Overview
Fix issues identified by multi-model code review to improve reliability and UX.

## Fixes

### 1. Add Test File to Git
- File: `tests/test_orchestrator_improvements.py`
- Action: `git add`

### 2. Fix default_test Bug
- Location: `src/cli.py:288`
- Current: `default_test = "npm run build"` (wrong - this is build command)
- Fix: `default_test = "npm test"`

### 3. Fix sops Command Syntax
- Location: `src/cli.py:255-257`
- Issue: `sed 's/: /=/'` produces `key = value` (invalid bash, spaces around =)
- Fix: Use `sed 's/: */=/'` or recommend yq

### 4. Smarter API Key Check
- Location: `src/cli.py:229-259`
- Current: Warns if ANY key missing (too noisy)
- Fix: Warn only if ALL keys missing, show which ARE available

### 5. Show item_id in Skip Summary
- Location: `src/cli.py:1333`
- Add item_id alongside description for traceability

### 6. Highlight Gate Bypasses
- Location: `src/cli.py:1333`
- Add `⚠️ GATE BYPASSED:` prefix for gate step types

## Constraints
- Maintain seamless UX for vibe coders
- No security friction for local CLI tool

# Implementation Plan: CORE-006, SEC-004, CORE-017, CORE-018

## Overview

Implementing four roadmap items to improve provider management, secrets handling, and model configuration:

1. **CORE-006**: Automatic Connector Detection with User Fallback
2. **SEC-004**: Cross-Repo Secrets Copy Command
3. **CORE-017**: Auto-Update Review Models
4. **CORE-018**: Dynamic Function Calling Detection

---

## CORE-006: Automatic Connector Detection with User Fallback

### Goal
Automatically detect available agent connectors and ask user before defaulting to manual implementation when preferred provider is unavailable.

### Implementation

**Files to modify:**
- `src/environment.py` - Add Manus connector detection
- `src/providers/__init__.py` - Add `get_available_providers()` and interactive selection
- `src/cli.py` - Add `--interactive` flag to handoff command

**Changes:**

1. **environment.py**:
   - Add `detect_manus_connector()` function that checks for direct Manus API access
   - Add `get_available_connectors()` to return list of all detectable connectors

2. **providers/__init__.py**:
   - Add `get_available_providers()` function returning list of available providers
   - Add `prompt_user_for_provider()` interactive function for CLI selection
   - Update `_auto_detect_provider()` to use interactive selection when preferred unavailable

3. **cli.py**:
   - Add `--interactive` flag to `handoff` command
   - Show available options when provider unavailable and `--interactive` set

---

## SEC-004: Cross-Repo Secrets Copy Command

### Goal
Add `orchestrator secrets copy` command to easily copy encrypted secrets between repositories.

### Implementation

**Files to modify:**
- `src/cli.py` - Add `copy` action to secrets subcommand
- `src/secrets.py` - Add helper function for copying

**Changes:**

1. **cli.py**:
   - Extend `cmd_secrets()` to handle `copy` action
   - Support `--from` and `--to` flags for source/destination directories
   - Validate source file exists before copying
   - Create destination directory if needed

2. **secrets.py**:
   - Add `copy_secrets_file()` helper function

---

## CORE-017: Auto-Update Review Models

### Goal
Automatically detect and use latest available AI models for reviews, with auto-update if stale.

### Implementation

**Files to modify:**
- `src/cli.py` - Add `update-models` command
- `src/providers/openrouter.py` - Add model update logic
- New: `src/model_registry.py` - Model registry with staleness checking

**Changes:**

1. **model_registry.py** (new file):
   - Store last update timestamp in `.model_registry.json`
   - `get_latest_models()` - Query OpenRouter API for available models
   - `is_registry_stale()` - Check if > 30 days since last update
   - `update_registry()` - Fetch and store latest model info
   - `get_recommended_model()` - Get latest recommended model by category

2. **cli.py**:
   - Add `update-models` command
   - Add `--check-models` flag to review command
   - Add `--no-auto-update` flag to disable auto-updates

3. **openrouter.py**:
   - Update `FUNCTION_CALLING_MODELS` from registry
   - Add staleness warning when using outdated models

---

## CORE-018: Dynamic Function Calling Detection

### Goal
Detect model function calling support from OpenRouter API instead of static list.

### Implementation

**Files to modify:**
- `src/model_registry.py` - Add capability detection (builds on CORE-017)
- `src/providers/openrouter.py` - Use dynamic detection

**Changes:**

1. **model_registry.py**:
   - `get_model_capabilities()` - Query OpenRouter for model capabilities
   - Cache capabilities in `.model_registry.json`
   - `supports_function_calling()` - Check if model supports tools

2. **openrouter.py**:
   - Update `_supports_function_calling()` to use registry
   - Fall back to static list if registry unavailable/stale

---

## Implementation Order

1. **CORE-017 + CORE-018** (together, since they share the model registry)
   - Create `model_registry.py`
   - Add CLI commands
   - Update openrouter.py

2. **CORE-006** (provider detection)
   - Update environment.py
   - Update providers/__init__.py
   - Update CLI

3. **SEC-004** (secrets copy)
   - Update secrets.py
   - Update CLI

---

## Testing Strategy

- Unit tests for new functions
- Integration tests for CLI commands
- Mock OpenRouter API responses for model registry tests

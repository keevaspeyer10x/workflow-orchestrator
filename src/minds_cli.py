#!/usr/bin/env python3
"""
Minds CLI - Multi-model AI query interface.

Provides CLI commands to interact with multiple AI models simultaneously
for questions, code reviews, and configuration status.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

# Import minds infrastructure
from src.gates.minds_proxy import (
    MODEL_WEIGHTS,
    call_model,
)
from src.gates.minds_config import (
    MindsConfig,
    load_minds_config,
    DEFAULT_MODELS,
)

VERSION = "1.0.0"


def get_api_key() -> Optional[str]:
    """Get OpenRouter API key from environment."""
    return os.environ.get("OPENROUTER_API_KEY")


def format_model_response(model: str, response: str, error: Optional[str] = None) -> str:
    """Format a model's response for display."""
    model_name = model.split("/")[-1]  # e.g., "gpt-4-turbo" from "openai/gpt-4-turbo"
    weight = MODEL_WEIGHTS.get(model, 1.0)

    if error:
        return f"\n[{model_name}] (weight: {weight}) ERROR:\n  {error}\n"

    # Indent the response for readability
    indented = "\n  ".join(response.strip().split("\n"))
    return f"\n[{model_name}] (weight: {weight}):\n  {indented}\n"


def query_model(model: str, prompt: str) -> tuple[str, str, Optional[str]]:
    """
    Query a single model and return result.

    Returns:
        Tuple of (model, response, error)
    """
    try:
        response = call_model(model, prompt)
        return (model, response, None)
    except Exception as e:
        return (model, "", str(e))


def cmd_ask(args):
    """
    Ask a question to multiple AI models.

    Queries all configured models in parallel and displays their responses.
    """
    question = args.question

    # Handle hello as a special greeting
    if question.lower() in ("hello", "hi", "hey"):
        prompt = f"The user said '{question}'. Respond with a brief, friendly greeting. Keep it to 1-2 sentences."
    else:
        prompt = question

    # Load configuration
    config = load_minds_config()

    if not config.enabled:
        print("Minds is disabled in configuration.")
        return 1

    # Check API key
    api_key = get_api_key()
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set.")
        print("Set your API key: export OPENROUTER_API_KEY='your-key-here'")
        return 1

    # Get models to query
    models = args.models.split(",") if args.models else config.models

    if args.verbose:
        print(f"Querying {len(models)} models...")
        print(f"Models: {', '.join(m.split('/')[-1] for m in models)}")
        print()

    # Query models in parallel
    results = []
    with ThreadPoolExecutor(max_workers=min(len(models), 5)) as executor:
        futures = {executor.submit(query_model, model, prompt): model for model in models}

        for future in as_completed(futures):
            model, response, error = future.result()
            results.append((model, response, error))

    # Sort by model weight (highest first)
    results.sort(key=lambda x: MODEL_WEIGHTS.get(x[0], 1.0), reverse=True)

    # Display results
    print(f"Question: {question}")
    print("=" * 60)

    success_count = 0
    for model, response, error in results:
        print(format_model_response(model, response, error))
        if not error:
            success_count += 1

    print("=" * 60)
    print(f"Responses: {success_count}/{len(models)} models")

    return 0 if success_count > 0 else 1


def cmd_review(args):
    """
    Request a multi-model code review.

    Reads code from file or stdin and requests review from multiple models.
    """
    # Get code to review
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"ERROR: File not found: {args.file}")
            return 1
        code = file_path.read_text()
        context = f"File: {args.file}"
    elif not sys.stdin.isatty():
        code = sys.stdin.read()
        context = "Code from stdin"
    else:
        print("ERROR: Provide a file with --file or pipe code via stdin")
        return 1

    # Load configuration
    config = load_minds_config()

    if not config.enabled:
        print("Minds is disabled in configuration.")
        return 1

    # Check API key
    api_key = get_api_key()
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set.")
        return 1

    # Build review prompt
    review_type = args.type or "general"

    prompts = {
        "general": f"""Review this code for issues, improvements, and best practices.
Focus on: bugs, security, performance, maintainability.

{context}
```
{code[:10000]}  # Truncate very long files
```

Provide a concise review with:
1. Issues found (if any)
2. Suggestions for improvement
3. Overall assessment (PASS/NEEDS_WORK)""",

        "security": f"""Perform a security review of this code.
Look for: injection vulnerabilities, authentication issues, data exposure, OWASP Top 10.

{context}
```
{code[:10000]}
```

List security issues found with severity (HIGH/MEDIUM/LOW) and remediation.""",

        "performance": f"""Analyze this code for performance issues.
Look for: inefficient algorithms, memory leaks, unnecessary operations, scalability concerns.

{context}
```
{code[:10000]}
```

List performance concerns with impact and suggested optimizations.""",
    }

    prompt = prompts.get(review_type, prompts["general"])

    # Get models to query
    models = args.models.split(",") if args.models else config.models

    print(f"Requesting {review_type} review from {len(models)} models...")
    print()

    # Query models in parallel
    results = []
    with ThreadPoolExecutor(max_workers=min(len(models), 5)) as executor:
        futures = {executor.submit(query_model, model, prompt): model for model in models}

        for future in as_completed(futures):
            model, response, error = future.result()
            results.append((model, response, error))

    # Sort by model weight (highest first)
    results.sort(key=lambda x: MODEL_WEIGHTS.get(x[0], 1.0), reverse=True)

    # Display results
    print(f"Code Review: {context}")
    print("=" * 60)

    for model, response, error in results:
        print(format_model_response(model, response, error))

    print("=" * 60)

    return 0


def cmd_status(args):
    """
    Show minds configuration status.

    Displays configured models, weights, and API key status.
    """
    config = load_minds_config()
    api_key = get_api_key()

    print("Minds Configuration Status")
    print("=" * 40)
    print()

    # General status
    print(f"Enabled: {'Yes' if config.enabled else 'No'}")
    print(f"Mode: {config.mode}")
    print(f"API Key: {'Set' if api_key else 'NOT SET'}")
    print()

    # Models
    print("Configured Models:")
    for model in config.models:
        weight = config.model_weights.get(model, 1.0)
        print(f"  - {model} (weight: {weight})")
    print()

    # Thresholds
    print("Thresholds:")
    print(f"  Approval threshold: {config.approval_threshold}")
    print(f"  Auto-proceed certainty: {config.auto_proceed_certainty}")
    print(f"  Escalate below certainty: {config.escalate_below_certainty}")
    print()

    # Re-deliberation
    print("Re-deliberation:")
    print(f"  Enabled: {config.re_deliberation_enabled}")
    print(f"  Max rounds: {config.re_deliberation_max_rounds}")
    print()

    if not api_key:
        print("WARNING: OPENROUTER_API_KEY not set.")
        print("Set your API key: export OPENROUTER_API_KEY='your-key-here'")
        return 1

    return 0


def main():
    """Main entry point for minds CLI."""
    parser = argparse.ArgumentParser(
        description="Minds - Multi-model AI query interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  minds ask "What's the best way to handle errors in Python?"
  minds ask "hello"
  minds review --file src/main.py
  minds review --file src/auth.py --type security
  minds status

Environment:
  OPENROUTER_API_KEY  Required for API access
        """,
    )
    parser.add_argument("--version", action="version", version=f"minds {VERSION}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question to multiple AI models")
    ask_parser.add_argument("question", help="The question to ask")
    ask_parser.add_argument(
        "--models", "-m",
        help="Comma-separated list of models to query (default: use config)",
    )
    ask_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output",
    )
    ask_parser.set_defaults(func=cmd_ask)

    # review command
    review_parser = subparsers.add_parser("review", help="Request multi-model code review")
    review_parser.add_argument(
        "--file", "-f",
        help="File to review",
    )
    review_parser.add_argument(
        "--type", "-t",
        choices=["general", "security", "performance"],
        help="Type of review (default: general)",
    )
    review_parser.add_argument(
        "--models", "-m",
        help="Comma-separated list of models to query",
    )
    review_parser.set_defaults(func=cmd_review)

    # status command
    status_parser = subparsers.add_parser("status", help="Show configuration status")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

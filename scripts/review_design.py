#!/usr/bin/env python3
"""
Review a design document using external AI models.

Usage:
    export OPENROUTER_API_KEY=...
    export GEMINI_API_KEY=...
    python scripts/review_design.py docs/designs/claude_squad_integration_sketch.md
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import litellm

# Configure litellm for OpenRouter
litellm.set_verbose = False


ARCHITECTURE_REVIEW_PROMPT = """You are a senior software architect reviewing a design document.

## Design Document

{design_content}

## Review Instructions

Please review this architecture/design proposal critically. Focus on:

1. **Feasibility**: Is this approach technically sound? Any blockers?
2. **Simplicity**: Is this the simplest solution? Are we overengineering?
3. **Dependencies**: Are we relying on stable/unstable external tools?
4. **Risks**: What could go wrong? Are the mitigations adequate?
5. **Gaps**: What's missing from this design?
6. **Alternatives**: Should we consider a different approach entirely?

Be direct and critical. It's better to find issues now than during implementation.

## Output Format

Return a JSON object:
```json
{{
  "overall_assessment": "approve" | "approve_with_changes" | "needs_rework",
  "confidence": 0.0-1.0,
  "summary": "One paragraph summary",
  "strengths": ["list of things done well"],
  "concerns": [
    {{
      "severity": "critical" | "high" | "medium" | "low",
      "title": "Brief title",
      "description": "Detailed concern",
      "recommendation": "How to address it"
    }}
  ],
  "questions": ["Questions that need answers before proceeding"],
  "alternative_approaches": ["Other ways to solve this problem"]
}}
```
"""


async def review_with_model(model_id: str, design_content: str, display_name: str) -> dict:
    """Review design with a specific model."""
    print(f"\n{'='*60}")
    print(f"Reviewing with {display_name}...")
    print(f"{'='*60}")

    try:
        response = await litellm.acompletion(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a senior software architect. Return your analysis as JSON."},
                {"role": "user", "content": ARCHITECTURE_REVIEW_PROMPT.format(design_content=design_content)}
            ],
            max_tokens=4000,
            temperature=0.3,
        )

        result = response.choices[0].message.content
        print(f"\n{display_name} Review:\n")
        print(result)

        return {
            "model": display_name,
            "response": result,
            "tokens": response.usage.total_tokens if response.usage else 0,
            "success": True
        }

    except Exception as e:
        print(f"Error with {display_name}: {e}")
        return {
            "model": display_name,
            "error": str(e),
            "success": False
        }


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/review_design.py <design_file.md>")
        sys.exit(1)

    design_file = Path(sys.argv[1])
    if not design_file.exists():
        print(f"File not found: {design_file}")
        sys.exit(1)

    design_content = design_file.read_text()

    # Check API keys
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not openrouter_key:
        print("Warning: OPENROUTER_API_KEY not set")
    if not gemini_key:
        print("Warning: GEMINI_API_KEY not set")

    print(f"\nReviewing: {design_file}")
    print(f"Content length: {len(design_content)} chars")

    # Models to use for architecture review
    models = []

    if openrouter_key:
        models.extend([
            ("openrouter/openai/gpt-4o", "GPT-4o"),
            ("openrouter/x-ai/grok-beta", "Grok"),
        ])

    if gemini_key:
        models.append(("gemini/gemini-2.5-pro", "Gemini 2.5 Pro"))

    if not models:
        print("No API keys available for review!")
        sys.exit(1)

    print(f"\nUsing {len(models)} models for review...")

    # Run reviews in parallel
    tasks = [
        review_with_model(model_id, design_content, display_name)
        for model_id, display_name in models
    ]

    results = await asyncio.gather(*tasks)

    # Summary
    print("\n" + "="*60)
    print("REVIEW SUMMARY")
    print("="*60)

    for result in results:
        status = "✓" if result["success"] else "✗"
        tokens = result.get("tokens", "N/A")
        print(f"  {status} {result['model']}: tokens={tokens}")

    # Save results
    output_file = design_file.with_suffix(".reviews.md")
    with open(output_file, "w") as f:
        f.write(f"# AI Reviews: {design_file.name}\n\n")
        f.write(f"Generated: {asyncio.get_event_loop().time()}\n\n")

        for result in results:
            f.write(f"## {result['model']}\n\n")
            if result["success"]:
                f.write(result["response"])
            else:
                f.write(f"Error: {result['error']}")
            f.write("\n\n---\n\n")

    print(f"\nReviews saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())

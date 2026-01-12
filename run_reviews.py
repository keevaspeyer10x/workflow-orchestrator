#!/usr/bin/env python3
"""
Run external model reviews on the containment strategy.
"""

import os
import json
from pathlib import Path

def read_review_files():
    """Read the review package and containment proposal."""
    review_package = Path("REVIEW_PACKAGE.md").read_text()
    containment_proposal = Path("CONTAINMENT_PROPOSAL.md").read_text()

    return f"""# Review Request

Please review the following multi-repo support and containment strategy for the workflow-orchestrator project.

{review_package}

---

# Full Technical Specification

{containment_proposal}

---

# Your Task

Please provide a detailed review addressing:

1. **Architecture Assessment**: Is the containment strategy sound? Any edge cases or risks?
2. **Migration Path**: Is the 4-phase migration plan reasonable? Better alternatives?
3. **Multi-Repo Support**: What gaps remain for seamless multi-repo usage?
4. **Web Compatibility**: Critical considerations for Claude Code Web (ephemeral sessions)?
5. **Implementation**: Feedback on PathResolver design and auto-migration approach?
6. **User Experience**: How to minimize disruption to existing users?
7. **Recommendations**: What should be prioritized? Alternative approaches?

Please be specific, cite examples, and identify potential issues we haven't considered.
"""

def review_with_gemini(prompt: str):
    """Review using Gemini via API."""
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set"}

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

    print("🔍 Reviewing with Gemini 2.0 Flash...")
    response = model.generate_content(prompt)
    return {
        "model": "gemini-2.0-flash-exp",
        "review": response.text
    }

def review_with_openai(prompt: str):
    """Review using OpenAI GPT-4."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set"}

    client = OpenAI(api_key=api_key)

    print("🔍 Reviewing with GPT-4...")
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=4000
    )

    return {
        "model": "gpt-4-turbo-preview",
        "review": response.choices[0].message.content
    }

def review_with_openrouter(prompt: str, model: str):
    """Review using OpenRouter API."""
    from openai import OpenAI

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"error": "OPENROUTER_API_KEY not set"}

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

    print(f"🔍 Reviewing with {model} via OpenRouter...")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=4000
    )

    return {
        "model": model,
        "review": response.choices[0].message.content
    }

def main():
    """Run all reviews."""
    prompt = read_review_files()

    reviews = []

    # 1. Gemini Review
    try:
        review = review_with_gemini(prompt)
        reviews.append(review)
        print(f"✅ Gemini review complete ({len(review.get('review', ''))} chars)")
    except Exception as e:
        print(f"❌ Gemini review failed: {e}")
        reviews.append({"model": "gemini-2.0-flash-exp", "error": str(e)})

    # 2. OpenAI Review
    try:
        review = review_with_openai(prompt)
        reviews.append(review)
        print(f"✅ OpenAI review complete ({len(review.get('review', ''))} chars)")
    except Exception as e:
        print(f"❌ OpenAI review failed: {e}")
        reviews.append({"model": "gpt-4-turbo-preview", "error": str(e)})

    # 3. Claude Opus (via OpenRouter)
    try:
        review = review_with_openrouter(prompt, "anthropic/claude-opus")
        reviews.append(review)
        print(f"✅ Claude Opus review complete ({len(review.get('review', ''))} chars)")
    except Exception as e:
        print(f"❌ Claude Opus review failed: {e}")
        reviews.append({"model": "anthropic/claude-opus", "error": str(e)})

    # 4. DeepSeek (via OpenRouter)
    try:
        review = review_with_openrouter(prompt, "deepseek/deepseek-chat")
        reviews.append(review)
        print(f"✅ DeepSeek review complete ({len(review.get('review', ''))} chars)")
    except Exception as e:
        print(f"❌ DeepSeek review failed: {e}")
        reviews.append({"model": "deepseek/deepseek-chat", "error": str(e)})

    # Save all reviews
    output_file = Path(".orchestrator") / "external_reviews.json"
    output_file.parent.mkdir(exist_ok=True)
    output_file.write_text(json.dumps(reviews, indent=2))
    print(f"\n✅ All reviews saved to {output_file}")

    # Create markdown summary
    summary_file = Path("EXTERNAL_REVIEWS.md")
    with summary_file.open("w") as f:
        f.write("# External Model Reviews\n\n")
        f.write("Reviews of the multi-repo support and containment strategy.\n\n")
        f.write("---\n\n")

        for review in reviews:
            model = review.get("model", "unknown")
            f.write(f"## {model}\n\n")

            if "error" in review:
                f.write(f"**Error**: {review['error']}\n\n")
            else:
                f.write(review.get("review", "No review content"))
                f.write("\n\n")

            f.write("---\n\n")

    print(f"✅ Review summary saved to {summary_file}")

    # Print summary
    print("\n" + "="*80)
    print("REVIEW SUMMARY")
    print("="*80)

    success_count = len([r for r in reviews if "error" not in r])
    error_count = len([r for r in reviews if "error" in r])

    print(f"✅ Successful reviews: {success_count}")
    print(f"❌ Failed reviews: {error_count}")
    print(f"📄 Full reviews: EXTERNAL_REVIEWS.md")
    print(f"📊 JSON data: .orchestrator/external_reviews.json")

if __name__ == "__main__":
    main()

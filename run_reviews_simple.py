#!/usr/bin/env python3
"""
Simple review script using only stdlib and requests
"""

import os
import sys
import json

try:
    import requests
except ImportError:
    print("❌ requests library not available")
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests

def load_prompt():
    """Load review prompt from files"""
    with open("REVIEW_PACKAGE.md") as f:
        review_package = f.read()

    with open("CONTAINMENT_PROPOSAL.md") as f:
        containment = f.read()

    return f"""# Review Request

Please review the following multi-repo support and containment strategy for the workflow-orchestrator project.

{review_package}

---

# Full Technical Specification

{containment}

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

def review_openai(prompt, api_key):
    """Review with OpenAI GPT-4"""
    print("🔍 Reviewing with GPT-4...")

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        json={
            "model": "gpt-4-turbo-preview",
            "messages": [
                {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        },
        timeout=120
    )

    if response.status_code != 200:
        return f"Error: {response.status_code} - {response.text}"

    result = response.json()
    return result["choices"][0]["message"]["content"]

def review_gemini(prompt, api_key):
    """Review with Gemini"""
    print("🔍 Reviewing with Gemini...")

    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        },
        timeout=120
    )

    if response.status_code != 200:
        return f"Error: {response.status_code} - {response.text}"

    result = response.json()
    return result["candidates"][0]["content"]["parts"][0]["text"]

def review_openrouter(prompt, api_key, model):
    """Review with OpenRouter"""
    model_name = model.split("/")[-1]
    print(f"🔍 Reviewing with {model_name}...")

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        },
        timeout=120
    )

    if response.status_code != 200:
        return f"Error: {response.status_code} - {response.text}"

    result = response.json()
    return result["choices"][0]["message"]["content"]

def main():
    """Run all reviews"""
    # Load API keys
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if not all([openai_key, gemini_key, openrouter_key]):
        print("❌ Missing API keys")
        print(f"OPENAI_API_KEY: {'✓' if openai_key else '✗'}")
        print(f"GEMINI_API_KEY: {'✓' if gemini_key else '✗'}")
        print(f"OPENROUTER_API_KEY: {'✓' if openrouter_key else '✗'}")
        sys.exit(1)

    # Load prompt
    prompt = load_prompt()
    print(f"📝 Loaded prompt ({len(prompt)} chars)")

    # Create output dir
    os.makedirs(".orchestrator", exist_ok=True)

    reviews = {}

    # GPT-4
    try:
        review = review_openai(prompt, openai_key)
        with open(".orchestrator/review_gpt4.md", "w") as f:
            f.write(review)
        reviews["gpt4"] = review
        print(f"✅ GPT-4 review complete ({len(review)} chars)")
    except Exception as e:
        print(f"❌ GPT-4 failed: {e}")
        reviews["gpt4"] = f"Error: {e}"

    # Gemini
    try:
        review = review_gemini(prompt, gemini_key)
        with open(".orchestrator/review_gemini.md", "w") as f:
            f.write(review)
        reviews["gemini"] = review
        print(f"✅ Gemini review complete ({len(review)} chars)")
    except Exception as e:
        print(f"❌ Gemini failed: {e}")
        reviews["gemini"] = f"Error: {e}"

    # Claude Opus
    try:
        review = review_openrouter(prompt, openrouter_key, "anthropic/claude-opus")
        with open(".orchestrator/review_claude_opus.md", "w") as f:
            f.write(review)
        reviews["claude_opus"] = review
        print(f"✅ Claude Opus review complete ({len(review)} chars)")
    except Exception as e:
        print(f"❌ Claude Opus failed: {e}")
        reviews["claude_opus"] = f"Error: {e}"

    # DeepSeek
    try:
        review = review_openrouter(prompt, openrouter_key, "deepseek/deepseek-chat")
        with open(".orchestrator/review_deepseek.md", "w") as f:
            f.write(review)
        reviews["deepseek"] = review
        print(f"✅ DeepSeek review complete ({len(review)} chars)")
    except Exception as e:
        print(f"❌ DeepSeek failed: {e}")
        reviews["deepseek"] = f"Error: {e}"

    # Create combined markdown
    print("📝 Creating combined review document...")
    with open("EXTERNAL_REVIEWS.md", "w") as f:
        f.write("# External Model Reviews\n\n")
        f.write("Reviews of the multi-repo support and containment strategy.\n\n")
        f.write("---\n\n")

        f.write("## GPT-4 Turbo (OpenAI)\n\n")
        f.write(reviews.get("gpt4", "No review"))
        f.write("\n\n---\n\n")

        f.write("## Gemini 2.0 Flash Exp (Google)\n\n")
        f.write(reviews.get("gemini", "No review"))
        f.write("\n\n---\n\n")

        f.write("## Claude Opus (Anthropic via OpenRouter)\n\n")
        f.write(reviews.get("claude_opus", "No review"))
        f.write("\n\n---\n\n")

        f.write("## DeepSeek Chat\n\n")
        f.write(reviews.get("deepseek", "No review"))
        f.write("\n\n")

    print("✅ All reviews completed!")
    print("\n" + "="*80)
    print("REVIEW SUMMARY")
    print("="*80)

    success = [k for k, v in reviews.items() if not v.startswith("Error:")]
    print(f"✅ Successful: {len(success)}/{len(reviews)}")
    print(f"📄 Combined: EXTERNAL_REVIEWS.md")
    print(f"📁 Individual: .orchestrator/review_*.md")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Run reviews with correct models:
- GPT-4o/o1 (latest OpenAI)
- Gemini 2.0 Flash
- Claude Opus (native Anthropic API)
- DeepSeek
"""

import os
import sys
import json

try:
    import requests
except ImportError:
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

def review_openai_latest(prompt, api_key):
    """Review with latest OpenAI model (o1 or GPT-4o)"""

    # Try o1-preview first (reasoning model)
    print("🔍 Reviewing with OpenAI o1-preview...")
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            json={
                "model": "o1-preview",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_completion_tokens": 8000
            },
            timeout=180
        )

        if response.status_code == 200:
            result = response.json()
            return {
                "model": "o1-preview",
                "review": result["choices"][0]["message"]["content"]
            }
        else:
            print(f"  o1-preview failed ({response.status_code}), trying gpt-4o...")
    except Exception as e:
        print(f"  o1-preview error: {e}, trying gpt-4o...")

    # Fallback to GPT-4o
    print("🔍 Reviewing with GPT-4o...")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        json={
            "model": "gpt-4o",
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
        return {
            "model": "gpt-4o",
            "error": f"{response.status_code} - {response.text}"
        }

    result = response.json()
    return {
        "model": "gpt-4o",
        "review": result["choices"][0]["message"]["content"]
    }

def review_gemini(prompt, api_key):
    """Review with Gemini 2.0 Flash"""
    print("🔍 Reviewing with Gemini 2.0 Flash...")

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "maxOutputTokens": 8000,
                    "temperature": 0.7
                }
            },
            timeout=120
        )

        if response.status_code != 200:
            return {
                "model": "gemini-2.0-flash-exp",
                "error": f"{response.status_code} - {response.text[:500]}"
            }

        result = response.json()
        return {
            "model": "gemini-2.0-flash-exp",
            "review": result["candidates"][0]["content"]["parts"][0]["text"]
        }
    except Exception as e:
        return {
            "model": "gemini-2.0-flash-exp",
            "error": str(e)
        }

def review_claude_opus(prompt, api_key):
    """Review with Claude Opus (native Anthropic API)"""
    print("🔍 Reviewing with Claude Opus (native Anthropic API)...")

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-opus-4-20250514",
                "max_tokens": 8000,
                "temperature": 0.7,
                "system": "You are an expert software architect reviewing a codebase refactoring proposal.",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=180
        )

        if response.status_code != 200:
            return {
                "model": "claude-opus-4",
                "error": f"{response.status_code} - {response.text[:500]}"
            }

        result = response.json()
        return {
            "model": "claude-opus-4",
            "review": result["content"][0]["text"]
        }
    except Exception as e:
        return {
            "model": "claude-opus-4",
            "error": str(e)
        }

def review_deepseek(prompt, api_key):
    """Review with DeepSeek via OpenRouter"""
    print("🔍 Reviewing with DeepSeek...")

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            json={
                "model": "deepseek/deepseek-chat",
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
            return {
                "model": "deepseek-chat",
                "error": f"{response.status_code} - {response.text[:500]}"
            }

        result = response.json()
        return {
            "model": "deepseek-chat",
            "review": result["choices"][0]["message"]["content"]
        }
    except Exception as e:
        return {
            "model": "deepseek-chat",
            "error": str(e)
        }

def main():
    """Run all reviews"""
    # Load API keys
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    print("API Keys:")
    print(f"  OPENAI_API_KEY: {'✓' if openai_key else '✗'}")
    print(f"  GEMINI_API_KEY: {'✓' if gemini_key else '✗'}")
    print(f"  ANTHROPIC_API_KEY: {'✓' if anthropic_key else '✗'}")
    print(f"  OPENROUTER_API_KEY: {'✓' if openrouter_key else '✗'}")
    print()

    # Load prompt
    prompt = load_prompt()
    print(f"📝 Loaded prompt ({len(prompt)} chars)\n")

    # Create output dir
    os.makedirs(".orchestrator", exist_ok=True)

    reviews = {}

    # 1. OpenAI (o1-preview or GPT-4o)
    if openai_key:
        try:
            result = review_openai_latest(prompt, openai_key)
            if "error" not in result:
                with open(f".orchestrator/review_{result['model'].replace('-', '_')}.md", "w") as f:
                    f.write(result["review"])
                reviews["openai"] = result
                print(f"✅ {result['model']} review complete ({len(result['review'])} chars)\n")
            else:
                print(f"❌ OpenAI failed: {result['error']}\n")
                reviews["openai"] = result
        except Exception as e:
            print(f"❌ OpenAI failed: {e}\n")
            reviews["openai"] = {"model": "openai", "error": str(e)}
    else:
        print("⏭️  Skipping OpenAI (no API key)\n")

    # 2. Gemini
    if gemini_key:
        try:
            result = review_gemini(prompt, gemini_key)
            if "error" not in result:
                with open(".orchestrator/review_gemini_2_0.md", "w") as f:
                    f.write(result["review"])
                reviews["gemini"] = result
                print(f"✅ Gemini review complete ({len(result['review'])} chars)\n")
            else:
                print(f"❌ Gemini failed: {result['error']}\n")
                reviews["gemini"] = result
        except Exception as e:
            print(f"❌ Gemini failed: {e}\n")
            reviews["gemini"] = {"model": "gemini-2.0-flash-exp", "error": str(e)}
    else:
        print("⏭️  Skipping Gemini (no API key)\n")

    # 3. Claude Opus (native)
    if anthropic_key:
        try:
            result = review_claude_opus(prompt, anthropic_key)
            if "error" not in result:
                with open(".orchestrator/review_claude_opus_native.md", "w") as f:
                    f.write(result["review"])
                reviews["claude_opus"] = result
                print(f"✅ Claude Opus review complete ({len(result['review'])} chars)\n")
            else:
                print(f"❌ Claude Opus failed: {result['error']}\n")
                reviews["claude_opus"] = result
        except Exception as e:
            print(f"❌ Claude Opus failed: {e}\n")
            reviews["claude_opus"] = {"model": "claude-opus-4", "error": str(e)}
    else:
        print("⏭️  Skipping Claude Opus (no API key)\n")

    # 4. DeepSeek
    if openrouter_key:
        try:
            result = review_deepseek(prompt, openrouter_key)
            if "error" not in result:
                with open(".orchestrator/review_deepseek.md", "w") as f:
                    f.write(result["review"])
                reviews["deepseek"] = result
                print(f"✅ DeepSeek review complete ({len(result['review'])} chars)\n")
            else:
                print(f"❌ DeepSeek failed: {result['error']}\n")
                reviews["deepseek"] = result
        except Exception as e:
            print(f"❌ DeepSeek failed: {e}\n")
            reviews["deepseek"] = {"model": "deepseek-chat", "error": str(e)}
    else:
        print("⏭️  Skipping DeepSeek (no API key)\n")

    # Create combined markdown
    print("📝 Creating combined review document...")
    with open("EXTERNAL_REVIEWS.md", "w") as f:
        f.write("# External Model Reviews\n\n")
        f.write("Reviews of the multi-repo support and containment strategy.\n\n")
        f.write("---\n\n")

        if "openai" in reviews:
            model = reviews["openai"].get("model", "OpenAI")
            f.write(f"## {model}\n\n")
            if "error" in reviews["openai"]:
                f.write(f"**Error**: {reviews['openai']['error']}\n\n")
            else:
                f.write(reviews["openai"]["review"])
            f.write("\n\n---\n\n")

        if "gemini" in reviews:
            f.write("## Gemini 2.0 Flash Exp (Google)\n\n")
            if "error" in reviews["gemini"]:
                f.write(f"**Error**: {reviews['gemini']['error']}\n\n")
            else:
                f.write(reviews["gemini"]["review"])
            f.write("\n\n---\n\n")

        if "claude_opus" in reviews:
            f.write("## Claude Opus 4 (Anthropic - Native API)\n\n")
            if "error" in reviews["claude_opus"]:
                f.write(f"**Error**: {reviews['claude_opus']['error']}\n\n")
            else:
                f.write(reviews["claude_opus"]["review"])
            f.write("\n\n---\n\n")

        if "deepseek" in reviews:
            f.write("## DeepSeek Chat\n\n")
            if "error" in reviews["deepseek"]:
                f.write(f"**Error**: {reviews['deepseek']['error']}\n\n")
            else:
                f.write(reviews["deepseek"]["review"])
            f.write("\n\n")

    print("✅ Combined reviews saved to EXTERNAL_REVIEWS.md\n")

    # Summary
    print("="*80)
    print("REVIEW SUMMARY")
    print("="*80)

    success = [k for k, v in reviews.items() if "error" not in v]
    total = len(reviews)

    print(f"✅ Successful: {len(success)}/{total}")
    if success:
        print(f"   Models: {', '.join([reviews[k]['model'] for k in success])}")

    failed = [k for k, v in reviews.items() if "error" in v]
    if failed:
        print(f"❌ Failed: {len(failed)}/{total}")
        print(f"   Models: {', '.join([reviews[k]['model'] for k in failed])}")

    print(f"\n📄 Combined: EXTERNAL_REVIEWS.md")
    print(f"📁 Individual: .orchestrator/review_*.md")

if __name__ == "__main__":
    main()

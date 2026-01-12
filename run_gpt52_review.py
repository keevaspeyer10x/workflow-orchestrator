#!/usr/bin/env python3
"""
Run review with GPT-5.2
"""

import os
import sys
import json

try:
    import requests
except ImportError:
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

def try_gpt52(prompt, api_key, model="gpt-5.2"):
    """Try different configurations for GPT-5.2"""

    configs = [
        # Config 1: Standard chat format
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert software architect reviewing a codebase refactoring proposal."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 8000,
            "temperature": 0.7
        },
        # Config 2: No system message
        {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 8000,
            "temperature": 0.7
        },
        # Config 3: max_completion_tokens instead of max_tokens
        {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_completion_tokens": 8000,
            "temperature": 0.7
        },
        # Config 4: Different alias
        {
            "model": "gpt-5.2-chat-latest",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_completion_tokens": 8000
        },
    ]

    for i, config in enumerate(configs, 1):
        print(f"\n🧪 Trying configuration {i} (model: {config['model']})...")

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                json=config,
                timeout=180
            )

            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                review = result["choices"][0]["message"]["content"]
                print(f"   ✅ Success! Got {len(review)} chars")
                return {
                    "model": config["model"],
                    "review": review,
                    "config": i
                }
            else:
                error = response.json() if response.text else {}
                print(f"   ❌ Error: {error.get('error', {}).get('message', response.text[:200])}")

        except Exception as e:
            print(f"   ❌ Exception: {e}")

    return None

def main():
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        sys.exit(1)

    print("GPT-5.2 Review Runner\n")

    # Load prompt
    prompt = load_prompt()
    print(f"📝 Loaded prompt ({len(prompt)} chars)\n")

    # Try GPT-5.2
    result = try_gpt52(prompt, api_key)

    if result:
        print(f"\n✅ GPT-5.2 review successful!")
        print(f"   Model: {result['model']}")
        print(f"   Config: {result['config']}")
        print(f"   Length: {len(result['review'])} chars")

        # Save review
        os.makedirs(".orchestrator", exist_ok=True)
        with open(".orchestrator/review_gpt_5_2.md", "w") as f:
            f.write(result["review"])

        print(f"\n📄 Saved to .orchestrator/review_gpt_5_2.md")

        # Update combined reviews
        print(f"📝 Updating EXTERNAL_REVIEWS.md...")

        # Read existing reviews
        with open("EXTERNAL_REVIEWS.md", "r") as f:
            content = f.read()

        # Add GPT-5.2 review at the top
        new_content = f"""# External Model Reviews

Reviews of the multi-repo support and containment strategy.

---

## GPT-5.2 (OpenAI)

{result['review']}

---

"""
        # Append rest of content (skip first heading)
        lines = content.split('\n')
        rest_start = next(i for i, line in enumerate(lines) if line.startswith('## '))
        new_content += '\n'.join(lines[rest_start:])

        with open("EXTERNAL_REVIEWS.md", "w") as f:
            f.write(new_content)

        print("✅ Updated EXTERNAL_REVIEWS.md")

    else:
        print(f"\n❌ All configurations failed")
        print(f"\nNote: GPT-5.2 may require:")
        print(f"  - Beta access / allowlist")
        print(f"  - Special API endpoint")
        print(f"  - Different authentication")

if __name__ == "__main__":
    main()

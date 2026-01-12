#!/usr/bin/env python3
"""Check available OpenAI models"""

import os
import sys

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests

def list_openai_models(api_key):
    """List available OpenAI models"""
    print("🔍 Fetching OpenAI models list...")

    response = requests.get(
        "https://api.openai.com/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}"
        },
        timeout=30
    )

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text[:500])
        return []

    models = response.json()["data"]

    # Filter for chat/completion models
    chat_models = [
        m["id"] for m in models
        if any(x in m["id"] for x in ["gpt", "o1", "o3"])
        and "instruct" not in m["id"]
    ]

    return sorted(chat_models, reverse=True)

def test_model(api_key, model_id):
    """Test if a model works"""
    print(f"Testing {model_id}...", end=" ")

    try:
        # For o1 models, don't use system message
        if "o1" in model_id or "o3" in model_id:
            messages = [{"role": "user", "content": "Say 'working' if you can read this."}]
        else:
            messages = [
                {"role": "system", "content": "Test"},
                {"role": "user", "content": "Say 'working' if you can read this."}
            ]

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            json={
                "model": model_id,
                "messages": messages,
                "max_tokens": 10
            },
            timeout=30
        )

        if response.status_code == 200:
            print("✅ Works")
            return True
        else:
            print(f"❌ {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ {e}")
        return False

def main():
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        sys.exit(1)

    print("OpenAI Model Checker\n")

    # List all models
    models = list_openai_models(api_key)

    print(f"\n📋 Found {len(models)} chat models:\n")
    for model in models:
        print(f"  - {model}")

    # Test specific models
    print("\n🧪 Testing models for reviews:\n")

    test_models = [
        "gpt-5.2",
        "gpt-5",
        "o3",
        "o3-mini",
        "o1",
        "o1-preview",
        "o1-mini",
        "gpt-4o",
        "gpt-4-turbo",
    ]

    working_models = []
    for model in test_models:
        if test_model(api_key, model):
            working_models.append(model)

    print(f"\n✅ Working models: {working_models}")
    print(f"\nBest model for review: {working_models[0] if working_models else 'None'}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Populate context, tags, and risk_level for existing patterns.

Usage:
    python scripts/populate_pattern_context.py
"""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from healing.context_extraction import extract_context


# Risk keywords
HIGH_RISK_KEYWORDS = ['credential', 'secret', 'password', 'api_key', 'token', 'private_key']
MEDIUM_RISK_KEYWORDS = ['permission', 'auth', 'login', 'session', 'cookie', 'jwt', 'oauth']


def determine_risk_level(description: str, error_category: str | None) -> str:
    """Determine risk level from description and category."""
    desc_lower = description.lower()

    # High risk: touching secrets/credentials
    if any(kw in desc_lower for kw in HIGH_RISK_KEYWORDS):
        return 'high'

    # Medium risk: auth/permission related
    if any(kw in desc_lower for kw in MEDIUM_RISK_KEYWORDS):
        return 'medium'

    # Medium risk: permission category errors
    if error_category == 'permission':
        return 'medium'

    # Default: low risk
    return 'low'


async def main():
    try:
        from supabase import acreate_client
    except ImportError:
        print("❌ supabase not installed. Run: pip install supabase")
        return 1

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
        print("❌ SUPABASE_URL and SUPABASE_KEY must be set")
        return 1

    print("🔌 Connecting to Supabase...")
    client = await acreate_client(url, key)

    # Fetch all patterns
    print("📥 Fetching patterns...")
    result = await client.table("error_patterns").select("id, fingerprint, description").execute()
    patterns = result.data or []
    print(f"   Found {len(patterns)} patterns\n")

    if not patterns:
        print("No patterns to update")
        return 0

    # Process each pattern
    updated = 0
    errors = 0

    for p in patterns:
        pattern_id = p.get("id")
        description = p.get("description", "")
        fingerprint = p.get("fingerprint", "")[:16]

        # Extract context
        context = extract_context(description)
        context_dict = context.to_dict()
        tags = context.derive_tags()

        # Determine risk level
        risk_level = determine_risk_level(description, context.error_category)

        # Update pattern
        try:
            await (
                client.table("error_patterns")
                .update({
                    "context": context_dict,
                    "tags": tags,
                    "risk_level": risk_level,
                })
                .eq("id", pattern_id)
                .execute()
            )

            # Show what was set
            ctx_summary = []
            if context.language:
                ctx_summary.append(f"lang={context.language}")
            if context.error_category:
                ctx_summary.append(f"cat={context.error_category}")
            if risk_level != 'low':
                ctx_summary.append(f"risk={risk_level}")

            status = ", ".join(ctx_summary) if ctx_summary else "no context extracted"
            print(f"  ✓ {fingerprint}: {status}")
            updated += 1

        except Exception as e:
            print(f"  ✗ {fingerprint}: {e}")
            errors += 1

    print(f"\n✅ Done: {updated} updated, {errors} errors")
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))

#!/usr/bin/env python3
"""Analyze what context we'd extract from existing patterns.

Run this to see what would be backfilled before committing.

Usage:
    python scripts/analyze_backfill.py
    python scripts/analyze_backfill.py --apply  # Actually apply the backfill
"""

import argparse
import asyncio
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from healing.context_extraction import extract_context, detect_language, detect_error_category


# Confidence threshold for backfill
BACKFILL_THRESHOLD = 0.8


async def get_supabase_client():
    """Get Supabase client."""
    try:
        from supabase import acreate_client

        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

        if not url or not key:
            print("❌ SUPABASE_URL and SUPABASE_KEY must be set")
            return None

        return await acreate_client(url, key)
    except Exception as e:
        print(f"❌ Failed to create Supabase client: {e}")
        return None


async def fetch_patterns(client):
    """Fetch all patterns from Supabase."""
    try:
        result = await (
            client.table("error_patterns")
            .select("id, fingerprint, description, context, tags")
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"❌ Failed to fetch patterns: {e}")
        return []


def analyze_pattern(pattern: dict) -> dict:
    """Analyze what context we'd extract from a pattern."""
    description = pattern.get("description", "")

    # Extract context
    context = extract_context(description)

    # Determine what we'd backfill
    result = {
        "id": pattern.get("id"),
        "fingerprint": pattern.get("fingerprint"),
        "description_preview": description[:80] + "..." if len(description) > 80 else description,
        "existing_context": pattern.get("context"),
        "existing_tags": pattern.get("tags"),
        "extracted_context": context.to_dict(),
        "extracted_tags": context.derive_tags(),
        "confidence": context.extraction_confidence,
        "would_backfill": context.extraction_confidence >= BACKFILL_THRESHOLD,
        "reason": "",
    }

    # Add reason
    if context.extraction_confidence >= BACKFILL_THRESHOLD:
        reasons = []
        if context.language:
            reasons.append(f"language={context.language}")
        if context.error_category:
            reasons.append(f"category={context.error_category}")
        result["reason"] = ", ".join(reasons) if reasons else "high confidence"
    elif context.extraction_confidence > 0:
        result["reason"] = f"low confidence ({context.extraction_confidence:.2f})"
    else:
        result["reason"] = "no signal in description"

    return result


async def apply_backfill(client, patterns_to_update: list[dict]):
    """Apply the backfill to Supabase."""
    print(f"\n🔄 Applying backfill to {len(patterns_to_update)} patterns...")

    success = 0
    failed = 0

    for p in patterns_to_update:
        try:
            await (
                client.table("error_patterns")
                .update({
                    "context": p["extracted_context"],
                    "tags": p["extracted_tags"],
                })
                .eq("id", p["id"])
                .execute()
            )
            success += 1
            print(f"  ✓ {p['fingerprint'][:16]}: {p['reason']}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {p['fingerprint'][:16]}: {e}")

    print(f"\n✅ Backfill complete: {success} updated, {failed} failed")


async def main():
    parser = argparse.ArgumentParser(description="Analyze/apply context backfill")
    parser.add_argument("--apply", action="store_true", help="Actually apply the backfill")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Get client
    client = await get_supabase_client()
    if not client:
        return 1

    # Fetch patterns
    print("📥 Fetching patterns from Supabase...")
    patterns = await fetch_patterns(client)
    print(f"   Found {len(patterns)} patterns\n")

    if not patterns:
        print("No patterns to analyze")
        return 0

    # Analyze each pattern
    results = [analyze_pattern(p) for p in patterns]

    # Categorize
    would_backfill = [r for r in results if r["would_backfill"]]
    low_confidence = [r for r in results if not r["would_backfill"] and r["confidence"] > 0]
    no_signal = [r for r in results if r["confidence"] == 0]
    already_has_context = [r for r in results if r["existing_context"]]

    if args.json:
        print(json.dumps({
            "total": len(results),
            "would_backfill": len(would_backfill),
            "low_confidence": len(low_confidence),
            "no_signal": len(no_signal),
            "already_has_context": len(already_has_context),
            "patterns": results,
        }, indent=2))
        return 0

    # Print summary
    print("=" * 60)
    print("BACKFILL ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Total patterns:           {len(results)}")
    print(f"Already have context:     {len(already_has_context)}")
    print(f"Would backfill (≥{BACKFILL_THRESHOLD}):    {len(would_backfill)}")
    print(f"Low confidence (<{BACKFILL_THRESHOLD}):    {len(low_confidence)}")
    print(f"No signal:                {len(no_signal)}")
    print("=" * 60)

    # Show what would be backfilled
    if would_backfill:
        print(f"\n✅ WOULD BACKFILL ({len(would_backfill)} patterns):\n")
        for r in would_backfill[:20]:  # Show first 20
            print(f"  {r['fingerprint'][:16]}: {r['reason']}")
            print(f"    → {r['description_preview']}")
            print(f"    → context: {r['extracted_context']}")
            print(f"    → tags: {r['extracted_tags']}")
            print()

        if len(would_backfill) > 20:
            print(f"  ... and {len(would_backfill) - 20} more\n")

    # Show low confidence
    if low_confidence:
        print(f"\n⚠️  LOW CONFIDENCE ({len(low_confidence)} patterns) - would skip:\n")
        for r in low_confidence[:5]:
            print(f"  {r['fingerprint'][:16]}: confidence={r['confidence']:.2f}")
            print(f"    → {r['description_preview']}")
            print()

    # Apply if requested
    if args.apply:
        if not would_backfill:
            print("\n❌ Nothing to backfill")
            return 0

        confirm = input(f"\n⚠️  Apply backfill to {len(would_backfill)} patterns? [y/N] ")
        if confirm.lower() == 'y':
            await apply_backfill(client, would_backfill)
        else:
            print("Aborted")
    else:
        if would_backfill:
            print(f"\n💡 Run with --apply to backfill {len(would_backfill)} patterns")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))

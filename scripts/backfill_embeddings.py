#!/usr/bin/env python3
"""Backfill embeddings for existing learnings.

This script generates embeddings for learnings that don't have them.
Embeddings enable semantic (RAG) search for similar errors.

Usage:
    # Dry run - show what would be updated
    python scripts/backfill_embeddings.py --dry-run

    # Actually generate embeddings (requires OPENAI_API_KEY)
    python scripts/backfill_embeddings.py

    # Force re-generate all embeddings
    python scripts/backfill_embeddings.py --force

Requirements:
    - OPENAI_API_KEY environment variable
    - SUPABASE_URL and SUPABASE_SERVICE_KEY (or secrets file)
"""

import asyncio
import argparse
import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    parser = argparse.ArgumentParser(description="Backfill embeddings for learnings")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    parser.add_argument("--force", action="store_true", help="Re-generate all embeddings")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size (default: 10)")
    args = parser.parse_args()

    # Load secrets if available
    secrets_file = "/tmp/supabase_secrets.yaml"
    if os.path.exists(secrets_file):
        try:
            import yaml
            with open(secrets_file) as f:
                secrets = yaml.safe_load(f)
            os.environ.setdefault("SUPABASE_URL", secrets.get("SUPABASE_URL", ""))
            os.environ.setdefault("SUPABASE_SERVICE_KEY", secrets.get("SUPABASE_SERVICE_KEY", ""))
        except Exception as e:
            print(f"Warning: Could not load secrets file: {e}")

    # Check required environment variables
    openai_key = os.environ.get("OPENAI_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        print("  Set via environment variables or /tmp/supabase_secrets.yaml")
        sys.exit(1)

    if not args.dry_run and not openai_key:
        print("Error: OPENAI_API_KEY required for generating embeddings")
        print("  Set via: export OPENAI_API_KEY='sk-...'")
        print("  Or run with --dry-run to see what needs updating")
        sys.exit(1)

    # Import dependencies
    try:
        from supabase import create_client
        import openai
    except ImportError as e:
        print(f"Error: Missing dependency: {e}")
        print("  Run: pip install supabase openai")
        sys.exit(1)

    # Connect to Supabase
    supabase = create_client(supabase_url, supabase_key)

    # Get learnings needing embeddings
    if args.force:
        query = supabase.table("learnings").select("id, title, description")
    else:
        query = supabase.table("learnings").select("id, title, description").is_("embedding", "null")

    result = query.execute()
    learnings = result.data

    print(f"=== Embedding Backfill ===")
    print(f"  Learnings needing embeddings: {len(learnings)}")

    if not learnings:
        print("  All learnings already have embeddings!")
        return

    if args.dry_run:
        print("\n  Learnings to process:")
        for l in learnings[:10]:
            print(f"    - {l['title']}")
        if len(learnings) > 10:
            print(f"    ... and {len(learnings) - 10} more")
        print("\n  Run without --dry-run to generate embeddings")
        return

    # Initialize OpenAI client
    client = openai.AsyncOpenAI(api_key=openai_key)

    # Process in batches
    updated = 0
    errors = 0

    for i in range(0, len(learnings), args.batch_size):
        batch = learnings[i:i + args.batch_size]
        print(f"\n  Processing batch {i // args.batch_size + 1} ({len(batch)} items)...")

        for learning in batch:
            # Create text for embedding
            text = f"{learning['title']}: {learning['description']}"

            try:
                # Generate embedding
                response = await client.embeddings.create(
                    model="text-embedding-ada-002",
                    input=text
                )
                embedding = response.data[0].embedding

                # Update in Supabase
                supabase.table("learnings").update({
                    "embedding": embedding,
                    "embedding_model": "text-embedding-ada-002"
                }).eq("id", learning["id"]).execute()

                print(f"    + {learning['title']}")
                updated += 1

            except Exception as e:
                print(f"    ! {learning['title']}: {e}")
                errors += 1

        # Small delay between batches to avoid rate limits
        if i + args.batch_size < len(learnings):
            await asyncio.sleep(0.5)

    print(f"\n=== Results ===")
    print(f"  Updated: {updated}")
    print(f"  Errors: {errors}")

    # Verify
    with_embeddings = supabase.table("learnings").select("id", count="exact").not_.is_("embedding", "null").execute()
    total = supabase.table("learnings").select("id", count="exact").execute()
    print(f"  Learnings with embeddings: {with_embeddings.count}/{total.count}")


if __name__ == "__main__":
    asyncio.run(main())

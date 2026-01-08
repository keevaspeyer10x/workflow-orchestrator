"""
Pattern hashing for conflict similarity matching.

Uses a simplified MinHash-like approach to compute fuzzy hashes
that allow similar conflicts to be identified.
"""

import hashlib
import re
from typing import Optional


class PatternHasher:
    """
    Computes fuzzy hashes for conflict patterns.

    The hash is designed so that similar conflicts produce similar hashes,
    enabling pattern matching and reuse of past resolutions.
    """

    # Number of hash functions for MinHash-like signature
    NUM_HASHES = 64

    # Patterns to normalize in file paths
    UUID_PATTERN = re.compile(r'[a-f0-9]{8}[-_]?[a-f0-9]{4}[-_]?[a-f0-9]{4}[-_]?[a-f0-9]{4}[-_]?[a-f0-9]{12}', re.I)
    TIMESTAMP_PATTERN = re.compile(r'\d{4}[-_]\d{2}[-_]\d{2}[_T-]?\d{2}[-_:]?\d{2}[-_:]?\d{2}')
    NUMERIC_SUFFIX_PATTERN = re.compile(r'_\d+$|_v\d+')

    def __init__(self, num_hashes: int = NUM_HASHES):
        """
        Initialize the hasher.

        Args:
            num_hashes: Number of hash functions for the signature
        """
        self._num_hashes = num_hashes
        # Pre-compute hash seeds
        self._seeds = [self._generate_seed(i) for i in range(num_hashes)]
        # Cache tokens for similarity comparison
        self._token_cache: dict[str, set[str]] = {}

    def _generate_seed(self, index: int) -> int:
        """Generate a deterministic seed for hash function i."""
        return int(hashlib.md5(f"seed_{index}".encode()).hexdigest()[:8], 16)

    def compute_hash(
        self,
        conflict_type: str,
        files_involved: list[str],
        intent_categories: list[str],
    ) -> str:
        """
        Compute a fuzzy hash for a conflict.

        Args:
            conflict_type: Type of conflict (textual, semantic, etc.)
            files_involved: Files involved in the conflict
            intent_categories: Categories of intent (bug_fix, feature, etc.)

        Returns:
            A hex string hash that can be compared for similarity
        """
        tokens = self.extract_tokens(conflict_type, files_involved, intent_categories)

        # Compute MinHash signature
        signature = self._compute_signature(tokens)

        # Convert signature to hex string
        hash_str = self._signature_to_hash(signature)

        # Store tokens in cache for similarity comparison
        self._token_cache[hash_str] = tokens

        return hash_str

    def _normalize_path(self, path: str) -> str:
        """
        Normalize a file path by removing unique identifiers.

        Args:
            path: Original file path

        Returns:
            Normalized path with UUIDs, timestamps, etc. replaced
        """
        normalized = path

        # Replace UUIDs with placeholder
        normalized = self.UUID_PATTERN.sub("<UUID>", normalized)

        # Replace timestamps with placeholder
        normalized = self.TIMESTAMP_PATTERN.sub("<TIMESTAMP>", normalized)

        # Replace numeric suffixes with placeholder
        normalized = self.NUMERIC_SUFFIX_PATTERN.sub("<NUM>", normalized)

        return normalized

    def _compute_signature(self, tokens: set[str]) -> list[int]:
        """
        Compute a MinHash-like signature for a set of tokens.

        Args:
            tokens: Set of string tokens

        Returns:
            List of minimum hash values (signature)
        """
        if not tokens:
            # Return a default signature for empty sets
            return [0] * self._num_hashes

        signature = []

        for seed in self._seeds:
            min_hash = float('inf')
            for token in tokens:
                # Hash the token with this seed
                h = self._hash_with_seed(token, seed)
                if h < min_hash:
                    min_hash = h
            signature.append(min_hash if min_hash != float('inf') else 0)

        return signature

    def _hash_with_seed(self, token: str, seed: int) -> int:
        """Compute hash of token with a given seed."""
        combined = f"{seed}:{token}"
        return int(hashlib.md5(combined.encode()).hexdigest()[:8], 16)

    def _signature_to_hash(self, signature: list[int]) -> str:
        """Convert a signature to a compact hex hash."""
        # Pack signature into bytes and hash
        sig_str = ":".join(str(h) for h in signature)
        return hashlib.sha256(sig_str.encode()).hexdigest()[:32]

    def compute_similarity(self, hash1: str, hash2: str) -> float:
        """
        Compute similarity between two hashes.

        Uses cached tokens for accurate Jaccard similarity when available,
        falls back to hash-based estimate otherwise.

        Args:
            hash1: First pattern hash
            hash2: Second pattern hash

        Returns:
            Similarity score from 0.0 to 1.0
        """
        if hash1 == hash2:
            return 1.0

        # Use cached tokens for accurate similarity
        tokens1 = self._token_cache.get(hash1)
        tokens2 = self._token_cache.get(hash2)

        if tokens1 is not None and tokens2 is not None:
            return self.compute_similarity_from_tokens(tokens1, tokens2)

        # Fall back to hash-based estimate
        return self._estimate_similarity_from_hashes(hash1, hash2)

    def _estimate_similarity_from_hashes(self, hash1: str, hash2: str) -> float:
        """
        Estimate similarity from compressed hashes.

        Uses character-level similarity as a rough approximation.
        """
        if len(hash1) != len(hash2):
            return 0.0

        matches = sum(1 for a, b in zip(hash1, hash2) if a == b)
        return matches / len(hash1)

    def compute_similarity_from_tokens(
        self,
        tokens1: set[str],
        tokens2: set[str],
    ) -> float:
        """
        Compute exact similarity from token sets.

        This gives more accurate results than comparing compressed hashes.

        Args:
            tokens1: First set of tokens
            tokens2: Second set of tokens

        Returns:
            Jaccard similarity (0.0 to 1.0)
        """
        if not tokens1 and not tokens2:
            return 1.0
        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def extract_tokens(
        self,
        conflict_type: str,
        files_involved: list[str],
        intent_categories: list[str],
    ) -> set[str]:
        """
        Extract tokens from conflict characteristics.

        Useful for direct similarity comparison without hash compression.

        Args:
            conflict_type: Type of conflict
            files_involved: Files in conflict
            intent_categories: Intent categories

        Returns:
            Set of tokens representing the conflict
        """
        tokens = set()

        tokens.add(f"type:{conflict_type}")

        for file_path in files_involved:
            normalized = self._normalize_path(file_path)
            parts = normalized.split("/")
            for i, part in enumerate(parts):
                tokens.add(f"path:{i}:{part}")
            if "." in parts[-1]:
                ext = parts[-1].rsplit(".", 1)[-1]
                tokens.add(f"ext:{ext}")

        for intent in intent_categories:
            tokens.add(f"intent:{intent}")

        return tokens

"""Embedding Service - Phase 2 Pattern Memory & Lookup.

Generates embeddings for semantic search (Tier 2 lookup).
Uses OpenAI's text-embedding-ada-002 model.
"""

import logging
from typing import Optional, TYPE_CHECKING

try:
    import openai
except ImportError:
    openai = None  # type: ignore

if TYPE_CHECKING:
    from .models import ErrorEvent


logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings for RAG-based pattern lookup.

    This service wraps OpenAI's embedding API and provides:
    - Graceful failure when API key is not available
    - Error handling for API failures
    - Consistent text formatting for errors

    Usage:
        service = EmbeddingService(api_key=os.environ.get("OPENAI_API_KEY"))
        if service.available:
            embedding = await service.embed("Error message")
    """

    DEFAULT_MODEL = "text-embedding-ada-002"
    EMBEDDING_DIMENSION = 1536  # ada-002 outputs 1536-dimensional vectors

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
    ):
        """Initialize the embedding service.

        Args:
            api_key: OpenAI API key. If None or empty, service is unavailable.
            model: Embedding model to use. Defaults to text-embedding-ada-002.
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self._client = None

        # Initialize client if API key is available
        if self.available and openai is not None:
            self._client = openai.AsyncOpenAI(api_key=self.api_key)

    @property
    def available(self) -> bool:
        """Check if the embedding service is available.

        Returns:
            True if API key is set and openai module is available
        """
        return bool(self.api_key) and openai is not None

    async def embed(self, text: str) -> Optional[list[float]]:
        """Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector) or None if unavailable/error
        """
        if not self.available or not self._client:
            return None

        try:
            response = await self._client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None

    async def embed_error(self, error: "ErrorEvent") -> Optional[list[float]]:
        """Generate embedding for an error event.

        Combines relevant error fields into a single text for embedding.
        This ensures consistent representation across different error types.

        Args:
            error: ErrorEvent to embed

        Returns:
            List of floats (embedding vector) or None if unavailable/error
        """
        if not self.available:
            return None

        # Build text from error fields
        parts = []

        if error.error_type:
            parts.append(error.error_type)

        if error.description:
            parts.append(error.description)

        if error.file_path:
            parts.append(f"in {error.file_path}")

        text = ": ".join(parts[:2])  # "ErrorType: Description"
        if len(parts) > 2:
            text += f" {parts[2]}"  # "... in filepath"

        if not text:
            text = error.description or "Unknown error"

        return await self.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings (or None for failures)
        """
        if not self.available:
            return [None] * len(texts)

        results = []
        for text in texts:
            embedding = await self.embed(text)
            results.append(embedding)

        return results

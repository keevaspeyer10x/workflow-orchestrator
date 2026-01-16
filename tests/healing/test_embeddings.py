"""Tests for EmbeddingService - Phase 2 Pattern Memory & Lookup."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock


class TestEmbeddingService:
    """Tests for OpenAI embedding generation."""

    @pytest.mark.asyncio
    async def test_embed_text_returns_vector(self):
        """Returns 1536-dimensional vector for text."""
        from src.healing.embeddings import EmbeddingService

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]

        with patch("src.healing.embeddings.openai") as mock_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = EmbeddingService(api_key="sk-test-key")
            result = await service.embed("Test error message")

            assert result is not None
            assert len(result) == 1536
            assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_embed_error_combines_fields(self):
        """Combines error type and description for embedding."""
        from src.healing.embeddings import EmbeddingService
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.2] * 1536)]

        with patch("src.healing.embeddings.openai") as mock_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = EmbeddingService(api_key="sk-test-key")
            error = ErrorEvent(
                error_id="err-123",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="Module not found",
                error_type="ModuleNotFoundError",
            )
            result = await service.embed_error(error)

            assert result is not None
            assert len(result) == 1536
            # Verify the call included error type and description
            call_args = mock_client.embeddings.create.call_args
            assert "ModuleNotFoundError" in call_args.kwargs["input"]
            assert "Module not found" in call_args.kwargs["input"]

    @pytest.mark.asyncio
    async def test_embed_error_includes_file_path(self):
        """Includes file path in embedding text when present."""
        from src.healing.embeddings import EmbeddingService
        from src.healing.models import ErrorEvent

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.3] * 1536)]

        with patch("src.healing.embeddings.openai") as mock_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = EmbeddingService(api_key="sk-test-key")
            error = ErrorEvent(
                error_id="err-456",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description="Import failed",
                file_path="src/main.py",
            )
            result = await service.embed_error(error)

            call_args = mock_client.embeddings.create.call_args
            assert "src/main.py" in call_args.kwargs["input"]

    @pytest.mark.asyncio
    async def test_embed_no_api_key_returns_none(self):
        """Returns None gracefully when no API key provided."""
        from src.healing.embeddings import EmbeddingService

        service = EmbeddingService(api_key=None)
        result = await service.embed("Test message")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_empty_api_key_returns_none(self):
        """Returns None gracefully when API key is empty string."""
        from src.healing.embeddings import EmbeddingService

        service = EmbeddingService(api_key="")
        result = await service.embed("Test message")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_api_error_returns_none(self):
        """Returns None gracefully on API error."""
        from src.healing.embeddings import EmbeddingService

        with patch("src.healing.embeddings.openai") as mock_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(side_effect=Exception("API Error"))
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = EmbeddingService(api_key="sk-test-key")
            result = await service.embed("Test message")

            assert result is None

    @pytest.mark.asyncio
    async def test_embed_rate_limit_returns_none(self):
        """Returns None gracefully on rate limit."""
        from src.healing.embeddings import EmbeddingService

        with patch("src.healing.embeddings.openai") as mock_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                side_effect=Exception("Rate limit exceeded")
            )
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = EmbeddingService(api_key="sk-test-key")
            result = await service.embed("Test message")

            assert result is None

    @pytest.mark.asyncio
    async def test_embed_uses_ada_002_by_default(self):
        """Uses text-embedding-ada-002 model by default."""
        from src.healing.embeddings import EmbeddingService

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]

        with patch("src.healing.embeddings.openai") as mock_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = EmbeddingService(api_key="sk-test-key")
            await service.embed("Test")

            call_args = mock_client.embeddings.create.call_args
            assert call_args.kwargs["model"] == "text-embedding-ada-002"

    @pytest.mark.asyncio
    async def test_embed_custom_model(self):
        """Uses custom model when specified."""
        from src.healing.embeddings import EmbeddingService

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1] * 3072)]  # Different dimension

        with patch("src.healing.embeddings.openai") as mock_openai:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            service = EmbeddingService(api_key="sk-test-key", model="text-embedding-3-large")
            await service.embed("Test")

            call_args = mock_client.embeddings.create.call_args
            assert call_args.kwargs["model"] == "text-embedding-3-large"

    def test_embedding_service_available_property_with_key(self):
        """Returns True when API key is set."""
        from src.healing.embeddings import EmbeddingService

        service = EmbeddingService(api_key="sk-test-key")
        assert service.available is True

    def test_embedding_service_available_property_without_key(self):
        """Returns False when API key is None."""
        from src.healing.embeddings import EmbeddingService

        service = EmbeddingService(api_key=None)
        assert service.available is False

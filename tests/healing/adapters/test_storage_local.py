"""Tests for local storage adapter."""

import pytest
import tempfile
from pathlib import Path


class TestLocalStorageAdapter:
    """Test LocalStorageAdapter functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def adapter(self, temp_dir):
        """Create a LocalStorageAdapter instance."""
        from src.healing.adapters.storage_local import LocalStorageAdapter

        return LocalStorageAdapter(base_path=temp_dir)

    @pytest.mark.asyncio
    async def test_read_file_existing(self, adapter, temp_dir):
        """STL-001: read_file() should return content for existing file."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("hello world")

        result = await adapter.read_file("test.txt")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_read_file_nonexistent(self, adapter):
        """STL-002: read_file() should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            await adapter.read_file("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_write_file_new(self, adapter, temp_dir):
        """STL-003: write_file() should create new file."""
        await adapter.write_file("new_file.txt", "content")

        assert (temp_dir / "new_file.txt").exists()
        assert (temp_dir / "new_file.txt").read_text() == "content"

    @pytest.mark.asyncio
    async def test_write_file_overwrite(self, adapter, temp_dir):
        """STL-004: write_file() should overwrite existing file."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("old content")

        await adapter.write_file("test.txt", "new content")

        assert test_file.read_text() == "new content"

    @pytest.mark.asyncio
    async def test_file_exists_true(self, adapter, temp_dir):
        """STL-005: file_exists() should return True for existing file."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        result = await adapter.file_exists("test.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_false(self, adapter):
        """STL-006: file_exists() should return False for non-existent file."""
        result = await adapter.file_exists("nonexistent.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_files_with_pattern(self, adapter, temp_dir):
        """STL-007: list_files() should return matching files."""
        (temp_dir / "test1.py").write_text("")
        (temp_dir / "test2.py").write_text("")
        (temp_dir / "other.txt").write_text("")

        result = await adapter.list_files("*.py")

        assert len(result) == 2
        assert "test1.py" in result
        assert "test2.py" in result

    @pytest.mark.asyncio
    async def test_list_files_empty(self, adapter, temp_dir):
        """STL-008: list_files() should return empty list for no matches."""
        result = await adapter.list_files("*.nonexistent")
        assert result == []

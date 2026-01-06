"""
Tests for the provider abstraction layer.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

from src.providers import (
    get_provider,
    list_providers,
    register_provider,
    AgentProvider,
    ExecutionResult,
    OpenRouterProvider,
    ClaudeCodeProvider,
    ManualProvider,
)
from src.providers.base import AgentProvider as BaseAgentProvider


class TestProviderRegistry:
    """Tests for the provider registry."""
    
    def test_list_providers(self):
        """Test that list_providers returns expected providers."""
        providers = list_providers()
        assert 'openrouter' in providers
        assert 'claude_code' in providers
        assert 'manual' in providers
    
    def test_get_provider_by_name(self):
        """Test getting a provider by explicit name."""
        provider = get_provider(name='manual')
        assert provider.name() == 'manual'
        assert isinstance(provider, ManualProvider)
    
    def test_get_provider_unknown_name(self):
        """Test that unknown provider name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_provider(name='unknown_provider')
        assert 'Unknown provider' in str(exc_info.value)
    
    @patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'})
    def test_auto_detect_openrouter(self):
        """Test auto-detection selects OpenRouter when API key is present."""
        provider = get_provider()
        assert provider.name() == 'openrouter'
    
    @patch.dict(os.environ, {}, clear=True)
    def test_auto_detect_fallback_to_manual(self):
        """Test auto-detection falls back to manual when nothing else available."""
        # Clear OPENROUTER_API_KEY and mock Claude Code as unavailable
        with patch.object(ClaudeCodeProvider, 'is_available', return_value=False):
            provider = get_provider()
            assert provider.name() == 'manual'


class TestAgentProviderInterface:
    """Tests for the AgentProvider abstract base class."""
    
    def test_cannot_instantiate_abc(self):
        """Test that AgentProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseAgentProvider()
    
    def test_execution_result_dataclass(self):
        """Test ExecutionResult dataclass."""
        result = ExecutionResult(
            success=True,
            output="test output",
            model_used="test-model",
            tokens_used=100,
            duration_seconds=1.5
        )
        assert result.success is True
        assert result.output == "test output"
        assert result.model_used == "test-model"
        assert result.tokens_used == 100
        assert result.duration_seconds == 1.5
        assert result.metadata == {}
    
    def test_execution_result_defaults(self):
        """Test ExecutionResult default values."""
        result = ExecutionResult(success=False, output="")
        assert result.error is None
        assert result.model_used is None
        assert result.tokens_used is None
        assert result.metadata == {}


class TestOpenRouterProvider:
    """Tests for the OpenRouter provider."""
    
    def test_name(self):
        """Test provider name."""
        provider = OpenRouterProvider()
        assert provider.name() == 'openrouter'
    
    def test_is_available_without_key(self):
        """Test is_available returns False without API key."""
        with patch.dict(os.environ, {}, clear=True):
            provider = OpenRouterProvider()
            assert provider.is_available() is False
    
    @patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-key'})
    def test_is_available_with_key(self):
        """Test is_available returns True with API key."""
        provider = OpenRouterProvider()
        assert provider.is_available() is True
    
    def test_default_model(self):
        """Test default model is set."""
        provider = OpenRouterProvider()
        assert provider.get_default_model() == 'anthropic/claude-sonnet-4'
    
    def test_custom_model(self):
        """Test custom model can be set."""
        provider = OpenRouterProvider(model='openai/gpt-4')
        assert provider.get_default_model() == 'openai/gpt-4'
    
    def test_generate_prompt(self):
        """Test prompt generation."""
        provider = OpenRouterProvider()
        prompt = provider.generate_prompt(
            task="Test task",
            context={
                "phase": "TEST",
                "items": [{"id": "item1", "description": "Test item"}],
                "constraints": ["Constraint 1"],
                "notes": ["Note 1"],
            }
        )
        assert "Test task" in prompt
        assert "TEST" in prompt
        assert "item1" in prompt
        assert "Constraint 1" in prompt
        assert "Note 1" in prompt
    
    def test_execute_without_api_key(self):
        """Test execute returns error without API key."""
        with patch.dict(os.environ, {}, clear=True):
            provider = OpenRouterProvider()
            result = provider.execute("test prompt")
            assert result.success is False
            assert "API key" in result.error


class TestClaudeCodeProvider:
    """Tests for the Claude Code provider."""
    
    def test_name(self):
        """Test provider name."""
        provider = ClaudeCodeProvider()
        assert provider.name() == 'claude_code'
    
    def test_is_available_checks_cli(self):
        """Test is_available checks for Claude CLI."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            provider = ClaudeCodeProvider()
            provider._claude_available = None  # Reset cache
            assert provider.is_available() is True
            mock_run.assert_called()
    
    def test_is_available_cli_not_found(self):
        """Test is_available returns False when CLI not found."""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            provider = ClaudeCodeProvider()
            provider._claude_available = None  # Reset cache
            assert provider.is_available() is False
    
    def test_generate_prompt(self):
        """Test prompt generation."""
        provider = ClaudeCodeProvider()
        prompt = provider.generate_prompt(
            task="Test task",
            context={
                "phase": "TEST",
                "items": [{"id": "item1", "name": "Test item", "status": "pending"}],
            }
        )
        assert "Test task" in prompt
        assert "TEST" in prompt
        assert "item1" in prompt
    
    def test_supports_execution(self):
        """Test that Claude Code supports execution."""
        provider = ClaudeCodeProvider()
        assert provider.supports_execution() is True


class TestManualProvider:
    """Tests for the Manual provider."""
    
    def test_name(self):
        """Test provider name."""
        provider = ManualProvider()
        assert provider.name() == 'manual'
    
    def test_is_always_available(self):
        """Test manual provider is always available."""
        provider = ManualProvider()
        assert provider.is_available() is True
    
    def test_does_not_support_execution(self):
        """Test manual provider does not support execution."""
        provider = ManualProvider()
        assert provider.supports_execution() is False
    
    def test_execute_raises_not_implemented(self):
        """Test execute raises NotImplementedError."""
        provider = ManualProvider()
        with pytest.raises(NotImplementedError):
            provider.execute("test prompt")
    
    def test_generate_prompt_includes_instructions(self):
        """Test prompt includes manual copy/paste instructions."""
        provider = ManualProvider()
        prompt = provider.generate_prompt(
            task="Test task",
            context={"phase": "TEST", "items": []}
        )
        assert "MANUAL HANDOFF" in prompt
        assert "Copy" in prompt
        assert "paste" in prompt.lower()
    
    def test_no_default_model(self):
        """Test manual provider has no default model."""
        provider = ManualProvider()
        assert provider.get_default_model() is None


class TestProviderRegistration:
    """Tests for custom provider registration."""
    
    def test_register_custom_provider(self):
        """Test registering a custom provider."""
        class CustomProvider(BaseAgentProvider):
            def name(self): return 'custom'
            def is_available(self): return True
            def generate_prompt(self, task, context): return f"Custom: {task}"
            def execute(self, prompt, model=None): return ExecutionResult(True, "done")
        
        register_provider('custom', CustomProvider)
        assert 'custom' in list_providers()
        
        provider = get_provider(name='custom')
        assert provider.name() == 'custom'
    
    def test_register_invalid_provider(self):
        """Test registering non-provider class raises TypeError."""
        class NotAProvider:
            pass
        
        with pytest.raises(TypeError):
            register_provider('invalid', NotAProvider)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

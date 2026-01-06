"""
Tests for the visual verification module.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from visual_verification import (
    VisualVerificationClient,
    VisualVerificationError,
    create_desktop_viewport,
    create_mobile_viewport,
    format_verification_result
)


class TestViewportCreation:
    """Tests for viewport creation functions."""
    
    def test_create_desktop_viewport(self):
        viewport = create_desktop_viewport()
        assert viewport == {"width": 1280, "height": 720}
    
    def test_create_mobile_viewport(self):
        viewport = create_mobile_viewport()
        assert viewport == {"width": 375, "height": 812}


class TestVisualVerificationClient:
    """Tests for VisualVerificationClient."""
    
    def test_init_with_params(self):
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        assert client.service_url == "https://test.com"
        assert client.api_key == "test-key"
    
    def test_init_with_env_vars(self):
        with patch.dict(os.environ, {
            'VISUAL_VERIFICATION_URL': 'https://env-test.com',
            'VISUAL_VERIFICATION_API_KEY': 'env-key'
        }):
            client = VisualVerificationClient()
            assert client.service_url == "https://env-test.com"
            assert client.api_key == "env-key"
    
    def test_init_missing_url_raises_error(self):
        with patch.dict(os.environ, {}, clear=True):
            # Clear any existing env vars
            os.environ.pop('VISUAL_VERIFICATION_URL', None)
            os.environ.pop('VISUAL_VERIFICATION_API_KEY', None)
            
            with pytest.raises(VisualVerificationError) as exc_info:
                VisualVerificationClient()
            assert "URL not configured" in str(exc_info.value)
    
    def test_init_missing_api_key_raises_error(self):
        with patch.dict(os.environ, {'VISUAL_VERIFICATION_URL': 'https://test.com'}, clear=True):
            os.environ.pop('VISUAL_VERIFICATION_API_KEY', None)
            
            with pytest.raises(VisualVerificationError) as exc_info:
                VisualVerificationClient()
            assert "API key not configured" in str(exc_info.value)
    
    def test_init_removes_trailing_slash(self):
        client = VisualVerificationClient(
            service_url="https://test.com/",
            api_key="test-key"
        )
        assert client.service_url == "https://test.com"
    
    @patch('visual_verification.requests.get')
    def test_health_check_success(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "healthy", "browserReady": True}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        result = client.health_check()
        
        assert result == {"status": "healthy", "browserReady": True}
        mock_get.assert_called_once_with(
            "https://test.com/health",
            headers={"X-API-Key": "test-key"},
            timeout=10
        )
    
    @patch('visual_verification.requests.get')
    def test_health_check_failure(self, mock_get):
        mock_get.side_effect = requests.RequestException("Connection failed")
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        
        with pytest.raises(VisualVerificationError) as exc_info:
            client.health_check()
        assert "Health check failed" in str(exc_info.value)
    
    @patch('visual_verification.requests.post')
    def test_verify_success(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "pass",
            "reasoning": "All checks passed",
            "screenshots": [],
            "issues": []
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        result = client.verify(
            url="https://example.com",
            specification="Test spec"
        )
        
        assert result["status"] == "pass"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"]["url"] == "https://example.com"
        assert call_args[1]["json"]["specification"] == "Test spec"
    
    @patch('visual_verification.requests.post')
    def test_verify_with_viewport(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "pass"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        client.verify(
            url="https://example.com",
            specification="Test spec",
            viewport={"width": 1280, "height": 720}
        )
        
        call_args = mock_post.call_args
        assert call_args[1]["json"]["viewport"] == {"width": 1280, "height": 720}
    
    @patch('visual_verification.requests.post')
    def test_verify_with_custom_actions(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "pass"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        actions = [
            {"type": "click", "selector": "#button"},
            {"type": "screenshot", "name": "after_click"}
        ]
        client.verify(
            url="https://example.com",
            specification="Test spec",
            actions=actions
        )
        
        call_args = mock_post.call_args
        assert call_args[1]["json"]["actions"] == actions
    
    @patch('visual_verification.requests.post')
    @patch('visual_verification.time.sleep')
    def test_verify_retries_on_failure(self, mock_sleep, mock_post):
        mock_post.side_effect = [
            requests.Timeout("Timeout"),
            requests.Timeout("Timeout"),
            Mock(
                json=Mock(return_value={"status": "pass"}),
                raise_for_status=Mock()
            )
        ]
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        result = client.verify(
            url="https://example.com",
            specification="Test spec",
            retries=3
        )
        
        assert result["status"] == "pass"
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2  # Backoff between retries
    
    @patch('visual_verification.requests.post')
    @patch('visual_verification.time.sleep')
    def test_verify_raises_after_all_retries_fail(self, mock_sleep, mock_post):
        mock_post.side_effect = requests.Timeout("Timeout")
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        
        with pytest.raises(VisualVerificationError) as exc_info:
            client.verify(
                url="https://example.com",
                specification="Test spec",
                retries=3
            )
        assert "failed after 3 attempts" in str(exc_info.value)
    
    @patch('visual_verification.requests.post')
    def test_verify_with_style_guide(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "pass"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        client.verify_with_style_guide(
            url="https://example.com",
            specification="Test spec",
            style_guide_content="# Style Guide\nUse blue buttons"
        )
        
        call_args = mock_post.call_args
        spec = call_args[1]["json"]["specification"]
        assert "Test spec" in spec
        assert "Style Guide Reference" in spec
        assert "Use blue buttons" in spec


class TestFormatVerificationResult:
    """Tests for format_verification_result function."""
    
    def test_format_pass_result(self):
        result = {
            "status": "pass",
            "reasoning": "All checks passed successfully"
        }
        formatted = format_verification_result(result, "desktop")
        
        assert "✓ DESKTOP: pass" in formatted
        assert "All checks passed" in formatted
    
    def test_format_fail_result(self):
        result = {
            "status": "fail",
            "reasoning": "Some checks failed"
        }
        formatted = format_verification_result(result, "mobile")
        
        assert "✗ MOBILE: fail" in formatted
        assert "Some checks failed" in formatted
    
    def test_format_result_with_issues(self):
        result = {
            "status": "fail",
            "reasoning": "Issues found",
            "issues": [
                {"severity": "high", "description": "Button not visible"},
                {"severity": "medium", "description": "Text too small"}
            ]
        }
        formatted = format_verification_result(result, "desktop")
        
        assert "[high] Button not visible" in formatted
        assert "[medium] Text too small" in formatted
    
    def test_format_result_truncates_long_reasoning(self):
        result = {
            "status": "pass",
            "reasoning": "A" * 500  # Very long reasoning
        }
        formatted = format_verification_result(result, "desktop")
        
        # Should truncate to ~300 chars + "..."
        assert "..." in formatted
        assert len(formatted) < 600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

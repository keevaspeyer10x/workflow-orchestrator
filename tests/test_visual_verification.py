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
    VerificationResult,
    UsageInfo,
    CostSummary,
    create_desktop_viewport,
    create_mobile_viewport,
    format_verification_result,
    format_cost_summary,
    discover_visual_tests,
    parse_visual_test_file,
)


class TestViewportCreation:
    """Tests for viewport creation functions."""

    def test_create_desktop_viewport(self):
        viewport = create_desktop_viewport()
        assert viewport == {"width": 1280, "height": 720}

    def test_create_mobile_viewport(self):
        viewport = create_mobile_viewport()
        # Updated to iPhone 14 dimensions (was iPhone 14 Pro: 375x812)
        assert viewport == {"width": 390, "height": 844}


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

    def test_init_without_api_key_ok(self):
        """API key is now optional (service may be unprotected)."""
        with patch.dict(os.environ, {'VISUAL_VERIFICATION_URL': 'https://test.com'}, clear=True):
            os.environ.pop('VISUAL_VERIFICATION_API_KEY', None)
            # Should not raise - API key is optional
            client = VisualVerificationClient()
            assert client.service_url == "https://test.com"
            assert client.api_key == ""

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
        mock_get.assert_called_once()

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
            "issues": [],
            "duration": 1000
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

        # Now returns VerificationResult instead of dict
        assert isinstance(result, VerificationResult)
        assert result.status == "pass"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"]["url"] == "https://example.com"
        assert call_args[1]["json"]["specification"] == "Test spec"

    @patch('visual_verification.requests.post')
    def test_verify_with_viewport(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "pass", "duration": 0}
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
    def test_verify_with_device(self, mock_post):
        """Test device preset support."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "pass", "duration": 0, "device": "iphone-14"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )
        result = client.verify(
            url="https://example.com",
            specification="Test spec",
            device="iphone-14"
        )

        call_args = mock_post.call_args
        assert call_args[1]["json"]["device"] == "iphone-14"
        assert result.device == "iphone-14"

    @patch('visual_verification.requests.post')
    def test_verify_with_custom_actions(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "pass", "duration": 0}
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
    def test_verify_failure_raises(self, mock_post):
        """verify() now raises on request failure."""
        mock_post.side_effect = requests.RequestException("Connection failed")

        client = VisualVerificationClient(
            service_url="https://test.com",
            api_key="test-key"
        )

        with pytest.raises(VisualVerificationError) as exc_info:
            client.verify(
                url="https://example.com",
                specification="Test spec"
            )
        assert "Verification request failed" in str(exc_info.value)

    @patch('visual_verification.requests.post')
    def test_verify_with_style_guide(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "pass", "duration": 0}
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

    @patch('visual_verification.requests.post')
    def test_verify_returns_usage_info(self, mock_post):
        """Test VV-006 cost tracking."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "pass",
            "reasoning": "OK",
            "screenshots": [],
            "issues": [],
            "duration": 1000,
            "usage": {
                "inputTokens": 1000,
                "outputTokens": 200,
                "estimatedCost": 0.005
            }
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

        assert result.usage is not None
        assert result.usage.input_tokens == 1000
        assert result.usage.output_tokens == 200
        assert result.usage.estimated_cost == 0.005


class TestFormatVerificationResult:
    """Tests for format_verification_result function."""

    def test_format_pass_result(self):
        result = VerificationResult(
            status="pass",
            reasoning="All checks passed successfully",
            screenshots=[],
            issues=[],
            duration=1000,
            device="desktop"
        )
        formatted = format_verification_result(result)

        assert "✓ DESKTOP: pass" in formatted
        assert "All checks passed" in formatted

    def test_format_fail_result(self):
        result = VerificationResult(
            status="fail",
            reasoning="Some checks failed",
            screenshots=[],
            issues=[],
            duration=1000,
            device="mobile"
        )
        formatted = format_verification_result(result)

        assert "✗ MOBILE: fail" in formatted
        assert "Some checks failed" in formatted

    def test_format_result_with_issues(self):
        result = VerificationResult(
            status="fail",
            reasoning="Issues found",
            screenshots=[],
            issues=[
                {"severity": "high", "description": "Button not visible"},
                {"severity": "medium", "description": "Text too small"}
            ],
            duration=1000,
            device="desktop"
        )
        formatted = format_verification_result(result)

        assert "[high] Button not visible" in formatted
        assert "[medium] Text too small" in formatted

    def test_format_result_truncates_long_reasoning(self):
        result = VerificationResult(
            status="pass",
            reasoning="A" * 500,  # Very long reasoning
            screenshots=[],
            issues=[],
            duration=1000,
            device="desktop"
        )
        formatted = format_verification_result(result)

        # Should truncate to ~300 chars + "..."
        assert "..." in formatted
        assert len(formatted) < 600

    def test_format_result_with_cost(self):
        """Test VV-006 cost display."""
        result = VerificationResult(
            status="pass",
            reasoning="OK",
            screenshots=[],
            issues=[],
            duration=1000,
            device="desktop",
            usage=UsageInfo(input_tokens=1000, output_tokens=200, estimated_cost=0.005)
        )
        formatted = format_verification_result(result, show_cost=True)

        assert "Cost: $0.005" in formatted
        assert "1000 in" in formatted


class TestCostSummary:
    """Tests for CostSummary class."""

    def test_add_usage(self):
        summary = CostSummary()
        summary.add(UsageInfo(input_tokens=100, output_tokens=50, estimated_cost=0.001))
        summary.add(UsageInfo(input_tokens=200, output_tokens=100, estimated_cost=0.002))

        assert summary.total_input_tokens == 300
        assert summary.total_output_tokens == 150
        assert summary.total_cost == 0.003
        assert summary.test_count == 2

    def test_add_none_usage(self):
        summary = CostSummary()
        summary.add(None)

        assert summary.total_input_tokens == 0
        assert summary.total_cost == 0.0
        assert summary.test_count == 1  # Still counts the test


class TestVisualTestDiscovery:
    """Tests for VV-003 visual test discovery."""

    def test_parse_visual_test_file(self):
        content = """---
url: /dashboard
device: iphone-14
tags: [core, dashboard]
---
# Dashboard Visual Test

The dashboard should display user information.
"""
        test_case = parse_visual_test_file(content, "test.md")

        assert test_case is not None
        assert test_case.url == "/dashboard"
        assert test_case.device == "iphone-14"
        assert "core" in test_case.tags
        assert "dashboard" in test_case.tags
        assert "Dashboard Visual Test" in test_case.specification

    def test_parse_visual_test_file_missing_frontmatter(self):
        content = "No frontmatter here"
        test_case = parse_visual_test_file(content, "test.md")
        assert test_case is None

    def test_parse_visual_test_file_missing_url(self):
        content = """---
device: desktop
---
Test content
"""
        test_case = parse_visual_test_file(content, "test.md")
        assert test_case is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

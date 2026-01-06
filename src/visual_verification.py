"""
Visual Verification Client

Communicates with the visual-verification-service for AI-powered UAT testing.
"""

import os
import requests
import time
from typing import List, Dict, Any, Optional


class VisualVerificationError(Exception):
    """Exception raised for visual verification errors."""
    pass


class VisualVerificationClient:
    """Client for the visual-verification-service API."""
    
    def __init__(self, service_url: str = None, api_key: str = None):
        """
        Initialize the visual verification client.
        
        Args:
            service_url: URL of the visual-verification-service (or set VISUAL_VERIFICATION_URL env var)
            api_key: API key for authentication (or set VISUAL_VERIFICATION_API_KEY env var)
        """
        self.service_url = service_url or os.environ.get('VISUAL_VERIFICATION_URL', '')
        self.api_key = api_key or os.environ.get('VISUAL_VERIFICATION_API_KEY', '')
        
        # Remove trailing slash from URL
        self.service_url = self.service_url.rstrip('/')
        
        if not self.service_url:
            raise VisualVerificationError(
                "Visual verification service URL not configured. "
                "Set VISUAL_VERIFICATION_URL environment variable or pass service_url parameter."
            )
        if not self.api_key:
            raise VisualVerificationError(
                "Visual verification API key not configured. "
                "Set VISUAL_VERIFICATION_API_KEY environment variable or pass api_key parameter."
            )
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check if the visual verification service is healthy.
        
        Returns:
            Health status dict with status, browserReady, etc.
        
        Raises:
            VisualVerificationError: If health check fails
        """
        try:
            response = requests.get(
                f"{self.service_url}/health",
                headers={"X-API-Key": self.api_key},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise VisualVerificationError(f"Health check failed: {e}")
    
    def verify(
        self,
        url: str,
        specification: str,
        actions: List[Dict[str, Any]] = None,
        viewport: Dict[str, int] = None,
        timeout: int = 60000,
        retries: int = 3
    ) -> Dict[str, Any]:
        """
        Run visual verification against a URL.
        
        Args:
            url: The URL to verify
            specification: Natural language specification to evaluate against
            actions: List of actions to perform (click, type, screenshot, etc.)
            viewport: Viewport dimensions {width, height}
            timeout: Request timeout in ms
            retries: Number of retry attempts
        
        Returns:
            Verification result with:
            - status: 'pass', 'fail', or 'error'
            - reasoning: Explanation of the evaluation
            - screenshots: List of captured screenshots (base64)
            - issues: List of identified issues
            - duration: Time taken in ms
        
        Raises:
            VisualVerificationError: If verification fails after all retries
        """
        if actions is None:
            actions = [{"type": "screenshot", "name": "initial"}]
        
        payload = {
            "url": url,
            "specification": specification,
            "actions": actions,
            "timeout": timeout
        }
        
        if viewport:
            payload["viewport"] = viewport
        
        last_error = None
        for attempt in range(retries):
            try:
                response = requests.post(
                    f"{self.service_url}/verify",
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=(timeout / 1000) + 30  # Add buffer for network latency
                )
                response.raise_for_status()
                return response.json()
            except requests.Timeout as e:
                last_error = e
                if attempt < retries - 1:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
            except requests.RequestException as e:
                last_error = e
                if attempt < retries - 1:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
        
        raise VisualVerificationError(
            f"Verification failed after {retries} attempts: {last_error}"
        )
    
    def verify_with_style_guide(
        self,
        url: str,
        specification: str,
        style_guide_content: str,
        actions: List[Dict[str, Any]] = None,
        viewport: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """
        Run verification with style guide context included in specification.
        
        Args:
            url: The URL to verify
            specification: Natural language specification to evaluate against
            style_guide_content: Content of the style guide to include
            actions: List of actions to perform
            viewport: Viewport dimensions
        
        Returns:
            Verification result (same as verify())
        """
        enhanced_spec = f"""{specification}

## Style Guide Reference

Please also evaluate the UI against the following style guide:

{style_guide_content}

Ensure the implementation is consistent with both the specific requirements above and the style guide.
"""
        return self.verify(url, enhanced_spec, actions, viewport)


def create_desktop_viewport() -> Dict[str, int]:
    """Create standard desktop viewport dimensions."""
    return {"width": 1280, "height": 720}


def create_mobile_viewport() -> Dict[str, int]:
    """Create standard mobile viewport dimensions (iPhone 14 Pro)."""
    return {"width": 375, "height": 812}


def format_verification_result(result: Dict[str, Any], viewport: str = "unknown") -> str:
    """
    Format a verification result for display.
    
    Args:
        result: Verification result dict
        viewport: Viewport name (desktop/mobile)
    
    Returns:
        Formatted string for display
    """
    status = result.get('status', 'unknown')
    icon = '✓' if status == 'pass' else '✗'
    
    lines = [
        f"{icon} {viewport.upper()}: {status}",
        f"  Reasoning: {result.get('reasoning', 'N/A')[:300]}..."
    ]
    
    issues = result.get('issues', [])
    if issues:
        lines.append("  Issues:")
        for issue in issues:
            severity = issue.get('severity', 'unknown')
            description = issue.get('description', 'No description')
            lines.append(f"    - [{severity}] {description}")
    
    return '\n'.join(lines)

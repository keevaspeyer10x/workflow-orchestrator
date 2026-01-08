"""
Visual Verification Client

Communicates with the visual-verification-service for AI-powered UAT testing.
Implements VV-001 through VV-004 and VV-006 from the roadmap.
"""

import os
import json
import hashlib
import base64
import logging
import time
import glob as glob_module
from pathlib import Path
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass, field

try:
    import requests
except ImportError:
    requests = None

try:
    import yaml
except ImportError:
    yaml = None


logger = logging.getLogger(__name__)


class VisualVerificationError(Exception):
    """Exception raised for visual verification errors."""
    pass


# Device presets (must match visual-verification-service)
DEVICE_PRESETS = {
    'iphone-14': {'width': 390, 'height': 844},
    'iphone-14-pro-max': {'width': 430, 'height': 932},
    'iphone-se': {'width': 375, 'height': 667},
    'pixel-7': {'width': 412, 'height': 915},
    'pixel-7-pro': {'width': 412, 'height': 892},
    'samsung-galaxy-s23': {'width': 360, 'height': 780},
    'ipad': {'width': 768, 'height': 1024},
    'ipad-pro': {'width': 1024, 'height': 1366},
    'desktop': {'width': 1280, 'height': 720},
    'desktop-hd': {'width': 1920, 'height': 1080},
}


@dataclass
class UsageInfo:
    """Token usage and cost information."""
    input_tokens: int
    output_tokens: int
    estimated_cost: float  # USD


@dataclass
class VerificationResult:
    """Result of a visual verification test."""
    status: str  # 'pass', 'fail', 'error'
    reasoning: str
    screenshots: List[Dict[str, Any]]
    issues: List[Dict[str, Any]]
    duration: int  # milliseconds
    device: Optional[str] = None
    viewport: Optional[Dict[str, int]] = None
    usage: Optional[UsageInfo] = None


@dataclass
class VisualTestCase:
    """A visual test case parsed from a test file."""
    name: str
    url: str
    specification: str
    device: Optional[str] = None
    viewport: Optional[Dict[str, int]] = None
    actions: List[Dict[str, Any]] = field(default_factory=lambda: [{"type": "screenshot", "name": "initial"}])
    tags: List[str] = field(default_factory=list)
    file_path: Optional[str] = None


@dataclass
class CostSummary:
    """Aggregated cost information for multiple tests."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    test_count: int = 0

    def add(self, usage: Optional[UsageInfo]) -> None:
        """Add usage from a single test."""
        if usage:
            self.total_input_tokens += usage.input_tokens
            self.total_output_tokens += usage.output_tokens
            self.total_cost += usage.estimated_cost
        self.test_count += 1


class VisualVerificationClient:
    """Client for the visual-verification-service API."""

    def __init__(
        self,
        service_url: str = None,
        api_key: str = None,
        style_guide_path: str = None,
        baselines_dir: str = None,
        auto_include_style_guide: bool = True
    ):
        """
        Initialize the visual verification client.

        Args:
            service_url: URL of the visual-verification-service (or set VISUAL_VERIFICATION_URL env var)
            api_key: API key for authentication (or set VISUAL_VERIFICATION_API_KEY env var)
            style_guide_path: Path to style guide file for VV-001 auto-loading
            baselines_dir: Directory for baseline screenshots (default: tests/visual/baselines)
            auto_include_style_guide: Whether to auto-include style guide in verifications (VV-001)
        """
        if requests is None:
            raise VisualVerificationError("requests library not installed. Run: pip install requests")

        self.service_url = service_url or os.environ.get('VISUAL_VERIFICATION_URL', '')
        self.api_key = api_key or os.environ.get('VISUAL_VERIFICATION_API_KEY', '')
        self.style_guide_path = style_guide_path
        self.baselines_dir = Path(baselines_dir or 'tests/visual/baselines')
        self.auto_include_style_guide = auto_include_style_guide
        self._style_guide_content: Optional[str] = None
        self._device_presets: Optional[Dict[str, Any]] = None

        # Remove trailing slash from URL
        self.service_url = self.service_url.rstrip('/')

        if not self.service_url:
            raise VisualVerificationError(
                "Visual verification service URL not configured. "
                "Set VISUAL_VERIFICATION_URL environment variable or pass service_url parameter."
            )

        # VV-001: Auto-load style guide
        if self.style_guide_path and self.auto_include_style_guide:
            self._load_style_guide()

    def _load_style_guide(self) -> None:
        """Load style guide content from file (VV-001)."""
        try:
            path = Path(self.style_guide_path)
            if path.exists():
                self._style_guide_content = path.read_text()
                logger.info(f"Loaded style guide from {path}")
            else:
                logger.warning(f"Style guide not found at {path}")
        except Exception as e:
            logger.warning(f"Failed to load style guide: {e}")

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _enhance_specification(self, specification: str) -> str:
        """Enhance specification with style guide if enabled (VV-001)."""
        if self._style_guide_content and self.auto_include_style_guide:
            return f"""{specification}

## Style Guide Reference

Please also evaluate the UI against the following style guide:

{self._style_guide_content}

Ensure the implementation is consistent with both the specific requirements above and the style guide.
"""
        return specification

    def health_check(self) -> Dict[str, Any]:
        """
        Check if the visual verification service is healthy.

        Returns:
            Health status dict with status, browserReady, etc.
        """
        try:
            response = requests.get(
                f"{self.service_url}/health",
                headers=self._get_auth_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise VisualVerificationError(f"Health check failed: {e}")

    def get_devices(self) -> Dict[str, Any]:
        """
        Get available device presets from the service.

        Returns:
            Dict with 'presets' list and 'details' dict
        """
        try:
            response = requests.get(
                f"{self.service_url}/devices",
                headers=self._get_auth_headers(),
                timeout=10
            )
            response.raise_for_status()
            self._device_presets = response.json()
            return self._device_presets
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch device presets: {e}")
            # Return local presets as fallback
            return {
                "presets": list(DEVICE_PRESETS.keys()),
                "details": DEVICE_PRESETS
            }

    def verify(
        self,
        url: str,
        specification: str,
        actions: List[Dict[str, Any]] = None,
        device: str = None,
        viewport: Dict[str, int] = None,
        auth: Dict[str, Any] = None,
        timeout: int = 60000,
        retries: int = 3,
        include_style_guide: bool = None
    ) -> VerificationResult:
        """
        Run visual verification against a URL.

        Args:
            url: The URL to verify
            specification: Natural language specification to evaluate against
            actions: List of actions to perform (click, type, screenshot, etc.)
            device: Device preset name (e.g., 'iphone-14', 'desktop')
            viewport: Custom viewport dimensions {width, height} (overrides device)
            auth: Authentication config {cookies, localStorage, headers}
            timeout: Request timeout in ms
            retries: Number of retry attempts (handled by service)
            include_style_guide: Override auto_include_style_guide for this request

        Returns:
            VerificationResult with status, reasoning, screenshots, issues, usage
        """
        if actions is None:
            actions = [{"type": "screenshot", "name": "initial"}]

        # VV-001: Auto-enhance with style guide
        should_include_style_guide = include_style_guide if include_style_guide is not None else self.auto_include_style_guide
        if should_include_style_guide:
            specification = self._enhance_specification(specification)

        payload = {
            "url": url,
            "specification": specification,
            "actions": actions,
            "timeout": timeout,
            "retries": retries
        }

        if device:
            payload["device"] = device
        if viewport:
            payload["viewport"] = viewport
        if auth:
            payload["auth"] = auth

        try:
            response = requests.post(
                f"{self.service_url}/verify",
                headers=self._get_auth_headers(),
                json=payload,
                timeout=(timeout / 1000) + 60  # Add buffer for retries
            )
            response.raise_for_status()
            data = response.json()

            # Parse usage if present (VV-006)
            usage = None
            if 'usage' in data and data['usage']:
                usage = UsageInfo(
                    input_tokens=data['usage'].get('inputTokens', 0),
                    output_tokens=data['usage'].get('outputTokens', 0),
                    estimated_cost=data['usage'].get('estimatedCost', 0.0)
                )

            return VerificationResult(
                status=data.get('status', 'error'),
                reasoning=data.get('reasoning', 'No reasoning provided'),
                screenshots=data.get('screenshots', []),
                issues=data.get('issues', []),
                duration=data.get('duration', 0),
                device=data.get('device'),
                viewport=data.get('viewport'),
                usage=usage
            )
        except requests.RequestException as e:
            raise VisualVerificationError(f"Verification request failed: {e}")

    def verify_with_style_guide(
        self,
        url: str,
        specification: str,
        style_guide_content: str,
        actions: List[Dict[str, Any]] = None,
        device: str = None,
        viewport: Dict[str, int] = None
    ) -> VerificationResult:
        """
        Run verification with explicit style guide content (legacy method).

        For new code, prefer setting style_guide_path in constructor with auto_include_style_guide=True.
        """
        enhanced_spec = f"""{specification}

## Style Guide Reference

Please also evaluate the UI against the following style guide:

{style_guide_content}

Ensure the implementation is consistent with both the specific requirements above and the style guide.
"""
        return self.verify(url, enhanced_spec, actions, device, viewport, include_style_guide=False)

    # VV-004: Baseline Management

    def save_baseline(self, name: str, screenshot_data: str) -> Path:
        """
        Save a screenshot as a baseline (VV-004).

        Args:
            name: Baseline name (will be sanitized for filesystem)
            screenshot_data: Base64-encoded screenshot data

        Returns:
            Path to saved baseline file
        """
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize name
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in name)
        baseline_path = self.baselines_dir / f"{safe_name}.png"

        # Decode and save
        image_data = base64.b64decode(screenshot_data)
        baseline_path.write_bytes(image_data)

        # Also save a hash for quick comparison
        hash_path = self.baselines_dir / f"{safe_name}.hash"
        content_hash = hashlib.sha256(image_data).hexdigest()
        hash_path.write_text(content_hash)

        logger.info(f"Saved baseline: {baseline_path}")
        return baseline_path

    def get_baseline(self, name: str) -> Optional[bytes]:
        """
        Get a baseline screenshot (VV-004).

        Args:
            name: Baseline name

        Returns:
            Raw image bytes, or None if baseline doesn't exist
        """
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in name)
        baseline_path = self.baselines_dir / f"{safe_name}.png"

        if baseline_path.exists():
            return baseline_path.read_bytes()
        return None

    def compare_with_baseline(self, name: str, screenshot_data: str) -> Dict[str, Any]:
        """
        Compare a screenshot with its baseline (VV-004).

        Args:
            name: Baseline name
            screenshot_data: Base64-encoded screenshot to compare

        Returns:
            Dict with 'match' bool, 'baseline_exists' bool, and optional 'hash_match'
        """
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in name)
        baseline_path = self.baselines_dir / f"{safe_name}.png"
        hash_path = self.baselines_dir / f"{safe_name}.hash"

        if not baseline_path.exists():
            return {'match': False, 'baseline_exists': False}

        # Compare hashes first (fast path)
        current_data = base64.b64decode(screenshot_data)
        current_hash = hashlib.sha256(current_data).hexdigest()

        if hash_path.exists():
            baseline_hash = hash_path.read_text().strip()
            hash_match = current_hash == baseline_hash
            return {
                'match': hash_match,
                'baseline_exists': True,
                'hash_match': hash_match,
                'current_hash': current_hash,
                'baseline_hash': baseline_hash
            }

        # Fall back to byte comparison
        baseline_data = baseline_path.read_bytes()
        byte_match = current_data == baseline_data
        return {
            'match': byte_match,
            'baseline_exists': True,
            'byte_match': byte_match
        }

    def list_baselines(self) -> List[str]:
        """List all available baselines (VV-004)."""
        if not self.baselines_dir.exists():
            return []
        return [p.stem for p in self.baselines_dir.glob("*.png")]


# VV-003: Visual Test Discovery

def discover_visual_tests(tests_dir: str = "tests/visual") -> List[VisualTestCase]:
    """
    Discover visual test files in a directory (VV-003).

    Test files are markdown files with YAML frontmatter:

    ```
    ---
    url: /dashboard
    device: iphone-14
    tags: [core, dashboard]
    ---
    # Dashboard Visual Test

    The dashboard should display:
    - User greeting in top-left
    - Navigation sidebar
    ```

    Args:
        tests_dir: Directory to scan for test files

    Returns:
        List of VisualTestCase objects
    """
    if yaml is None:
        logger.warning("PyYAML not installed. Cannot discover visual tests.")
        return []

    tests_path = Path(tests_dir)
    if not tests_path.exists():
        logger.info(f"Visual tests directory does not exist: {tests_path}")
        return []

    test_cases = []

    for test_file in tests_path.glob("*.md"):
        try:
            content = test_file.read_text()
            test_case = parse_visual_test_file(content, str(test_file))
            if test_case:
                test_cases.append(test_case)
        except Exception as e:
            logger.warning(f"Failed to parse test file {test_file}: {e}")

    return test_cases


def parse_visual_test_file(content: str, file_path: str = None) -> Optional[VisualTestCase]:
    """
    Parse a visual test file with YAML frontmatter (VV-003).

    Args:
        content: File content
        file_path: Path to the file (for error messages)

    Returns:
        VisualTestCase or None if parsing fails
    """
    if yaml is None:
        return None

    # Check for frontmatter
    if not content.startswith('---'):
        logger.warning(f"Test file missing YAML frontmatter: {file_path}")
        return None

    # Split frontmatter and body
    parts = content.split('---', 2)
    if len(parts) < 3:
        logger.warning(f"Invalid frontmatter format: {file_path}")
        return None

    try:
        frontmatter = yaml.safe_load(parts[1])
        specification = parts[2].strip()
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse YAML frontmatter in {file_path}: {e}")
        return None

    if not frontmatter or 'url' not in frontmatter:
        logger.warning(f"Test file missing required 'url' field: {file_path}")
        return None

    # Extract name from filename or frontmatter
    name = frontmatter.get('name')
    if not name and file_path:
        name = Path(file_path).stem

    return VisualTestCase(
        name=name or 'unnamed',
        url=frontmatter['url'],
        specification=specification,
        device=frontmatter.get('device'),
        viewport=frontmatter.get('viewport'),
        actions=frontmatter.get('actions', [{"type": "screenshot", "name": "initial"}]),
        tags=frontmatter.get('tags', []),
        file_path=file_path
    )


def filter_tests_by_tag(tests: List[VisualTestCase], tag: str) -> List[VisualTestCase]:
    """Filter visual tests by tag (VV-003)."""
    return [t for t in tests if tag in t.tags]


def run_all_visual_tests(
    client: VisualVerificationClient,
    tests_dir: str = "tests/visual",
    app_url: str = None,
    tags: List[str] = None,
    save_baselines: bool = False
) -> Dict[str, Any]:
    """
    Run all discovered visual tests (VV-002, VV-003).

    Args:
        client: VisualVerificationClient instance
        tests_dir: Directory containing test files
        app_url: Base URL to prepend to relative URLs
        tags: Filter tests by these tags (run all if None)
        save_baselines: Save screenshots as baselines

    Returns:
        Dict with 'results', 'summary', and 'cost_summary'
    """
    tests = discover_visual_tests(tests_dir)

    if tags:
        for tag in tags:
            tests = filter_tests_by_tag(tests, tag)

    if not tests:
        return {
            'results': [],
            'summary': {'total': 0, 'passed': 0, 'failed': 0, 'errors': 0},
            'cost_summary': CostSummary()
        }

    results = []
    cost_summary = CostSummary()
    passed = 0
    failed = 0
    errors = 0

    for test in tests:
        # Resolve URL
        url = test.url
        if app_url and not url.startswith(('http://', 'https://')):
            url = app_url.rstrip('/') + '/' + url.lstrip('/')

        try:
            result = client.verify(
                url=url,
                specification=test.specification,
                actions=test.actions,
                device=test.device,
                viewport=test.viewport
            )

            # Track costs (VV-006)
            cost_summary.add(result.usage)

            # Save baseline if requested (VV-004)
            if save_baselines and result.screenshots:
                for screenshot in result.screenshots:
                    baseline_name = f"{test.name}_{screenshot.get('name', 'screenshot')}"
                    client.save_baseline(baseline_name, screenshot.get('base64', ''))

            # Count results
            if result.status == 'pass':
                passed += 1
            elif result.status == 'fail':
                failed += 1
            else:
                errors += 1

            results.append({
                'test': test.name,
                'file': test.file_path,
                'result': result
            })

        except Exception as e:
            errors += 1
            results.append({
                'test': test.name,
                'file': test.file_path,
                'error': str(e)
            })

    return {
        'results': results,
        'summary': {
            'total': len(tests),
            'passed': passed,
            'failed': failed,
            'errors': errors
        },
        'cost_summary': cost_summary
    }


# Helper functions

def create_desktop_viewport() -> Dict[str, int]:
    """Create standard desktop viewport dimensions."""
    return {"width": 1280, "height": 720}


def create_mobile_viewport() -> Dict[str, int]:
    """Create standard mobile viewport dimensions (iPhone 14)."""
    return {"width": 390, "height": 844}


def format_verification_result(result: VerificationResult, show_cost: bool = False) -> str:
    """
    Format a verification result for display.

    Args:
        result: VerificationResult object
        show_cost: Include cost information (VV-006)

    Returns:
        Formatted string for display
    """
    status = result.status
    icon = '✓' if status == 'pass' else '✗'
    device_info = result.device or (f"{result.viewport['width']}x{result.viewport['height']}" if result.viewport else "unknown")

    lines = [
        f"{icon} {device_info.upper()}: {status}",
        f"  Reasoning: {result.reasoning[:300]}{'...' if len(result.reasoning) > 300 else ''}"
    ]

    if result.issues:
        lines.append("  Issues:")
        for issue in result.issues:
            severity = issue.get('severity', 'unknown')
            description = issue.get('description', 'No description')
            lines.append(f"    - [{severity}] {description}")

    # VV-006: Show cost
    if show_cost and result.usage:
        lines.append(f"  Cost: ${result.usage.estimated_cost:.6f} ({result.usage.input_tokens} in / {result.usage.output_tokens} out)")

    return '\n'.join(lines)


def format_cost_summary(summary: CostSummary) -> str:
    """Format cost summary for display (VV-006)."""
    return f"""
Cost Summary:
  Tests run: {summary.test_count}
  Total tokens: {summary.total_input_tokens:,} input / {summary.total_output_tokens:,} output
  Estimated cost: ${summary.total_cost:.4f} USD
"""

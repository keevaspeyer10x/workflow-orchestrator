# Claude Code Implementation Task: Visual Verification Integration

## Context
Add visual verification integration to the workflow-orchestrator to enable AI-powered UAT testing using the visual-verification-service.

## Service Details
- **Service URL:** https://visual-verification-service.onrender.com
- **API Key:** Set via environment variable `VISUAL_VERIFICATION_API_KEY`
- **Health endpoint:** GET /health
- **Verify endpoint:** POST /verify

## Files to Create/Modify

### 1. Create `src/visual_verification.py`

Create a client module to communicate with the visual-verification-service:

```python
import os
import requests
import time
from typing import List, Dict, Any, Optional

class VisualVerificationError(Exception):
    pass

class VisualVerificationClient:
    def __init__(self, service_url: str = None, api_key: str = None):
        self.service_url = service_url or os.environ.get('VISUAL_VERIFICATION_URL')
        self.api_key = api_key or os.environ.get('VISUAL_VERIFICATION_API_KEY')
        
        if not self.service_url:
            raise VisualVerificationError("VISUAL_VERIFICATION_URL not set")
        if not self.api_key:
            raise VisualVerificationError("VISUAL_VERIFICATION_API_KEY not set")
    
    def health_check(self) -> Dict[str, Any]:
        """Check if the service is healthy."""
        response = requests.get(
            f"{self.service_url}/health",
            headers={"X-API-Key": self.api_key},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    
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
            Verification result with status, reasoning, screenshots, issues
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
                    timeout=timeout / 1000 + 30  # Add buffer for network
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
        
        raise VisualVerificationError(f"Verification failed after {retries} attempts: {last_error}")
    
    def verify_with_style_guide(
        self,
        url: str,
        specification: str,
        style_guide_content: str,
        actions: List[Dict[str, Any]] = None,
        viewport: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """Run verification with style guide context included in specification."""
        enhanced_spec = f"""
{specification}

## Style Guide Reference
{style_guide_content}

Please evaluate the UI against both the specific requirements above and the style guide.
"""
        return self.verify(url, enhanced_spec, actions, viewport)


def create_desktop_viewport() -> Dict[str, int]:
    return {"width": 1280, "height": 720}

def create_mobile_viewport() -> Dict[str, int]:
    return {"width": 375, "height": 812}
```

### 2. Update `src/cli.py`

Add visual verification commands:

```python
# Add to imports
from visual_verification import VisualVerificationClient, VisualVerificationError, create_desktop_viewport, create_mobile_viewport

# Add these commands to the CLI

@cli.command()
@click.option('--url', required=True, help='URL to verify')
@click.option('--spec', required=True, help='Path to specification file or inline spec')
@click.option('--mobile/--no-mobile', default=True, help='Include mobile viewport test')
@click.option('--style-guide', help='Path to style guide file')
def visual_verify(url: str, spec: str, mobile: bool, style_guide: str):
    """Run visual verification against a URL."""
    try:
        client = VisualVerificationClient()
        
        # Load specification
        if os.path.exists(spec):
            with open(spec, 'r') as f:
                specification = f.read()
        else:
            specification = spec
        
        # Load style guide if provided
        style_guide_content = None
        if style_guide and os.path.exists(style_guide):
            with open(style_guide, 'r') as f:
                style_guide_content = f.read()
        
        results = []
        
        # Desktop verification
        click.echo("Running desktop verification...")
        if style_guide_content:
            desktop_result = client.verify_with_style_guide(
                url, specification, style_guide_content,
                viewport=create_desktop_viewport()
            )
        else:
            desktop_result = client.verify(
                url, specification,
                viewport=create_desktop_viewport()
            )
        desktop_result['viewport'] = 'desktop'
        results.append(desktop_result)
        
        # Mobile verification
        if mobile:
            click.echo("Running mobile verification...")
            if style_guide_content:
                mobile_result = client.verify_with_style_guide(
                    url, specification, style_guide_content,
                    viewport=create_mobile_viewport()
                )
            else:
                mobile_result = client.verify(
                    url, specification,
                    viewport=create_mobile_viewport()
                )
            mobile_result['viewport'] = 'mobile'
            results.append(mobile_result)
        
        # Output results
        all_passed = all(r['status'] == 'pass' for r in results)
        
        for result in results:
            viewport = result.get('viewport', 'unknown')
            status = result['status']
            icon = '✓' if status == 'pass' else '✗'
            click.echo(f"\n{icon} {viewport.upper()}: {status}")
            click.echo(f"  Reasoning: {result.get('reasoning', 'N/A')[:200]}...")
            if result.get('issues'):
                click.echo("  Issues:")
                for issue in result['issues']:
                    click.echo(f"    - [{issue['severity']}] {issue['description']}")
        
        click.echo(f"\n{'✓ ALL PASSED' if all_passed else '✗ SOME FAILED'}")
        return 0 if all_passed else 1
        
    except VisualVerificationError as e:
        click.echo(f"Error: {e}", err=True)
        return 1

@cli.command()
@click.argument('feature_name')
def visual_template(feature_name: str):
    """Generate a visual test template for a feature."""
    template = f'''# Visual UAT Test: {feature_name}

## Test URL
{{{{base_url}}}}/path/to/feature

## Pre-conditions
- User is logged in
- [Other setup requirements]

## Actions to Perform
1. Navigate to the page
2. [Action 2]
3. [Action 3]

## Specific Checks
- [ ] [Specific element] is visible
- [ ] [Specific functionality] works
- [ ] [Expected state] is achieved

## Open-Ended Evaluation (Mandatory)
1. Does this feature work as specified? Can the user complete the intended action?
2. Is the design consistent with our style guide?
3. Is the user journey intuitive? Would a first-time user understand what to do?
4. How does it handle edge cases (errors, empty states, unexpected input)?
5. Does it work well on mobile? Are there any responsive design issues?

## Open-Ended Evaluation (Optional)
- [ ] Accessibility: Are there any obvious accessibility concerns?
- [ ] Visual hierarchy: Does the layout guide the user appropriately?
- [ ] Performance: Do loading states feel responsive?
'''
    click.echo(template)
```

### 3. Update `src/engine.py`

Add visual verification handling to the engine:

```python
# Add to imports
from visual_verification import VisualVerificationClient, VisualVerificationError, create_desktop_viewport, create_mobile_viewport

# Add method to WorkflowEngine class
def run_visual_verification(self) -> dict:
    """Run visual verification tests from tests/visual/ directory."""
    settings = self.workflow.get('settings', {})
    
    # Get configuration from settings
    service_url = self._substitute_env_vars(settings.get('visual_verification_url', ''))
    api_key = self._substitute_env_vars(settings.get('visual_verification_api_key', ''))
    style_guide_path = settings.get('style_guide_path', '')
    mobile_enabled = settings.get('mobile_check_enabled', True)
    test_mode = settings.get('visual_test_mode', 'quick')
    
    if not service_url or not api_key:
        return {
            'status': 'skipped',
            'reason': 'Visual verification not configured (missing URL or API key)'
        }
    
    # Initialize client
    try:
        client = VisualVerificationClient(service_url, api_key)
        health = client.health_check()
        if not health.get('browserReady'):
            return {'status': 'error', 'reason': 'Visual verification service browser not ready'}
    except Exception as e:
        return {'status': 'error', 'reason': f'Could not connect to visual verification service: {e}'}
    
    # Load style guide
    style_guide_content = None
    if style_guide_path and os.path.exists(style_guide_path):
        with open(style_guide_path, 'r') as f:
            style_guide_content = f.read()
    
    # Find visual test files
    visual_tests_dir = 'tests/visual'
    if not os.path.exists(visual_tests_dir):
        return {'status': 'skipped', 'reason': 'No tests/visual directory found'}
    
    test_files = [f for f in os.listdir(visual_tests_dir) if f.endswith('.md')]
    if not test_files:
        return {'status': 'skipped', 'reason': 'No visual test files found'}
    
    results = []
    for test_file in test_files:
        test_path = os.path.join(visual_tests_dir, test_file)
        with open(test_path, 'r') as f:
            spec_content = f.read()
        
        # Parse test file to extract URL and actions
        url, actions = self._parse_visual_test(spec_content)
        if not url:
            results.append({
                'file': test_file,
                'status': 'error',
                'reason': 'Could not parse test URL from file'
            })
            continue
        
        # Run desktop verification
        try:
            if style_guide_content:
                desktop_result = client.verify_with_style_guide(
                    url, spec_content, style_guide_content,
                    actions=actions,
                    viewport=create_desktop_viewport()
                )
            else:
                desktop_result = client.verify(
                    url, spec_content,
                    actions=actions,
                    viewport=create_desktop_viewport()
                )
            
            results.append({
                'file': test_file,
                'viewport': 'desktop',
                'status': desktop_result['status'],
                'reasoning': desktop_result.get('reasoning', ''),
                'issues': desktop_result.get('issues', [])
            })
        except Exception as e:
            results.append({
                'file': test_file,
                'viewport': 'desktop',
                'status': 'error',
                'reason': str(e)
            })
        
        # Run mobile verification if enabled
        if mobile_enabled:
            try:
                if style_guide_content:
                    mobile_result = client.verify_with_style_guide(
                        url, spec_content, style_guide_content,
                        actions=actions,
                        viewport=create_mobile_viewport()
                    )
                else:
                    mobile_result = client.verify(
                        url, spec_content,
                        actions=actions,
                        viewport=create_mobile_viewport()
                    )
                
                results.append({
                    'file': test_file,
                    'viewport': 'mobile',
                    'status': mobile_result['status'],
                    'reasoning': mobile_result.get('reasoning', ''),
                    'issues': mobile_result.get('issues', [])
                })
            except Exception as e:
                results.append({
                    'file': test_file,
                    'viewport': 'mobile',
                    'status': 'error',
                    'reason': str(e)
                })
    
    # Aggregate results
    all_passed = all(r['status'] == 'pass' for r in results)
    
    return {
        'status': 'pass' if all_passed else 'fail',
        'results': results,
        'summary': {
            'total': len(results),
            'passed': sum(1 for r in results if r['status'] == 'pass'),
            'failed': sum(1 for r in results if r['status'] == 'fail'),
            'errors': sum(1 for r in results if r['status'] == 'error')
        }
    }

def _parse_visual_test(self, content: str) -> tuple:
    """Parse a visual test file to extract URL and actions."""
    import re
    
    # Extract URL from ## Test URL section
    url_match = re.search(r'## Test URL\s*\n\s*(\S+)', content)
    url = url_match.group(1) if url_match else None
    
    # Default actions - just take a screenshot
    actions = [{"type": "screenshot", "name": "verification"}]
    
    # Could parse ## Actions section for more complex tests
    
    return url, actions
```

### 4. Update `examples/development_workflow.yaml`

Add visual verification settings:

```yaml
settings:
  # ... existing settings ...
  
  # Visual verification settings
  visual_verification_url: "${VISUAL_VERIFICATION_URL}"
  visual_verification_api_key: "${VISUAL_VERIFICATION_API_KEY}"
  style_guide_path: "docs/UI_DESIGN_BRIEF.md"
  mobile_check_enabled: true
  visual_test_mode: "quick"  # "quick" or "full"
```

### 5. Create `templates/visual_test_template.md`

```markdown
# Visual UAT Test: {{feature_name}}

## Test URL
{{base_url}}/path/to/feature

## Pre-conditions
- User is logged in
- [Other setup requirements]

## Actions to Perform
1. Navigate to the page
2. [Action 2]
3. [Action 3]

## Specific Checks
- [ ] [Specific element] is visible
- [ ] [Specific functionality] works
- [ ] [Expected state] is achieved

## Open-Ended Evaluation (Mandatory)
1. Does this feature work as specified? Can the user complete the intended action?
2. Is the design consistent with our style guide?
3. Is the user journey intuitive? Would a first-time user understand what to do?
4. How does it handle edge cases (errors, empty states, unexpected input)?
5. Does it work well on mobile? Are there any responsive design issues?

## Open-Ended Evaluation (Optional)
- [ ] Accessibility: Are there any obvious accessibility concerns?
- [ ] Visual hierarchy: Does the layout guide the user appropriately?
- [ ] Performance: Do loading states feel responsive?
```

### 6. Create `docs/VISUAL_VERIFICATION.md`

Documentation for setting up and using visual verification.

## Success Criteria
1. `./orchestrator visual-verify --url "..." --spec "..."` works
2. `./orchestrator visual-template "Feature"` outputs template
3. Visual verification runs during `visual_regression_test` workflow step
4. Both desktop and mobile viewports are tested
5. Style guide is included in evaluation when configured
6. Clear pass/fail output with reasoning

## Environment Variables Required
- `VISUAL_VERIFICATION_URL` - URL of the visual-verification-service
- `VISUAL_VERIFICATION_API_KEY` - API key for authentication

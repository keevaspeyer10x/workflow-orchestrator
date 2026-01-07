"""
Reusable Utilities

Common utilities for the workflow orchestrator.
"""

import time
import functools
from typing import Tuple, Type, Callable, TypeVar, Any

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exceptions: Tuple of exception types to catch and retry on

    Returns:
        Decorated function that will retry on specified exceptions

    Example:
        @retry_with_backoff(max_retries=3, exceptions=(ConnectionError, TimeoutError))
        def fetch_data():
            return requests.get(url)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Exception = Exception("No attempts made")
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        time.sleep(delay)
            raise last_error
        return wrapper
    return decorator


def slugify(text: str, max_length: int = 30) -> str:
    """
    Convert text to a URL/filename-safe slug.

    Args:
        text: Input text to slugify
        max_length: Maximum length of output (default: 30)

    Returns:
        Lowercase string with only alphanumeric chars and hyphens
    """
    import re
    # Lowercase and replace spaces/underscores with hyphens
    slug = text.lower().strip()
    slug = re.sub(r'[\s_]+', '-', slug)
    # Remove non-alphanumeric characters except hyphens
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    # Trim hyphens from ends
    slug = slug.strip('-')
    # Truncate to max length
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('-')
    return slug or 'untitled'

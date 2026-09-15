"""Global in-process request rate limiter for Gemini API calls.

Enforces a configurable minimum interval between outgoing requests to prevent
RPM quota exhaustion during concurrent or rapid pipeline stages.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class GeminiRateLimiter:
    """Thread-safe rate limiter enforcing a minimum interval between Gemini requests."""

    def __init__(self, min_interval: Optional[float] = None):
        self._lock = threading.Lock()
        self._last_request_time: float = 0.0
        self._min_interval = min_interval

    @property
    def min_interval(self) -> float:
        if self._min_interval is not None:
            return self._min_interval
        # Read from environment with safe default (3.0s -> max 20 RPM)
        val = os.getenv("GEMINI_MIN_REQUEST_INTERVAL", "3.0")
        try:
            return float(val)
        except ValueError:
            return 3.0

    @min_interval.setter
    def min_interval(self, value: Optional[float]) -> None:
        self._min_interval = value

    @property
    def is_enabled(self) -> bool:
        env_enabled = os.getenv("GEMINI_RATE_LIMIT_ENABLED")
        if env_enabled is not None:
            return env_enabled.lower() not in ("false", "0", "no")
        # In unit tests (under pytest), disable by default so sleep mocks and assertions are unaffected
        if "PYTEST_CURRENT_TEST" in os.environ:
            return False
        return self.min_interval > 0

    def acquire(self) -> float:
        """Wait if necessary to ensure minimum interval since last request.

        Returns the number of seconds slept (0.0 if no sleep needed).
        """
        if not self.is_enabled:
            return 0.0

        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            interval = self.min_interval
            wait_time = interval - elapsed

            if wait_time > 0 and self._last_request_time > 0:
                logger.debug("Rate limiter: sleeping %.2fs to maintain <= %.1f RPM", wait_time, 60.0 / interval if interval > 0 else 0)
                time.sleep(wait_time)
                now = time.time()
                slept = wait_time
            else:
                slept = 0.0

            self._last_request_time = now
            return slept

    def reset(self) -> None:
        """Reset state for tests."""
        with self._lock:
            self._last_request_time = 0.0


# Global singleton instance
gemini_rate_limiter = GeminiRateLimiter()

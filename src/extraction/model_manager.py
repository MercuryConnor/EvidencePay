"""Model manager for provider-specific LLM fallback, quota handling, resilience, and discovery.

Features:
1. Runtime Gemini model discovery via client.models.list()
2. Error categorization: INVALID_MODEL, DAILY_QUOTA_EXHAUSTED, RATE_LIMITED,
   TEMPORARILY_UNAVAILABLE, TRANSIENT_ERROR, PERMANENT_ERROR
3. Health tracking per model (healthy, rate_limited, temporarily_unavailable,
   daily_quota_exhausted, invalid)
4. Fast failover: zero retries on 404 (INVALID_MODEL) or daily quota, bounded retries on 503
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Error Categorization ─────────────────────────────────────────────

class ModelErrorKind(str, Enum):
    """Categorized errors for API responses."""
    INVALID_MODEL = "INVALID_MODEL"                     # 404 / NOT_FOUND
    DAILY_QUOTA_EXHAUSTED = "DAILY_QUOTA_EXHAUSTED"     # 429 with daily quota metrics
    RATE_LIMITED = "RATE_LIMITED"                       # 429 RPM / concurrency limits
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE" # 503, 500, 502, 504
    TRANSIENT_ERROR = "TRANSIENT_ERROR"                 # network timeout / connection drops
    PERMANENT_ERROR = "PERMANENT_ERROR"                 # auth failure, malformed payload


class ModelHealthState(str, Enum):
    """Health / quarantine state for each LLM model."""
    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    DAILY_QUOTA_EXHAUSTED = "daily_quota_exhausted"
    INVALID = "invalid"


# ── Exceptions ────────────────────────────────────────────────────────

class InfrastructureError(Exception):
    """Base exception for infrastructure failures (network, API, quota, outage).

    Infrastructure failures indicate that document processing could not be performed
    and must NEVER be recorded as an accounting business decision (e.g. non-payable decline).
    """


class InvalidModelError(InfrastructureError):
    """Raised when an LLM model does not exist or is not supported (404).

    Never retried; model is immediately marked invalid for the entire run.
    """

    def __init__(self, model_name: str, message: str = ""):
        super().__init__(f"Model '{model_name}' is invalid/not found: {message}")
        self.model_name = model_name
        self.message = message


class DailyQuotaExhaustedError(InfrastructureError):
    """Raised when an LLM model exceeds its daily request/token quota.

    Signals that the model cannot serve further requests today and should
    be marked daily quota exhausted for this run without backoff retries.
    """

    def __init__(self, model_name: str, message: str = ""):
        super().__init__(f"Daily quota exhausted for model '{model_name}': {message}")
        self.model_name = model_name
        self.message = message


class TemporaryModelUnavailableError(InfrastructureError):
    """Raised when an LLM model fails its retry budget due to transient server errors (e.g. 503)."""

    def __init__(self, model_name: str, message: str = ""):
        super().__init__(f"Model '{model_name}' temporarily unavailable: {message}")
        self.model_name = model_name
        self.message = message


class RateLimitExceededError(TemporaryModelUnavailableError):
    """Raised when a model is rate-limited (RPM) and exhausted its retry budget."""

    def __init__(self, model_name: str, message: str = ""):
        super().__init__(model_name, f"rate limited (429 RPM): {message}" if message else "rate limited (429 RPM)")


class AllModelsUnavailableError(InfrastructureError):
    """Raised when all models in the pool are exhausted, invalid, or unavailable."""


# ── Error Classifier ──────────────────────────────────────────────────

def is_daily_quota_exhausted(exc: Exception) -> bool:
    """Detect if an exception indicates daily quota exhaustion (vs a transient RPM rate limit)."""
    message = str(exc)
    quota_indicators = [
        "GenerateRequestsPerDayPerModel",
        "GenerateRequestsPerDayPerProjectPerModel",
        "generate_content_free_tier_requests",
        "DailyQuotaExceeded",
        "Daily quota exceeded",
        "Quota exceeded for quota metric 'Generate Content API requests per day'",
        "per day per model",
        "per-day",
    ]
    return any(indicator.lower() in message.lower() for indicator in quota_indicators)


def classify_gemini_error(exc: Exception) -> tuple[ModelErrorKind, str]:
    """Classify exception into a structured ModelErrorKind and concise summary string."""
    msg = str(exc)
    msg_lower = msg.lower()

    # 1. 404 / NOT_FOUND -> INVALID_MODEL
    if "404" in msg or "not_found" in msg_lower or "is not found" in msg_lower or "model not found" in msg_lower:
        return ModelErrorKind.INVALID_MODEL, "returned 404 NOT_FOUND"

    # 2. Daily Quota Exhaustion
    if is_daily_quota_exhausted(exc):
        return ModelErrorKind.DAILY_QUOTA_EXHAUSTED, "daily quota exhausted"

    # 3. Rate Limited (RPM / 429 without daily quota marker)
    if "429" in msg or "resourceexhausted" in msg_lower or "too many requests" in msg_lower or "quota exceeded" in msg_lower:
        return ModelErrorKind.RATE_LIMITED, "rate limited (429 RPM)"

    # 4. Temporarily Unavailable (503, 500, 502, 504, capacity)
    if "503" in msg or "no capacity available" in msg_lower:
        return ModelErrorKind.TEMPORARILY_UNAVAILABLE, "returned 503"
    if (
        any(code in msg for code in ("500", "502", "504"))
        or "serviceunavailable" in msg_lower
        or "unavailable" in msg_lower
    ):
        return ModelErrorKind.TEMPORARILY_UNAVAILABLE, "temporarily unavailable"

    # 5. Transient Network Errors
    if "timeout" in msg_lower or "timed out" in msg_lower or "connection reset" in msg_lower or "remotedisconnected" in msg_lower:
        return ModelErrorKind.TRANSIENT_ERROR, "transient network timeout/reset"

    # 6. Permanent Errors (auth, bad request)
    first_line = msg.splitlines()[0] if msg else type(exc).__name__
    return ModelErrorKind.PERMANENT_ERROR, f"permanent error: {first_line[:60]}"


# ── Model Discovery ───────────────────────────────────────────────────

def discover_gemini_models(
    client: Any,
    preferred_models: Optional[List[str]] = None,
) -> List[str]:
    """Discover usable Gemini models from the API, filtered and ordered by configured preference.

    Validates that each discovered model supports content generation and multimodal tasks.
    Falls back to preferred_models or safe defaults if discovery fails or client is offline/mock.
    """
    defaults = preferred_models or ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-2.5-flash"]
    if not hasattr(client, "models") or not hasattr(client.models, "list"):
        logger.debug("Client does not support models.list(); using configured defaults: %s", defaults)
        return defaults

    try:
        discovered: List[str] = []
        for m in client.models.list():
            name = getattr(m, "name", "")
            # Strip 'models/' prefix
            clean_name = name.replace("models/", "").strip()
            if not clean_name:
                continue

            # Must support generateContent
            actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None)
            if actions and "generateContent" not in actions:
                continue

            # Filter out non-text/vision audio-only or tts-only preview variants
            name_lower = clean_name.lower()
            if any(term in name_lower for term in ("tts", "audio", "image-preview", "realtime")):
                continue

            # Keep flash and general models
            if "flash" in name_lower or "pro" in name_lower or "gemini" in name_lower:
                discovered.append(clean_name)

        if not discovered:
            logger.warning("Discovery returned empty usable models list; using configured defaults.")
            return defaults

        # Order by preferred_models first, then append other discovered models
        ordered_models: List[str] = []
        discovered_set = set(discovered)

        # 1. Preferred models that exist in discovered set
        for pref in defaults:
            if pref in discovered_set and pref not in ordered_models:
                ordered_models.append(pref)

        # 2. Add remaining discovered models
        for disc in discovered:
            if disc not in ordered_models:
                ordered_models.append(disc)

        logger.info("Discovered %d usable Gemini models. Prioritized: %s", len(ordered_models), ordered_models[:5])
        return ordered_models

    except Exception as e:
        logger.warning("Runtime model discovery failed (%s); using configured fallback pool: %s", e, defaults)
        return defaults


# ── Model Manager ─────────────────────────────────────────────────────

class GeminiModelManager:
    """Manages Gemini model selection, discovery, failure classification, and resilient failover."""

    def __init__(
        self,
        model_pool: Optional[List[str]] = None,
        primary_model: Optional[str] = None,
    ):
        self._configured_pool = model_pool
        self._configured_primary = primary_model
        self._discovered_pool: Optional[List[str]] = None
        self.model_states: Dict[str, ModelHealthState] = {}
        self.skip_reasons: Dict[str, str] = {}
        self.fallback_count: int = 0
        self.last_used_model: Optional[str] = None
        self.last_fallback_reason: Optional[str] = None

    @property
    def daily_exhausted_models(self) -> Set[str]:
        return {m for m, state in self.model_states.items() if state == ModelHealthState.DAILY_QUOTA_EXHAUSTED}

    @property
    def temporarily_unavailable_models(self) -> Set[str]:
        return {m for m, state in self.model_states.items() if state == ModelHealthState.TEMPORARILY_UNAVAILABLE}

    @property
    def invalid_models(self) -> Set[str]:
        return {m for m, state in self.model_states.items() if state == ModelHealthState.INVALID}

    @property
    def exhausted_models(self) -> Set[str]:
        """Backwards compatibility: returns all quarantined / unusable models."""
        return {m for m, state in self.model_states.items() if state != ModelHealthState.HEALTHY}

    def initialize_discovery(self, client: Any) -> List[str]:
        """Discover models from client and update pool."""
        preferred = self.get_configured_models()
        self._discovered_pool = discover_gemini_models(client, preferred)
        # Initialize discovered models to HEALTHY if not already set
        for m in self._discovered_pool:
            if m not in self.model_states:
                self.model_states[m] = ModelHealthState.HEALTHY
        return list(self._discovered_pool)

    def get_configured_models(self) -> List[str]:
        """Return the list of configured models from env or defaults."""
        if self._configured_pool:
            return list(self._configured_pool)

        # 1. Check GEMINI_MODELS or LLM_MODEL_POOL
        configured = os.getenv("GEMINI_MODELS", os.getenv("LLM_MODEL_POOL", ""))
        if configured:
            models = [m.strip() for m in configured.split(",") if m.strip()]
            if models:
                return models

        # 2. Check LLM_MODEL
        primary = self._configured_primary or os.getenv("LLM_MODEL", "gemini-3.5-flash")
        defaults = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-2.5-flash"]
        if primary not in defaults:
            return [primary] + defaults
        return defaults

    def get_all_ordered_models(self) -> List[str]:
        """Get ordered list of all configured or discovered models, primary first."""
        base_pool = self._discovered_pool if self._discovered_pool is not None else self.get_configured_models()
        primary = self._configured_primary or os.getenv("LLM_MODEL", base_pool[0] if base_pool else "gemini-3.5-flash")
        ordered = [primary] + [m for m in base_pool if m != primary]
        # Ensure all models have an initial state
        for m in ordered:
            if m not in self.model_states:
                self.model_states[m] = ModelHealthState.HEALTHY
        return ordered

    def get_models_to_try(self) -> List[str]:
        """Get available models in priority order, excluding unavailable ones."""
        ordered = self.get_all_ordered_models()
        return [m for m in ordered if self.is_available(m)[0]]

    def is_available(self, model_name: str) -> Tuple[bool, str]:
        """Check if a model is currently available to serve requests."""
        state = self.model_states.get(model_name, ModelHealthState.HEALTHY)
        reason = self.skip_reasons.get(model_name, "")

        if state == ModelHealthState.INVALID:
            return False, reason or "invalid model (404 NOT_FOUND)"
        if state == ModelHealthState.DAILY_QUOTA_EXHAUSTED:
            return False, reason or "daily quota exhausted"
        if state == ModelHealthState.TEMPORARILY_UNAVAILABLE:
            return False, reason or "temporarily unavailable (outage/503)"
        if state == ModelHealthState.RATE_LIMITED:
            return False, reason or "rate limited (cooldown active)"
        return True, "healthy"

    def get_model_status(self, model_name: str) -> Tuple[bool, str]:
        """Check if model is available, returning (is_available, status_string)."""
        return self.is_available(model_name)

    def mark_invalid(self, model_name: str, reason: str = "") -> None:
        """Mark model as permanently invalid (404 / unsupported). Never retried."""
        self.model_states[model_name] = ModelHealthState.INVALID
        self.skip_reasons[model_name] = reason or "invalid_model_404"
        self.fallback_count += 1
        self.last_fallback_reason = reason or "invalid_model_404"
        logger.warning("Model '%s' quarantined as INVALID (%s)", model_name, reason)

    def mark_daily_exhausted(self, model_name: str, reason: str = "") -> None:
        """Mark model as permanently exhausted for today due to daily quota."""
        self.model_states[model_name] = ModelHealthState.DAILY_QUOTA_EXHAUSTED
        self.skip_reasons[model_name] = reason or "daily_quota_exhausted"
        self.fallback_count += 1
        self.last_fallback_reason = reason or "daily_quota_exhausted"
        logger.warning("Model '%s' quarantined for daily quota exhaustion", model_name)

    def mark_temporarily_unavailable(self, model_name: str, reason: str = "") -> None:
        """Mark model as temporarily unavailable due to transient server/network outages."""
        self.model_states[model_name] = ModelHealthState.TEMPORARILY_UNAVAILABLE
        self.skip_reasons[model_name] = reason or "temporarily_unavailable"
        self.fallback_count += 1
        self.last_fallback_reason = reason or "temporarily_unavailable"
        logger.warning("Model '%s' temporarily quarantined (%s)", model_name, reason)

    def mark_rate_limited(self, model_name: str, reason: str = "") -> None:
        """Mark model as rate-limited (RPM). Can be cleared after backoff."""
        self.model_states[model_name] = ModelHealthState.RATE_LIMITED
        self.skip_reasons[model_name] = reason or "rate_limited_429"
        self.fallback_count += 1
        self.last_fallback_reason = reason or "rate_limited"

    def mark_exhausted(self, model_name: str, reason: str = "") -> None:
        """Backwards compatibility: defaults to daily exhausted."""
        self.mark_daily_exhausted(model_name, reason)

    def record_success(self, model_name: str) -> None:
        """Record successful extraction using model_name and mark healthy."""
        self.model_states[model_name] = ModelHealthState.HEALTHY
        self.skip_reasons.pop(model_name, None)
        self.last_used_model = model_name

    def reset(self) -> None:
        """Reset all state (for tests and session reinitialization)."""
        self.model_states.clear()
        self.skip_reasons.clear()
        self._discovered_pool = None
        self.fallback_count = 0
        self.last_used_model = None
        self.last_fallback_reason = None


# Global singleton instance for the application
gemini_manager = GeminiModelManager()

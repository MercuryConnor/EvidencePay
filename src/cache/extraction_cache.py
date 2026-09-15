"""Local filesystem extraction cache with pass-aware composite keying."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(".cache/extractions")


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_cache_key(
    file_path: Path,
    pass_type: str = "initial",
    focus: str = "",
    prompt_version: str = "v1",
) -> str:
    """Compute cache key incorporating document hash, prompt version, pass type, and focus."""
    file_hash = compute_file_hash(file_path)
    if pass_type == "initial" and not focus:
        # Preserve backwards compatibility for initial extractions
        return file_hash
    composite = f"{file_hash}:{prompt_version}:{pass_type}:{focus}"
    focus_hash = hashlib.sha256(composite.encode()).hexdigest()[:12]
    return f"{file_hash}_{pass_type}_{focus_hash}"


class ExtractionCache:
    """Pass-aware disk cache for extraction responses."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(
        self,
        file_path: Path,
        pass_type: str = "initial",
        focus: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached extraction JSON if present for this pass type and focus context."""
        try:
            cache_key = compute_cache_key(file_path, pass_type=pass_type, focus=focus)
            cache_file = self.cache_dir / f"{cache_key}.json"
            if cache_file.exists():
                with open(cache_file, "r", encoding="utf-8") as f:
                    logger.debug("Cache hit for %s [%s] (%s)", file_path.name, pass_type, cache_key[:12])
                    return json.load(f)
        except Exception as e:
            logger.debug("Failed reading cache for %s: %s", file_path.name, e)
        return None

    def put(
        self,
        file_path: Path,
        data: Dict[str, Any],
        pass_type: str = "initial",
        focus: str = "",
    ) -> None:
        """Store extraction JSON in cache with pass type and focus context."""
        try:
            cache_key = compute_cache_key(file_path, pass_type=pass_type, focus=focus)
            cache_file = self.cache_dir / f"{cache_key}.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug("Cached extraction for %s [%s] (%s)", file_path.name, pass_type, cache_key[:12])
        except Exception as e:
            logger.debug("Failed writing cache for %s: %s", file_path.name, e)

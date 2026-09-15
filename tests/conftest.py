"""Pytest configuration — adds candidate_kit and project root to sys.path."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CANDIDATE_KIT = _ROOT / "candidate_kit" / "candidate_kit"

for p in [str(_ROOT), str(_CANDIDATE_KIT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

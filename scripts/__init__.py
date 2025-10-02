"""Utility package exposing Prometheus bootstrap scripts."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if (repo_str := str(_REPO_ROOT)) not in sys.path:
    sys.path.append(repo_str)

__all__ = ["_REPO_ROOT"]

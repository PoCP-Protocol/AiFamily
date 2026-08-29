"""Shared fixtures for architecture tests.

All architecture tests need the repository root to resolve paths like
``governance/`` or ``backend/`` regardless of the CWD pytest was invoked
from. Per R12 (no implicit layout coupling), we compute this once here
from ``__file__`` rather than relying on cwd, and every test file reuses
it via the ``repo_root`` fixture instead of re-deriving its own path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# tests/architecture/conftest.py -> parents[0]=architecture, [1]=tests, [2]=repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT

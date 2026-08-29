"""Shared Python contracts package.

STRUCTURE_ONLY — see `intelligence/design_copilot/README.md` and
`domains/product_strategy/README.md`. Nothing in this package is wired into
any FastAPI app or real database yet; it exists so multiple skeleton domains
share one type-level vocabulary instead of each domain inventing its own.
"""

from __future__ import annotations

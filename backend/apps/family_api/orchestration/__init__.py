"""Composition-root orchestration for cross-domain flows.

Nothing here belongs inside a single domain: each module in this package
explicitly names two or more domain application services and sequences calls
across them. Domains stay decoupled from each other (family_need never imports
commerce or service; commerce never imports journey); this package is the one
place allowed to know about more than one of them at once.
"""

from __future__ import annotations

__all__: list[str] = []

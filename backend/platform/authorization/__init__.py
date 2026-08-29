"""Minimal fail-closed authorization policy engine.

See governance/MIGRATION_MANIFEST.yaml capability
`platform_authorization_policy` (disposition REIMPLEMENT). Behavior is
re-derived from the *test* semantics of the source repository's
`family-authorization.policy.ts` (unknown role -> fail closed), not from
its code.
"""

from __future__ import annotations

from backend.platform.authorization.policy import Decision, PolicyEngine, PolicyRule

__all__ = ["Decision", "PolicyEngine", "PolicyRule"]

"""Minimal fail-closed authorization policy engine.

See governance/MIGRATION_MANIFEST.yaml capability
`platform_authorization_policy` (disposition REIMPLEMENT). Behavior is
re-derived from the *test* semantics of the source repository's
`family-authorization.policy.ts` (unknown role -> fail closed), not from
its code.
"""

from __future__ import annotations

from backend.platform.authorization.policy import Decision, PolicyEngine, PolicyRule
from backend.platform.authorization.review_receipts import (
    REVIEW_ACTION,
    REVIEW_RESOURCE_TYPE,
    ReviewReceipt,
    ReviewReceiptBinding,
    ReviewReceiptDenied,
    ReviewReceiptInvalid,
    ReviewReceiptIssuer,
)

__all__ = [
    "REVIEW_ACTION",
    "REVIEW_RESOURCE_TYPE",
    "Decision",
    "PolicyEngine",
    "PolicyRule",
    "ReviewReceipt",
    "ReviewReceiptBinding",
    "ReviewReceiptDenied",
    "ReviewReceiptInvalid",
    "ReviewReceiptIssuer",
]

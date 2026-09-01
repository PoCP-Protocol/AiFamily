"""Closed family scopes accepted by the reviewed-understanding handoff."""

from __future__ import annotations

SUPPORTED_UNDERSTANDING_SCOPE_KINDS = frozenset({"assessment", "problem-understanding"})


def supported_understanding_scope_refs(*, tenant_id: str, family_id: str) -> frozenset[str]:
    """Return the complete allowlist; callers must not infer new scope kinds."""

    return frozenset(
        f"family://{tenant_id}/{family_id}/{kind}"
        for kind in SUPPORTED_UNDERSTANDING_SCOPE_KINDS
    )


def is_supported_understanding_scope(
    *, scope_ref: str, tenant_id: str, family_id: str
) -> bool:
    return scope_ref in supported_understanding_scope_refs(
        tenant_id=tenant_id,
        family_id=family_id,
    )


__all__ = [
    "SUPPORTED_UNDERSTANDING_SCOPE_KINDS",
    "is_supported_understanding_scope",
    "supported_understanding_scope_refs",
]

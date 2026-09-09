"""Explicit deployment configuration for family-scoped worker activities."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FamilyWorkerScope:
    """One tenant/family pair a worker is authorized to process."""

    tenant_id: str
    family_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.family_id.strip():
            raise ValueError("worker tenant and family are required")


def resolve_family_worker_scope(
    *,
    environ: dict[str, str] | None = None,
) -> FamilyWorkerScope:
    """Resolve an explicit scope; missing configuration fails closed."""

    values = os.environ if environ is None else environ
    tenant_id = values.get("AIFAMILY_WORKER_TENANT_ID", "").strip()
    family_id = values.get("AIFAMILY_WORKER_FAMILY_ID", "").strip()
    if not tenant_id or not family_id:
        raise RuntimeError("worker family scope configuration is required")
    return FamilyWorkerScope(tenant_id=tenant_id, family_id=family_id)


__all__ = ["FamilyWorkerScope", "resolve_family_worker_scope"]

"""Dependency seams for the Family Need HTTP adapter.

The domain/application layers remain framework agnostic.  The process entry
point must inject a real actor resolver and a repository-backed application
service; the default dependencies fail closed so an unconfigured route cannot
invent a family identity or silently use synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from ..application.service import FamilyNeedApplicationService
from ..domain.value_objects import ActorType


@dataclass(frozen=True)
class FamilyNeedActor:
    """Server-derived identity and family scope for one request."""

    tenant_id: str
    family_id: str
    actor_id: str
    actor_type: ActorType
    region: str = "CN"
    environment: str = "development"


def get_family_need_actor() -> FamilyNeedActor:
    """Require process wiring; never infer identity from a request body."""

    raise HTTPException(status_code=503, detail="family_need_actor_not_wired")


def get_family_need_service() -> FamilyNeedApplicationService:
    """Require a repository/policy-backed application service."""

    raise HTTPException(status_code=503, detail="family_need_service_not_wired")


__all__ = ["FamilyNeedActor", "get_family_need_actor", "get_family_need_service"]

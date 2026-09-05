"""Fail-closed dependencies for commerce catalogue reads."""

from __future__ import annotations

from backend.platform.identity.context import ActorContext

from ..application.ports import CommerceRepositoryPort


async def get_repository() -> CommerceRepositoryPort:
    raise RuntimeError("commerce repository not configured — production persistence is pending")


def get_actor_context() -> ActorContext:
    raise RuntimeError("commerce actor context resolver not configured")

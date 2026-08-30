"""Composition helpers for the governed multimodal experience router.

The main application factory owns when these helpers are called.  Keeping the
helpers separate makes the integration patch small while preserving the same
router and dependency graph in every environment.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.intelligence.experience.api import (
    MultimodalDraftRuntimeResolver,
    get_multimodal_draft_runtime_resolver,
)
from backend.intelligence.experience.api import router as experience_router
from backend.intelligence.experience.synthetic_runtime import SyntheticRuntimeResolver


def mount_experience_router(application: FastAPI) -> None:
    """Mount the production-shaped experience API exactly once at the root."""

    application.include_router(experience_router)


def install_experience_runtime_resolver(
    application: FastAPI,
    resolver: MultimodalDraftRuntimeResolver,
) -> None:
    """Install an explicit non-synthetic resolver at the composition root.

    Production identity, consent and provider policy are deployment concerns;
    this helper only installs their already-composed resolver.  Keeping the
    dependency override here makes ``create_app`` injectable without adding
    credentials or request-body scope to the experience router.  Synthetic
    test wiring remains behind :func:`install_synthetic_experience_runtime`.
    """

    if isinstance(resolver, SyntheticRuntimeResolver):
        raise ValueError(
            "synthetic experience resolver must use install_synthetic_experience_runtime"
        )
    if not callable(getattr(resolver, "resolve", None)):
        raise TypeError("experience runtime resolver must implement resolve(family_id)")
    application.dependency_overrides[get_multimodal_draft_runtime_resolver] = (
        lambda resolver=resolver: resolver
    )


def install_synthetic_experience_runtime(
    application: FastAPI,
    *,
    tenant_id: str,
    subject_ids: tuple[str, ...],
    environment: str = "test",
) -> None:
    """Install an explicit request-level resolver for test parity.

    No family is accepted here: the resolver receives it from the URL on each
    request.  The helper refuses every environment other than ``test`` and
    therefore cannot silently place synthetic data on a production app.
    """

    if environment != "test":
        raise ValueError("synthetic experience wiring only supports the test environment")
    resolver = SyntheticRuntimeResolver(
        tenant_id=tenant_id,
        subject_ids=subject_ids,
        environment=environment,
    )
    application.dependency_overrides[get_multimodal_draft_runtime_resolver] = (
        lambda resolver=resolver: resolver
    )


__all__ = [
    "install_experience_runtime_resolver",
    "install_synthetic_experience_runtime",
    "mount_experience_router",
]

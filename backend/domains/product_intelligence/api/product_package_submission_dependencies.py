"""Request-scoped composition for ProductPackage review submission HTTP."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..application.context import ActorContext
from ..application.product_package_source_resolution import ProductPackageSourceResolver
from ..application.product_package_submission import (
    ProductPackageSubmissionError,
    ProductPackageSubmissionForbiddenError,
    ProductPackageSubmissionRepository,
    authorize_product_package_read,
    authorize_product_package_submission,
)
from ..infrastructure.product_package_submission_repository import (
    SqlAlchemyProductPackageSubmissionRepository,
)
from .dependencies import get_actor_context

ProductPackageSourceResolverFactory = Callable[[AsyncSession], ProductPackageSourceResolver]


@dataclass(frozen=True, slots=True)
class ProductPackageSubmissionServices:
    repository: ProductPackageSubmissionRepository
    source_resolver: ProductPackageSourceResolver | None


_session_factory: async_sessionmaker[AsyncSession] | None = None
_source_resolver_factory: ProductPackageSourceResolverFactory | None = None


def configure_product_package_submission_services(
    session_factory: async_sessionmaker[AsyncSession] | None,
    source_resolver_factory: ProductPackageSourceResolverFactory | None,
) -> None:
    global _session_factory, _source_resolver_factory
    _session_factory = session_factory
    _source_resolver_factory = source_resolver_factory


def clear_product_package_submission_services() -> None:
    configure_product_package_submission_services(None, None)


async def get_product_package_actor_context(request: Request) -> ActorContext:
    """Map the app-owned identity bridge to stable fail-closed HTTP outcomes."""

    try:
        return await get_actor_context(request)
    except PermissionError as exc:
        code = str(exc)
        if code in {"BEARER_REQUIRED", "BEARER_INVALID", "IDENTITY_SESSION_EXPIRED"}:
            raise HTTPException(
                status_code=401,
                detail=code,
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raise HTTPException(status_code=503, detail="PRODUCT_PACKAGE_IDENTITY_UNAVAILABLE") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="PRODUCT_PACKAGE_IDENTITY_UNAVAILABLE") from exc


def _authorization_http(callable_, context: ActorContext) -> ActorContext:
    try:
        callable_(context)
    except ProductPackageSubmissionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc
    except ProductPackageSubmissionError as exc:
        raise HTTPException(
            status_code=503,
            detail="PRODUCT_PACKAGE_TRUSTED_CONTEXT_INVALID",
        ) from exc
    return context


async def get_authorized_product_package_submitter(
    context: ActorContext = Depends(get_product_package_actor_context),
) -> ActorContext:
    return _authorization_http(authorize_product_package_submission, context)


async def get_authorized_product_package_reader(
    context: ActorContext = Depends(get_product_package_actor_context),
) -> ActorContext:
    return _authorization_http(authorize_product_package_read, context)


async def get_product_package_submission_services() -> AsyncGenerator[
    ProductPackageSubmissionServices, None
]:
    if _session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="PRODUCT_PACKAGE_TRUSTED_SOURCE_RESOLVER_NOT_CONFIGURED",
        )
    async with _session_factory() as session:
        yield ProductPackageSubmissionServices(
            repository=SqlAlchemyProductPackageSubmissionRepository(session),
            source_resolver=(
                _source_resolver_factory(session)
                if _source_resolver_factory is not None
                else None
            ),
        )


async def get_product_package_submission_repository() -> AsyncGenerator[
    ProductPackageSubmissionRepository, None
]:
    if _session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="PRODUCT_PACKAGE_REPOSITORY_NOT_CONFIGURED",
        )
    async with _session_factory() as session:
        yield SqlAlchemyProductPackageSubmissionRepository(session)


def get_product_package_submission_clock() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "ProductPackageSourceResolverFactory",
    "ProductPackageSubmissionServices",
    "clear_product_package_submission_services",
    "configure_product_package_submission_services",
    "get_authorized_product_package_reader",
    "get_authorized_product_package_submitter",
    "get_product_package_actor_context",
    "get_product_package_submission_clock",
    "get_product_package_submission_repository",
    "get_product_package_submission_services",
]

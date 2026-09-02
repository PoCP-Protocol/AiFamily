"""Isolated, unmounted composition seam for receipt health observation."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..application.context import ActorContext
from ..application.product_package_evidence_admission import ProductPackageEvidenceReader
from ..application.product_package_submission import (
    ProductPackageSubmissionError,
    ProductPackageSubmissionForbiddenError,
    authorize_product_package_read,
)
from ..infrastructure.product_package_evidence_reader import (
    SqlAlchemyProductPackageEvidenceReader,
)
from .product_package_submission_dependencies import get_product_package_actor_context

_session_factory: async_sessionmaker[AsyncSession] | None = None
_NO_STORE = {"Cache-Control": "no-store"}


def configure_evidence_receipt_health_session_factory(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    global _session_factory
    _session_factory = session_factory


def clear_evidence_receipt_health_session_factory() -> None:
    configure_evidence_receipt_health_session_factory(None)


async def get_evidence_receipt_health_reader() -> AsyncGenerator[
    ProductPackageEvidenceReader, None
]:
    if _session_factory is None:
        raise HTTPException(
            status_code=503,
            detail="EVIDENCE_RECEIPT_HEALTH_REPOSITORY_NOT_CONFIGURED",
            headers=_NO_STORE,
        )
    async with _session_factory() as session:
        yield SqlAlchemyProductPackageEvidenceReader(session)


def get_evidence_receipt_health_clock() -> datetime:
    return datetime.now(UTC)


async def get_authorized_evidence_receipt_health_context(
    request: Request,
) -> ActorContext:
    try:
        context = await get_product_package_actor_context(request)
        authorize_product_package_read(context)
        return context
    except HTTPException as exc:
        headers = dict(exc.headers or {})
        headers.update(_NO_STORE)
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=headers,
        ) from exc
    except ProductPackageSubmissionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.code, headers=_NO_STORE) from exc
    except ProductPackageSubmissionError as exc:
        raise HTTPException(
            status_code=503,
            detail="EVIDENCE_RECEIPT_HEALTH_TRUSTED_CONTEXT_INVALID",
            headers=_NO_STORE,
        ) from exc


__all__ = [
    "clear_evidence_receipt_health_session_factory",
    "configure_evidence_receipt_health_session_factory",
    "get_evidence_receipt_health_clock",
    "get_evidence_receipt_health_reader",
    "get_authorized_evidence_receipt_health_context",
]

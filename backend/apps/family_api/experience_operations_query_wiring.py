"""Composition helpers for the operator-only Experience operations API."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.experience_operations_query_api import (
    get_experience_operations_cursor_signer,
    get_experience_operations_query_service,
)
from backend.intelligence.evaluation.operator_identity import (
    HttpRequestOperatorIdentityPort,
    OperatorIdentityPort,
)
from backend.intelligence.experience.operations_audit_persistence import (
    SqlAlchemyExperienceOperationsAuditSessionSink,
    SqlAlchemyExperienceOperationsAuditSink,
)
from backend.intelligence.experience.operations_query import (
    EXPERIENCE_OPERATIONS_READ_SCOPE,
    AuthorizedExperienceOperationsQueryService,
    ExperienceOperationsAuditSink,
    ExperienceOperationsQueryRuntime,
    HmacExperienceOperationsCursorSigner,
)
from backend.platform.security.mtls import MtlsClientConfig


def install_experience_operations_query(
    application: FastAPI,
    service: AuthorizedExperienceOperationsQueryService,
    signer: HmacExperienceOperationsCursorSigner,
) -> None:
    """Install an explicit identity-bound service and cursor signer."""

    if not isinstance(service, AuthorizedExperienceOperationsQueryService):
        raise TypeError(
            "experience operations query service must be AuthorizedExperienceOperationsQueryService"
        )
    if not isinstance(signer, HmacExperienceOperationsCursorSigner):
        raise TypeError(
            "experience operations cursor signer must be HmacExperienceOperationsCursorSigner"
        )
    def provide_service() -> AuthorizedExperienceOperationsQueryService:
        return service

    def provide_signer() -> HmacExperienceOperationsCursorSigner:
        return signer

    # Avoid lambda default arguments here: FastAPI deep-copies dependency
    # defaults while resolving requests, and a durable service may contain an
    # async_sessionmaker that references an unpickleable driver module.
    application.dependency_overrides[get_experience_operations_query_service] = provide_service
    application.dependency_overrides[get_experience_operations_cursor_signer] = provide_signer


def build_production_experience_operations_query_service(
    *,
    environment: str,
    identity_port: OperatorIdentityPort,
    runtime: ExperienceOperationsQueryRuntime,
    required_scope: str = EXPERIENCE_OPERATIONS_READ_SCOPE,
    audit_sink: ExperienceOperationsAuditSink | None = None,
) -> AuthorizedExperienceOperationsQueryService:
    """Compose staging/production operator access without hidden credentials."""

    return AuthorizedExperienceOperationsQueryService(
        environment=environment,
        identity_port=identity_port,
        runtime=runtime,
        required_scope=required_scope,
        audit_sink=audit_sink,
    )


def build_sql_experience_operations_audit_sink(
    session: AsyncSession,
) -> SqlAlchemyExperienceOperationsAuditSink:
    """Build the durable sink from the caller-owned request/UoW session."""

    if not isinstance(session, AsyncSession):
        raise TypeError("experience operations audit sink requires AsyncSession")
    return SqlAlchemyExperienceOperationsAuditSink(session)


def build_production_experience_operations_audit_sink(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlAlchemyExperienceOperationsAuditSessionSink:
    """Compose a durable per-access transaction for operator query requests."""

    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("experience operations audit session factory is required")
    return SqlAlchemyExperienceOperationsAuditSessionSink(session_factory)


def build_production_experience_operations_query_wiring(
    *,
    environment: str,
    identity_port: OperatorIdentityPort,
    runtime: ExperienceOperationsQueryRuntime,
    cursor_signer: HmacExperienceOperationsCursorSigner,
    session_factory: async_sessionmaker[AsyncSession],
    required_scope: str = EXPERIENCE_OPERATIONS_READ_SCOPE,
) -> Callable[[FastAPI], None]:
    """Compose the complete production hook consumed by ``create_app``."""

    if not isinstance(cursor_signer, HmacExperienceOperationsCursorSigner):
        raise TypeError(
            "experience operations cursor signer must be HmacExperienceOperationsCursorSigner"
        )
    service = build_production_experience_operations_query_service(
        environment=environment,
        identity_port=identity_port,
        runtime=runtime,
        required_scope=required_scope,
        audit_sink=build_production_experience_operations_audit_sink(session_factory),
    )

    def install(application: FastAPI) -> None:
        install_experience_operations_query(application, service, cursor_signer)

    return install


def build_http_production_experience_operations_query_wiring(
    *,
    environment: str,
    identity_base_url: str,
    runtime: ExperienceOperationsQueryRuntime,
    cursor_signer: HmacExperienceOperationsCursorSigner,
    session_factory: async_sessionmaker[AsyncSession],
    identity_client: httpx.AsyncClient | None = None,
    identity_client_config: MtlsClientConfig | None = None,
    required_scope: str = EXPERIENCE_OPERATIONS_READ_SCOPE,
) -> Callable[[FastAPI], None]:
    """Compose operations API with request-bound HTTP identity resolution."""

    identity_port = HttpRequestOperatorIdentityPort(
        base_url=identity_base_url,
        client=identity_client,
        client_config=identity_client_config,
    )
    return build_production_experience_operations_query_wiring(
        environment=environment,
        identity_port=identity_port,
        runtime=runtime,
        cursor_signer=cursor_signer,
        session_factory=session_factory,
        required_scope=required_scope,
    )


__all__ = [
    "build_production_experience_operations_query_service",
    "build_production_experience_operations_audit_sink",
    "build_http_production_experience_operations_query_wiring",
    "build_production_experience_operations_query_wiring",
    "build_sql_experience_operations_audit_sink",
    "install_experience_operations_query",
]

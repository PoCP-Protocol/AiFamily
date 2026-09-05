"""Composition helpers for the operator-only evaluation query API."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from fastapi import FastAPI

from backend.apps.family_api.evaluation_query_api import get_evaluation_query_service
from backend.intelligence.evaluation.operator_identity import (
    HttpRequestOperatorIdentityPort,
    OperatorIdentityPort,
)
from backend.intelligence.evaluation.query import (
    EVALUATION_READ_SCOPE,
    AuthorizedEvaluationQueryService,
    EvaluationArchiveQueryRuntime,
)
from backend.platform.security.mtls import MtlsClientConfig


def install_evaluation_query_service(
    application: FastAPI,
    service: AuthorizedEvaluationQueryService,
) -> None:
    """Install an already-composed identity-bound query service."""

    if not isinstance(service, AuthorizedEvaluationQueryService):
        raise TypeError("evaluation query service must be AuthorizedEvaluationQueryService")
    def provide_service() -> AuthorizedEvaluationQueryService:
        return service

    application.dependency_overrides[get_evaluation_query_service] = provide_service


def build_production_evaluation_query_service(
    *,
    environment: str,
    identity_port: OperatorIdentityPort,
    archive_runtime: EvaluationArchiveQueryRuntime,
    required_scope: str = EVALUATION_READ_SCOPE,
) -> AuthorizedEvaluationQueryService:
    """Compose staging/production query access without hidden credentials."""

    return AuthorizedEvaluationQueryService(
        environment=environment,
        identity_port=identity_port,
        archive_runtime=archive_runtime,
        required_scope=required_scope,
    )


def build_http_production_evaluation_query_wiring(
    *,
    environment: str,
    identity_base_url: str,
    archive_runtime: EvaluationArchiveQueryRuntime,
    identity_client: httpx.AsyncClient | None = None,
    identity_client_config: MtlsClientConfig | None = None,
    required_scope: str = EVALUATION_READ_SCOPE,
) -> Callable[[FastAPI], None]:
    """Compose evaluation query access with request-bound HTTP identity."""

    identity_port = HttpRequestOperatorIdentityPort(
        base_url=identity_base_url,
        client=identity_client,
        client_config=identity_client_config,
    )
    service = build_production_evaluation_query_service(
        environment=environment,
        identity_port=identity_port,
        archive_runtime=archive_runtime,
        required_scope=required_scope,
    )

    def install(application: FastAPI) -> None:
        install_evaluation_query_service(application, service)

    return install


__all__ = [
    "build_http_production_evaluation_query_wiring",
    "build_production_evaluation_query_service",
    "install_evaluation_query_service",
]

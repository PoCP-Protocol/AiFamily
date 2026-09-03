from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from backend.intelligence.evaluation.operator_identity import (
    HttpOperatorIdentityPort,
    HttpOperatorTokenProvider,
    OperatorIdentity,
    OperatorIdentityError,
)
from backend.platform.security.mtls import MtlsClientConfig


@pytest.mark.asyncio
async def test_http_identity_and_token_adapter_use_explicit_injected_credentials() -> None:
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/identity"):
            return httpx.Response(
                200,
                json={
                    "operator_id": "operator-1",
                    "environment": "staging",
                    "authorization_ref": "key-ref-1",
                    "scopes": ["ai.release.deploy"],
                },
            )
        return httpx.Response(200, json={"access_token": "short-lived-token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        identity = HttpOperatorIdentityPort(
            base_url="https://identity.example",
            bootstrap_token_provider=lambda: "bootstrap-token",
            client=client,
        )
        token_provider = HttpOperatorTokenProvider(
            base_url="https://identity.example",
            identity_port=identity,
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="deployment-platform",
            environment="staging",
            client=client,
        )
        resolved = await identity.resolve(environment="staging")
        token = await token_provider()

    assert resolved == OperatorIdentity(
        operator_id="operator-1",
        environment="staging",
        authorization_ref="key-ref-1",
        scopes=("ai.release.deploy",),
    )
    assert token == "short-lived-token"
    assert calls[0].headers["authorization"] == "Bearer bootstrap-token"
    assert calls[1].headers["authorization"] == "Bearer bootstrap-token"
    assert "short-lived-token" not in repr(token_provider)


@pytest.mark.asyncio
async def test_identity_environment_mismatch_fails_closed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "operator_id": "operator-1",
                "environment": "production",
                "authorization_ref": "key-ref-1",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        identity = HttpOperatorIdentityPort(
            base_url="https://identity.example",
            bootstrap_token_provider=lambda: "bootstrap-token",
            client=client,
        )
        with pytest.raises(OperatorIdentityError, match="ENVIRONMENT_MISMATCH"):
            await identity.resolve(environment="staging")


@pytest.mark.asyncio
async def test_token_exchange_requires_release_deploy_scope() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/identity"):
            return httpx.Response(
                200,
                json={
                    "operator_id": "operator-1",
                    "environment": "staging",
                    "authorization_ref": "key-ref-1",
                    "scopes": ["ai.release.read"],
                },
            )
        raise AssertionError("token exchange must not run without deployment scope")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        identity = HttpOperatorIdentityPort(
            base_url="https://identity.example",
            bootstrap_token_provider=lambda: "bootstrap-token",
            client=client,
        )
        token_provider = HttpOperatorTokenProvider(
            base_url="https://identity.example",
            identity_port=identity,
            bootstrap_token_provider=lambda: "bootstrap-token",
            audience="deployment-platform",
            environment="staging",
            client=client,
        )
        with pytest.raises(OperatorIdentityError, match="SCOPE_MISSING"):
            await token_provider()


@pytest.mark.asyncio
async def test_identity_adapter_can_construct_a_temporary_mtls_client(tmp_path: Path) -> None:
    cert_paths = []
    for name in ("ca.pem", "client.pem", "client.key"):
        path = tmp_path / name
        path.write_text("placeholder", encoding="utf-8")
        cert_paths.append(str(path))
    config = MtlsClientConfig(*cert_paths)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "operator_id": "operator-1",
                "environment": "staging",
                "authorization_ref": "ref-1",
                "scopes": ["ai.evaluation.read"],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    identity_port = HttpOperatorIdentityPort(
        base_url="https://identity.example",
        bootstrap_token_provider=lambda: "bootstrap",
        client_config=config,
    )
    with patch(
        "backend.platform.security.mtls.MtlsClientConfig.build_async_client",
        return_value=client,
    ):
        resolved = await identity_port.resolve(environment="staging")

    assert resolved.operator_id == "operator-1"


def test_identity_and_token_adapters_reject_client_and_mtls_config_together(tmp_path: Path) -> None:
    cert_paths = []
    for name in ("ca.pem", "client.pem", "client.key"):
        path = tmp_path / name
        path.write_text("placeholder", encoding="utf-8")
        cert_paths.append(str(path))
    config = MtlsClientConfig(*cert_paths)

    identity_client = httpx.AsyncClient()
    try:
        with pytest.raises(OperatorIdentityError, match="IDENTITY_MTLS_CLIENT_CONFLICT"):
            HttpOperatorIdentityPort(
                base_url="https://identity.example",
                bootstrap_token_provider=lambda: "bootstrap",
                client=identity_client,
                client_config=config,
            )
    finally:
        asyncio.run(identity_client.aclose())

    identity_port = HttpOperatorIdentityPort(
        base_url="https://identity.example",
        bootstrap_token_provider=lambda: "bootstrap",
    )
    token_client = httpx.AsyncClient()
    try:
        with pytest.raises(OperatorIdentityError, match="TOKEN_MTLS_CLIENT_CONFLICT"):
            HttpOperatorTokenProvider(
                base_url="https://identity.example",
                identity_port=identity_port,
                bootstrap_token_provider=lambda: "bootstrap",
                audience="deployment-platform",
                environment="staging",
                client=token_client,
                client_config=config,
            )
    finally:
        asyncio.run(token_client.aclose())


def test_operator_identity_rejects_empty_identity_and_duplicate_scopes() -> None:
    with pytest.raises(OperatorIdentityError, match="OPERATOR_ID_REQUIRED"):
        OperatorIdentity(operator_id="", environment="staging", authorization_ref="ref")
    with pytest.raises(OperatorIdentityError, match="SCOPES_MUST_BE_UNIQUE"):
        OperatorIdentity(
            operator_id="operator-1",
            environment="staging",
            authorization_ref="ref",
            scopes=("deploy", "deploy"),
        )

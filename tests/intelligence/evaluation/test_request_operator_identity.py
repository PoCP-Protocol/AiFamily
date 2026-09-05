from __future__ import annotations

import httpx
import pytest

from backend.intelligence.evaluation.operator_identity import (
    HttpRequestOperatorIdentityPort,
    OperatorIdentity,
    OperatorIdentityError,
)
from backend.intelligence.evaluation.request_operator_identity import (
    bind_operator_bearer,
    current_operator_bearer,
    parse_bearer_authorization,
    reset_operator_bearer,
)


def test_bearer_parser_and_context_are_strict_and_reset() -> None:
    with pytest.raises(OperatorIdentityError, match="AUTHORIZATION_REQUIRED"):
        parse_bearer_authorization(None)
    with pytest.raises(OperatorIdentityError, match="AUTHORIZATION_INVALID"):
        parse_bearer_authorization("Bearer token with-space")
    marker = bind_operator_bearer("opaque-token")
    try:
        assert current_operator_bearer() == "opaque-token"
    finally:
        reset_operator_bearer(marker)
    with pytest.raises(OperatorIdentityError, match="TOKEN_REQUIRED"):
        current_operator_bearer()


@pytest.mark.asyncio
async def test_request_identity_port_forwards_bearer_and_parses_metadata() -> None:
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "operator_id": "operator-7",
                "environment": "production",
                "authorization_ref": "auth-7",
                "scopes": ["ai.experience.read"],
            },
        )

    marker = bind_operator_bearer("request-secret")
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            port = HttpRequestOperatorIdentityPort(
                base_url="https://identity.example", client=client
            )
            identity = await port.resolve(environment="production")
    finally:
        reset_operator_bearer(marker)

    assert identity == OperatorIdentity(
        "operator-7", "production", "auth-7", ("ai.experience.read",)
    )
    assert calls[0].headers["authorization"] == "Bearer request-secret"
    assert "request-secret" not in repr(port)


@pytest.mark.asyncio
async def test_request_identity_port_fails_closed_without_context_or_bad_response() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    ) as client:
        port = HttpRequestOperatorIdentityPort(
            base_url="https://identity.example", client=client
        )
        with pytest.raises(OperatorIdentityError, match="TOKEN_REQUIRED"):
            await port.resolve(environment="production")

        marker = bind_operator_bearer("opaque-token")
        try:
            with pytest.raises(OperatorIdentityError, match="RESPONSE_INVALID"):
                await port.resolve(environment="production")
        finally:
            reset_operator_bearer(marker)

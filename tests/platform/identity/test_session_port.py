from datetime import UTC, datetime, timedelta

import httpx
import pytest

from backend.platform.identity.session_port import (
    HttpIdentitySessionPort,
    IdentitySessionError,
)


def _session_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "session_id": "session-1",
        "access_token": "opaque-access-token",
        "account_id": "account-1",
        "family_id": "family-1",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
    }
    body.update(overrides)
    return body


@pytest.mark.anyio
async def test_issue_uses_verified_identity_metadata_and_returns_opaque_session() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = request.read()
        seen["headers"] = dict(request.headers)
        return httpx.Response(201, json=_session_body())

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        port = HttpIdentitySessionPort(
            base_url="https://identity.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-secret",
            audience="aifamily-mobile",
            client=client,
        )
        session = await port.issue(
            account_id="account-1", person_id="person-1", family_id="family-1"
        )

    assert seen["path"] == "/v1/identity/sessions"
    assert b"bootstrap-secret" not in seen["json"]  # type: ignore[operator]
    assert b"opaque-access-token" not in seen["json"]  # type: ignore[operator]
    assert session.access_token == "opaque-access-token"
    assert session.session_id == "session-1"


@pytest.mark.anyio
async def test_rotate_separates_current_session_from_json_and_revoke_is_metadata_only() -> None:
    calls: list[tuple[str, bytes, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, request.read(), request.headers.get("x-identity-session")))
        if request.url.path.endswith("/revoke"):
            return httpx.Response(204)
        return httpx.Response(200, json=_session_body(session_id="session-2"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = HttpIdentitySessionPort(
            base_url="https://identity.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-secret",
            audience="aifamily-mobile",
            client=client,
        )
        rotated = await port.rotate(access_token="old-access-token")
        result = await port.revoke(access_token="old-access-token")

    assert rotated.session_id == "session-2"
    assert result is None
    assert calls[0][0].endswith("/rotate")
    assert calls[0][2] == "old-access-token"
    assert b"old-access-token" not in calls[0][1]
    assert calls[1][0].endswith("/revoke")
    assert calls[1][2] == "old-access-token"


@pytest.mark.anyio
async def test_introspect_returns_metadata_without_requiring_access_token_in_response() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["session"] = request.headers.get("x-identity-session")
        return httpx.Response(
            200,
            json={
                "session_id": "session-verified",
                "account_id": "account-1",
                "family_id": "family-1",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = HttpIdentitySessionPort(
            base_url="https://identity.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap-secret",
            audience="aifamily-mobile",
            client=client,
        )
        verified = await port.introspect(access_token="opaque-access-token")

    assert seen == {
        "path": "/v1/identity/sessions/introspect",
        "session": "opaque-access-token",
    }
    assert verified.session_id == "session-verified"
    assert verified.family_id == "family-1"


@pytest.mark.anyio
async def test_session_port_rejects_expired_or_malformed_identity_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_session_body(
                expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = HttpIdentitySessionPort(
            base_url="https://identity.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap",
            audience="aifamily-mobile",
            client=client,
        )
        with pytest.raises(IdentitySessionError, match="SESSION_RESPONSE_EXPIRED"):
            await port.rotate(access_token="old")


@pytest.mark.anyio
async def test_session_port_fails_closed_for_missing_bootstrap_and_client_config_conflict() -> None:
    with pytest.raises(IdentitySessionError, match="SESSION_MTLS_CLIENT_CONFLICT"):
        HttpIdentitySessionPort(
            base_url="https://identity.example.invalid",
            bootstrap_token_provider=lambda: "bootstrap",
            audience="aifamily-mobile",
            client=httpx.AsyncClient(),
            client_config=object(),  # type: ignore[arg-type]
        )

    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    async with httpx.AsyncClient(transport=transport) as client:
        port = HttpIdentitySessionPort(
            base_url="https://identity.example.invalid",
            bootstrap_token_provider=lambda: "",
            audience="aifamily-mobile",
            client=client,
        )
        with pytest.raises(IdentitySessionError, match="SESSION_BOOTSTRAP_REQUIRED"):
            await port.rotate(access_token="old")

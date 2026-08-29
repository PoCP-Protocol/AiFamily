"""The real adapter's code path, driven end to end without a network or a key.

`httpx.MockTransport` intercepts at the transport layer, so everything above it —
URL construction, headers, request body, status-code classification, envelope
parsing, error mapping — is the same code a production call would run. That is what
"a real provider adapter with a complete code path" has to mean; a hand-rolled
stub of the adapter's own interface would prove only that the stub works.

Its registry entry is deliberately non-callable (`sub_delegates=None`), so these
tests exercise the adapter directly rather than through `ModelGateway`. That
separation is honest: the adapter is technically validated, and technically
validated is not approved.
"""

from __future__ import annotations

import json

import httpx
import pytest

from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.providers.openai_compatible import (
    OpenAICompatibleProvider,
    build_openai_compatible_provider,
)
from tests.intelligence.model_gateway.test_fail_closed import make_request

VALID_ENVELOPE = {
    "model": "test-model-served",
    "choices": [{"message": {"content": '{"headline": "h", "hypotheses": ["a"]}'}}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}


def provider_with(handler) -> OpenAICompatibleProvider:  # type: ignore[no-untyped-def]
    return OpenAICompatibleProvider(
        provider_id="openai-compatible-unassessed",
        base_url="https://vendor.example.invalid/v1",
        api_key="test-key-not-real",
        model="test-model",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


class TestRequestConstruction:
    async def test_posts_to_chat_completions_with_bearer_auth(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=VALID_ENVELOPE)

        await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert seen["url"] == "https://vendor.example.invalid/v1/chat/completions"
        assert seen["auth"] == "Bearer test-key-not-real"

    async def test_request_carries_versions_and_schema_for_auditability(self) -> None:
        """The version identifiers travel in the prompt as well as in provenance, so
        a provider-side request capture is self-describing during an audit."""
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=VALID_ENVELOPE)

        await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        body = seen["body"]
        assert isinstance(body, dict)
        system = body["messages"][0]["content"]
        assert "prompt_version=v3" in system
        assert "schema_version=s1" in system
        assert "use_case=assessment_interpretation" in system
        assert body["response_format"] == {"type": "json_object"}

    async def test_returns_reported_model_and_token_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=VALID_ENVELOPE)

        response = await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert response.model == "test-model-served"
        assert response.token_usage is not None
        assert response.token_usage.total_tokens == 18

    async def test_adapter_returns_raw_text_and_does_not_parse_it(self) -> None:
        """Parsing and validation belong to the gateway, applied uniformly to every
        adapter (the R10 discipline point)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=VALID_ENVELOPE)

        response = await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert isinstance(response.text, str)
        assert response.text == '{"headline": "h", "hypotheses": ["a"]}'


class TestFailureMapping:
    @pytest.mark.parametrize(
        ("status", "expected_kind"),
        [
            (400, "PROVIDER_4XX"),
            (401, "PROVIDER_4XX"),
            (429, "PROVIDER_4XX"),
            (503, "PROVIDER_5XX"),
        ],
    )
    async def test_http_errors_map_to_failure_kinds(
        self, status: int, expected_kind: str
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": "nope"})

        with pytest.raises(ModelGatewayError) as excinfo:
            await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert excinfo.value.kind == expected_kind
        assert excinfo.value.status_code == status

    async def test_timeout_maps_to_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow", request=request)

        with pytest.raises(ModelGatewayError) as excinfo:
            await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert excinfo.value.kind == "TIMEOUT"

    async def test_transport_failure_maps_to_network_error_without_leaking_the_message(
        self,
    ) -> None:
        """httpx error strings can include the URL and body fragments, and this
        adapter's bodies contain family data — so only the exception class name is
        propagated."""
        secret = "child-name-Xiaoming"

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"failed while sending {secret}", request=request)

        with pytest.raises(ModelGatewayError) as excinfo:
            await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert excinfo.value.kind == "NETWORK_ERROR"
        assert secret not in str(excinfo.value)

    async def test_non_json_envelope_maps_to_invalid_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>gateway error page</html>")

        with pytest.raises(ModelGatewayError) as excinfo:
            await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert excinfo.value.kind == "INVALID_JSON"

    @pytest.mark.parametrize(
        "envelope",
        [
            {"model": "m", "choices": []},
            {"model": "m"},
            {"model": "m", "choices": [{"message": {"content": ""}}]},
            {"model": "m", "choices": [{"message": {}}]},
        ],
    )
    async def test_empty_or_missing_content_maps_to_invalid_json(
        self, envelope: dict
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=envelope)

        with pytest.raises(ModelGatewayError) as excinfo:
            await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert excinfo.value.kind == "INVALID_JSON"


class TestCredentialHandling:
    def test_missing_credentials_raise_rather_than_degrading_to_a_fake(self) -> None:
        """The source repository's `createAiGatewayFromEnv` returned
        `new FakeAiGateway()` whenever real settings were absent, meaning a
        production misconfiguration would silently serve canned output a caller
        could not distinguish from a model answer. That is R5's synthetic-on-a-
        production-route failure, and it is not reproduced."""
        with pytest.raises(ModelGatewayError) as excinfo:
            build_openai_compatible_provider(
                provider_id="openai-compatible-unassessed",
                model="m",
                base_url_env_var="AIFAMILY_TEST_BASE_URL",
                credential_env_var="AIFAMILY_TEST_API_KEY",
                env={},
            )
        assert excinfo.value.kind == "CREDENTIAL_MISSING"

    def test_partial_configuration_also_fails(self) -> None:
        with pytest.raises(ModelGatewayError) as excinfo:
            build_openai_compatible_provider(
                provider_id="openai-compatible-unassessed",
                model="m",
                base_url_env_var="AIFAMILY_TEST_BASE_URL",
                credential_env_var="AIFAMILY_TEST_API_KEY",
                env={"AIFAMILY_TEST_BASE_URL": "https://vendor.example.invalid/v1"},
            )
        assert "AIFAMILY_TEST_API_KEY" in excinfo.value.message

    def test_factory_builds_from_an_injected_environment(self) -> None:
        provider = build_openai_compatible_provider(
            provider_id="openai-compatible-unassessed",
            model="m",
            base_url_env_var="AIFAMILY_TEST_BASE_URL",
            credential_env_var="AIFAMILY_TEST_API_KEY",
            env={
                "AIFAMILY_TEST_BASE_URL": "https://vendor.example.invalid/v1",
                "AIFAMILY_TEST_API_KEY": "k",
            },
        )
        assert provider.provider_id == "openai-compatible-unassessed"

    async def test_the_api_key_never_appears_in_a_provider_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=VALID_ENVELOPE)

        response = await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert "test-key-not-real" not in repr(response)

    async def test_the_api_key_never_appears_in_an_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "bad key"})

        with pytest.raises(ModelGatewayError) as excinfo:
            await provider_with(handler).invoke(make_request(), timeout_seconds=5.0)
        assert "test-key-not-real" not in str(excinfo.value)

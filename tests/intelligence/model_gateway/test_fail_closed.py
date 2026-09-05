"""Fail-closed behaviour, observed rather than assumed.

`AI_NATIVE_PRINCIPLES.md` §5 and R14 make the same point from two directions: a
guarantee nobody has watched fail is not a guarantee. So every failure mode the
gateway claims to handle is provoked here, and each assertion checks two things —
that the call raised, and that nothing resembling a model answer came back.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.intelligence.model_gateway.attempts import InMemoryAttemptSink
from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import GATEWAY_POLICY, ModelGateway
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider

SCHEMA = {
    "type": "object",
    "required": ["headline", "hypotheses"],
    "properties": {
        "headline": {"type": "string"},
        "hypotheses": {"type": "array", "items": {"type": "string"}},
    },
}

VALID_OUTPUT = {"headline": "morning routine friction", "hypotheses": ["sleep debt"]}


def make_request(**overrides: object) -> StructuredRequest:
    base: dict[str, object] = {
        "use_case": "assessment_interpretation",
        "prompt_version": "v3",
        "schema_version": "s1",
        "data_class": "SYNTHETIC",
        "payload": {"answers": [1, 2, 3]},
        "output_schema": SCHEMA,
        "context_snapshot_ref": "ctx-0001",
        "request_id": "req-1",
        "session_id": "sess-1",
        "prompt_execution_plan": PromptExecutionPlan(
            prompt_ref="assessment_interpretation",
            prompt_version="v3",
            template="Use the reviewed assessment interpretation instructions.",
            system_policy_ref="family-safety.v1",
            safety_policy_version="family-safety.v1",
            knowledge_refs=("assessment-knowledge.v1",),
            asset_digest="a" * 64,
            system_policy="Only produce a reviewed draft.",
            system_policy_digest="b" * 64,
            knowledge_materials=(
                KnowledgeExecutionPayload(
                    knowledge_ref="assessment-knowledge.v1",
                    content="Reviewed assessment guidance.",
                    source_ref="source:test",
                    license_ref="license:test",
                    evidence_level="E3",
                    content_digest="c" * 64,
                ),
            ),
            material_digest="d" * 64,
        ),
    }
    base.update(overrides)
    return StructuredRequest(**base)  # type: ignore[arg-type]


def fake_record(provider_id: str = "fake-deterministic", **overrides: object) -> ProviderRecord:
    base: dict[str, object] = {
        "provider_id": provider_id,
        "vendor": "aifamily-internal",
        "model": "fake-deterministic",
        "model_version": "1.0.0",
        "status": "INTERNAL_APPROVED",
        "approved_environments": ("test",),
        "sub_delegates": False,
        "security_assessment_ref": "N/A",
        "processing_agreement_ref": "N/A",
        "deletion_on_termination_committed": True,
        "timeout_seconds": 5.0,
    }
    base.update(overrides)
    return ProviderRecord(**base)  # type: ignore[arg-type]


def build(provider: FakeProvider, **kwargs: object) -> ModelGateway:
    sink = kwargs.pop("attempt_sink", None) or InMemoryAttemptSink()
    records = kwargs.pop("records", None) or [fake_record(provider.provider_id)]
    return ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry(records),  # type: ignore[arg-type]
        attempt_sink=sink,
        **kwargs,  # type: ignore[arg-type]
    )


class TestHappyPathExistsFirst:
    """Without this, every fail-closed test below could pass on a gateway that
    simply never succeeds."""

    async def test_valid_response_yields_a_draft(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        assert draft.output == VALID_OUTPUT
        assert draft.status == "DRAFT"


class TestTimeout:
    async def test_slow_provider_raises_timeout(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT}, delay_seconds=5.0)
        gateway = build(provider, records=[fake_record(timeout_seconds=0.05)])
        with pytest.raises(ModelGatewayError) as excinfo:
            await gateway.generate_structured(make_request(), provider_id="fake-deterministic")
        assert excinfo.value.kind == "TIMEOUT"

    async def test_timeout_is_enforced_by_the_gateway_not_only_the_adapter(self) -> None:
        """An adapter that ignores its `timeout_seconds` argument must still be cut off.

        The fake here sleeps for far longer than the deadline while being handed
        the deadline it declines to honour — the same situation as a third-party
        adapter with a transport bug. The outer `asyncio.wait_for` is what has to
        fire.
        """

        class IgnoresTimeout(FakeProvider):
            async def invoke(self, request, *, timeout_seconds):  # type: ignore[no-untyped-def]
                await asyncio.sleep(5.0)
                raise AssertionError("gateway should have cancelled this attempt")

        gateway = build(IgnoresTimeout(), records=[fake_record(timeout_seconds=0.05)])
        with pytest.raises(ModelGatewayError) as excinfo:
            await gateway.generate_structured(make_request(), provider_id="fake-deterministic")
        assert excinfo.value.kind == "TIMEOUT"

    async def test_timed_out_attempt_is_recorded_as_a_failure_not_lost(self) -> None:
        """The whole reason `begin()` precedes the call: a timeout must leave a trace."""
        sink = InMemoryAttemptSink()
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT}, delay_seconds=5.0)
        gateway = build(provider, records=[fake_record(timeout_seconds=0.05)], attempt_sink=sink)
        with pytest.raises(ModelGatewayError):
            await gateway.generate_structured(make_request(), provider_id="fake-deterministic")
        attempts = sink.all_attempts()
        assert len(attempts) == 1
        assert attempts[0].status == "FAILURE"
        assert attempts[0].failure_kind == "TIMEOUT"
        assert not sink.unaccounted_attempts()


class TestMalformedResponse:
    async def test_non_json_response_raises_invalid_json(self) -> None:
        provider = FakeProvider(
            raw_text_by_use_case={"assessment_interpretation": "I think your child is fine."}
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert excinfo.value.kind == "INVALID_JSON"

    async def test_raw_model_text_is_never_returned_or_embedded_in_the_error(self) -> None:
        """The specific degradation R9 forbids: prose reaching a caller as if it
        were a structured recommendation."""
        prose = "Your child shows signs of oppositional defiant disorder."
        provider = FakeProvider(raw_text_by_use_case={"assessment_interpretation": prose})
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert prose not in str(excinfo.value)
        assert "oppositional" not in str(excinfo.value)

    async def test_schema_violating_json_raises_schema_invalid(self) -> None:
        provider = FakeProvider({"assessment_interpretation": {"headline": "only this"}})
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert excinfo.value.kind == "SCHEMA_INVALID"
        assert "hypotheses" in excinfo.value.message

    async def test_wrong_element_type_inside_an_array_is_caught(self) -> None:
        provider = FakeProvider(
            {"assessment_interpretation": {"headline": "x", "hypotheses": [1, 2]}}
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert excinfo.value.kind == "SCHEMA_INVALID"

    async def test_empty_object_from_an_unconfigured_provider_is_not_special_cased(self) -> None:
        provider = FakeProvider({})
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert excinfo.value.kind == "SCHEMA_INVALID"

    async def test_markdown_fenced_json_is_accepted_without_altering_content(self) -> None:
        """Tolerating a fence is a formatting concession, not a content one."""
        provider = FakeProvider(
            raw_text_by_use_case={
                "assessment_interpretation": (
                    '```json\n{"headline": "h", "hypotheses": ["a"]}\n```'
                )
            }
        )
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        assert draft.output == {"headline": "h", "hypotheses": ["a"]}


class TestUnregisteredAndUnadmittedProviders:
    async def test_wiring_an_unregistered_provider_fails_at_construction(self) -> None:
        """Surfacing at startup rather than on the first family request."""
        provider = FakeProvider(provider_id="ghost-vendor")
        with pytest.raises(ModelGatewayError) as excinfo:
            ModelGateway(
                {"ghost-vendor": provider},
                environment="test",
                registry=ProviderRegistry([fake_record()]),
            )
        assert excinfo.value.kind == "POLICY_REJECTED"

    async def test_calling_an_unregistered_provider_id_is_rejected(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider).generate_structured(
                make_request(), provider_id="never-registered"
            )
        assert excinfo.value.kind == "POLICY_REJECTED"

    async def test_rejected_admission_never_reaches_the_provider(self) -> None:
        """Proves admission runs *before* the call, not alongside it.

        Asserting that the provider recorded no invocation is the only way to
        distinguish "refused in time" from "refused after the payload left".
        """
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        gateway = build(provider)
        with pytest.raises(ModelGatewayError):
            await gateway.generate_structured(
                make_request(data_class="MINOR_PERSONAL_DATA"),
                provider_id="fake-deterministic",
            )
        assert provider.invocations == []

    async def test_rejected_admission_records_no_attempt(self) -> None:
        """No outbound attempt happened, so the ledger must not claim one."""
        sink = InMemoryAttemptSink()
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        gateway = build(provider, attempt_sink=sink)
        with pytest.raises(ModelGatewayError):
            await gateway.generate_structured(
                make_request(data_class="FAMILY_PRIVATE_TEXT"),
                provider_id="fake-deterministic",
            )
        assert sink.all_attempts() == ()

    async def test_gateway_with_no_wired_providers_rejects_everything(self) -> None:
        """The default posture of this repository today."""
        gateway = ModelGateway({}, environment="test", registry=ProviderRegistry([fake_record()]))
        with pytest.raises(ModelGatewayError) as excinfo:
            await gateway.generate_structured(make_request(), provider_id="fake-deterministic")
        assert excinfo.value.kind == "POLICY_REJECTED"


class TestNoSilentDegradation:
    @pytest.mark.parametrize(
        "kind", ["PROVIDER_4XX", "PROVIDER_5XX", "NETWORK_ERROR", "CREDENTIAL_MISSING"]
    )
    async def test_every_provider_failure_kind_propagates_unchanged(self, kind: str) -> None:
        """No failure kind is quietly converted into a usable-looking result."""
        provider = FakeProvider(fail_with=kind)  # type: ignore[arg-type]
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert excinfo.value.kind == kind

    async def test_an_adapter_leaking_a_foreign_exception_is_mapped_not_propagated(self) -> None:
        """A raw vendor exception can carry the request payload in its message,
        and this gateway's payloads contain family data."""
        secret = "child-name-Xiaoming"

        class LeakyAdapter(FakeProvider):
            async def invoke(self, request, *, timeout_seconds):  # type: ignore[no-untyped-def]
                raise ValueError(f"vendor blew up while processing {secret}")

        with pytest.raises(ModelGatewayError) as excinfo:
            await build(LeakyAdapter()).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert excinfo.value.kind == "NETWORK_ERROR"
        assert secret not in str(excinfo.value)

    async def test_a_broken_ledger_does_not_mask_the_provider_outcome(self) -> None:
        """Losing an audit row is bad; reporting the wrong failure reason is worse."""

        class BrokenSink(InMemoryAttemptSink):
            def begin(self, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("ledger down")

            def finish(self, attempt_id, outcome):  # type: ignore[no-untyped-def]
                raise RuntimeError("ledger down")

        provider = FakeProvider(fail_with="PROVIDER_5XX")
        with pytest.raises(ModelGatewayError) as excinfo:
            await build(provider, attempt_sink=BrokenSink()).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert excinfo.value.kind == "PROVIDER_5XX"

    async def test_a_broken_ledger_does_not_block_a_successful_call(self) -> None:
        class BrokenSink(InMemoryAttemptSink):
            def begin(self, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("ledger down")

        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        draft = await build(provider, attempt_sink=BrokenSink()).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        assert draft.output == VALID_OUTPUT


class TestPolicyIsDocumentationNotMechanism:
    def test_declared_policy_records_retry_zero(self) -> None:
        assert GATEWAY_POLICY["automatic_retry"] == 0
        assert GATEWAY_POLICY["on_failure"] == "fail_closed"
        assert GATEWAY_POLICY["schema_failure_returns_raw_text"] is False

    def test_policy_mapping_cannot_be_mutated_at_runtime(self) -> None:
        with pytest.raises(TypeError):
            GATEWAY_POLICY["automatic_retry"] = 3  # type: ignore[index]

    async def test_retry_zero_is_the_actual_behaviour_not_only_the_declaration(self) -> None:
        """R14 in one test: the constant above is checked against reality.

        The source repository's policy constant said `business_module_direct_
        provider_call: 'forbidden'` while a business service called a provider
        directly. Counting invocations is how that class of gap is closed here.
        """
        provider = FakeProvider(fail_with="PROVIDER_5XX")
        with pytest.raises(ModelGatewayError):
            await build(provider).generate_structured(
                make_request(), provider_id="fake-deterministic"
            )
        assert len(provider.invocations) == 1, (
            "the gateway retried a failed call; GATEWAY_POLICY declares "
            "automatic_retry=0 and the code must agree with it"
        )

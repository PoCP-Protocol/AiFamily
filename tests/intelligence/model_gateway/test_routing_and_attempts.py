"""Routing bounds, and the attempt ledger's ordering guarantee.

Routing is the one place where "try another provider" is permitted, and it is also
the place where 不得转委托 could be defeated by accident — falling back to a second
vendor is, legally, a second delegated-processing relationship rather than a retry.
So these tests pin both halves: it advances only for infrastructure failures, and
every candidate is admitted on its own merits.
"""

from __future__ import annotations

import pytest

from backend.intelligence.model_gateway.attempts import InMemoryAttemptSink
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.model_gateway.routing import RoutingModelGateway
from tests.intelligence.model_gateway.test_fail_closed import (
    VALID_OUTPUT,
    fake_record,
    make_request,
)


def two_provider_gateway(
    first: FakeProvider,
    second: FakeProvider,
    *,
    sink: InMemoryAttemptSink | None = None,
    second_environments: tuple[str, ...] = ("test",),
) -> ModelGateway:
    return ModelGateway(
        {first.provider_id: first, second.provider_id: second},
        environment="test",
        registry=ProviderRegistry(
            [
                fake_record(first.provider_id),
                fake_record(second.provider_id, approved_environments=second_environments),
            ]
        ),
        attempt_sink=sink or InMemoryAttemptSink(),
    )


class TestRoutingAdvancesOnlyForInfrastructureFailures:
    @pytest.mark.parametrize("kind", ["TIMEOUT", "NETWORK_ERROR", "PROVIDER_5XX"])
    async def test_infrastructure_failure_moves_to_the_next_provider(
        self, kind: str
    ) -> None:
        first = FakeProvider(fail_with=kind, provider_id="p-first")  # type: ignore[arg-type]
        second = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-second"
        )
        routing = RoutingModelGateway(
            two_provider_gateway(first, second), ["p-first", "p-second"]
        )
        draft = await routing.generate_structured(make_request())
        assert draft.output == VALID_OUTPUT
        assert draft.provenance.provider_id == "p-second"

    @pytest.mark.parametrize("kind", ["PROVIDER_4XX", "CREDENTIAL_MISSING"])
    async def test_non_infrastructure_failure_fails_closed_immediately(
        self, kind: str
    ) -> None:
        first = FakeProvider(fail_with=kind, provider_id="p-first")  # type: ignore[arg-type]
        second = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-second"
        )
        routing = RoutingModelGateway(
            two_provider_gateway(first, second), ["p-first", "p-second"]
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            await routing.generate_structured(make_request())
        assert excinfo.value.kind == kind
        assert second.invocations == [], "a 4xx must not be retried against another vendor"

    async def test_malformed_output_never_causes_a_second_vendor_to_be_asked(self) -> None:
        """The R9 line. Asking vendor B the same question because vendor A returned
        unparseable text is sampling until something looks like an answer, and the
        result would be indistinguishable to the caller from a well-grounded one.
        """
        first = FakeProvider(
            raw_text_by_use_case={"assessment_interpretation": "just some prose"},
            provider_id="p-first",
        )
        second = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-second"
        )
        routing = RoutingModelGateway(
            two_provider_gateway(first, second), ["p-first", "p-second"]
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            await routing.generate_structured(make_request())
        assert excinfo.value.kind == "INVALID_JSON"
        assert second.invocations == []

    async def test_schema_failure_never_causes_a_second_vendor_to_be_asked(self) -> None:
        first = FakeProvider(
            {"assessment_interpretation": {"headline": "incomplete"}}, provider_id="p-first"
        )
        second = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-second"
        )
        routing = RoutingModelGateway(
            two_provider_gateway(first, second), ["p-first", "p-second"]
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            await routing.generate_structured(make_request())
        assert excinfo.value.kind == "SCHEMA_INVALID"
        assert second.invocations == []

    async def test_last_provider_failing_raises_rather_than_returning_nothing(self) -> None:
        first = FakeProvider(fail_with="PROVIDER_5XX", provider_id="p-first")
        second = FakeProvider(fail_with="PROVIDER_5XX", provider_id="p-second")
        routing = RoutingModelGateway(
            two_provider_gateway(first, second), ["p-first", "p-second"]
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            await routing.generate_structured(make_request())
        assert excinfo.value.kind == "PROVIDER_5XX"

    async def test_empty_provider_order_is_refused(self) -> None:
        first = FakeProvider(provider_id="p-first")
        second = FakeProvider(provider_id="p-second")
        with pytest.raises(ValueError):
            RoutingModelGateway(two_provider_gateway(first, second), [])


class TestRoutingCannotBypassAdmission:
    async def test_each_candidate_is_admitted_independently(self) -> None:
        """Fallback must not smuggle a payload to a provider that was not approved
        for this environment. §16 duties attach per processor."""
        first = FakeProvider(fail_with="PROVIDER_5XX", provider_id="p-first")
        second = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-second"
        )
        gateway = two_provider_gateway(
            first, second, second_environments=("some-other-environment",)
        )
        routing = RoutingModelGateway(gateway, ["p-first", "p-second"])
        with pytest.raises(ModelGatewayError) as excinfo:
            await routing.generate_structured(make_request())
        assert excinfo.value.kind == "POLICY_REJECTED"
        assert second.invocations == []

    async def test_data_class_admission_applies_to_the_fallback_too(self) -> None:
        first = FakeProvider(fail_with="TIMEOUT", provider_id="p-first")
        second = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-second"
        )
        routing = RoutingModelGateway(
            two_provider_gateway(first, second), ["p-first", "p-second"]
        )
        with pytest.raises(ModelGatewayError) as excinfo:
            await routing.generate_structured(make_request(data_class="MINOR_PERSONAL_DATA"))
        assert excinfo.value.kind == "POLICY_REJECTED"
        assert first.invocations == []
        assert second.invocations == []


class TestAttemptLedger:
    async def test_every_routed_attempt_is_recorded_with_its_sequence(self) -> None:
        """The ledger must show the whole chain, not only whichever provider
        answered — otherwise an audit cannot tell how many processors saw the
        payload, which is the §16 question."""
        sink = InMemoryAttemptSink()
        first = FakeProvider(fail_with="PROVIDER_5XX", provider_id="p-first")
        second = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-second"
        )
        routing = RoutingModelGateway(
            two_provider_gateway(first, second, sink=sink), ["p-first", "p-second"]
        )
        await routing.generate_structured(make_request())
        attempts = sink.all_attempts()
        assert [(a.provider_id, a.route_sequence, a.status) for a in attempts] == [
            ("p-first", 0, "FAILURE"),
            ("p-second", 1, "SUCCESS"),
        ]

    async def test_attempt_records_the_data_class_that_was_sent(self) -> None:
        """"Which data class went to which provider, when" cannot be reconstructed
        from the vendor's logs afterwards, so it is recorded here."""
        sink = InMemoryAttemptSink()
        provider = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT}, provider_id="p-first"
        )
        gateway = ModelGateway(
            {"p-first": provider},
            environment="test",
            registry=ProviderRegistry([fake_record("p-first")]),
            attempt_sink=sink,
        )
        await gateway.generate_structured(make_request(), provider_id="p-first")
        record = sink.all_attempts()[0]
        assert record.data_class == "SYNTHETIC"
        assert record.environment == "test"
        assert record.use_case == "assessment_interpretation"
        assert record.request_id == "req-1"
        assert record.session_id == "sess-1"

    async def test_successful_attempt_records_the_model_that_answered(self) -> None:
        sink = InMemoryAttemptSink()
        provider = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT},
            provider_id="p-first",
            model="served-model",
            model_version="9",
        )
        gateway = ModelGateway(
            {"p-first": provider},
            environment="test",
            registry=ProviderRegistry([fake_record("p-first")]),
            attempt_sink=sink,
        )
        await gateway.generate_structured(make_request(), provider_id="p-first")
        record = sink.all_attempts()[0]
        assert record.model == "served-model"
        assert record.model_version == "9"
        assert record.latency_ms is not None

    async def test_schema_failure_is_recorded_as_a_failed_attempt(self) -> None:
        """An attempt that reached the provider and produced unusable output is
        still a delegated-processing event and must appear in the ledger."""
        sink = InMemoryAttemptSink()
        provider = FakeProvider(
            {"assessment_interpretation": {"headline": "incomplete"}}, provider_id="p-first"
        )
        gateway = ModelGateway(
            {"p-first": provider},
            environment="test",
            registry=ProviderRegistry([fake_record("p-first")]),
            attempt_sink=sink,
        )
        with pytest.raises(ModelGatewayError):
            await gateway.generate_structured(make_request(), provider_id="p-first")
        record = sink.all_attempts()[0]
        assert record.status == "FAILURE"
        assert record.failure_kind == "SCHEMA_INVALID"
        assert record.model == "fake-deterministic", (
            "the provider did answer, so the ledger should say which model did"
        )

    def test_an_unfinished_attempt_is_visible_as_unaccounted(self) -> None:
        """The reason `begin()` runs before the call: a record stuck in STARTED is
        itself the finding — an outbound attempt was made and never accounted for.
        """
        sink = InMemoryAttemptSink()
        sink.begin(
            provider_id="p-first",
            use_case="u",
            data_class="SYNTHETIC",
            environment="test",
            route_sequence=0,
            request_id=None,
            session_id=None,
        )
        assert len(sink.unaccounted_attempts()) == 1
        assert sink.all_attempts()[0].is_unaccounted is True

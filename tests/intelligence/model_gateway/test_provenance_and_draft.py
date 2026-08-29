"""AI Provenance completeness, and the R9 shape of the output.

Provenance is not a logging nicety here. PIPL 第24条 gives an individual the right
to an explanation of an automated decision, and
`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §2 spells out the consequence:
recording model / model_version / prompt_version / context_snapshot / confidence is
强制. A draft carrying a half-filled provenance record is an unexplainable
recommendation about a family, so these tests treat a missing field as a defect
rather than untidiness.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    ModelDraft,
    PolicyContext,
    StructuredRequest,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import (
    VALID_OUTPUT,
    build,
    make_request,
)

REQUIRED_PROVENANCE_FIELDS = (
    "provider_id",
    "model",
    "model_version",
    "prompt_version",
    "context_snapshot_ref",
    "confidence",
    "latency_ms",
)
"""Verbatim from the T-06 acceptance criteria and COMPLIANCE_HARD_CONSTRAINTS §2.
`confidence` is present as a field even when its value is `None` — see below."""


class TestProvenanceCompleteness:
    async def test_every_required_field_is_present_on_a_real_draft(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT}, confidence=0.72)
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        present = {f.name for f in dataclasses.fields(draft.provenance)}
        missing = [name for name in REQUIRED_PROVENANCE_FIELDS if name not in present]
        assert not missing, f"provenance is missing mandated field(s): {missing}"

    async def test_identity_fields_carry_real_values_not_placeholders(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        p = draft.provenance
        assert p.provider_id == "fake-deterministic"
        assert p.model == "fake-deterministic"
        assert p.model_version == "1.0.0"
        assert p.prompt_version == "v3"
        assert p.schema_version == "s1"
        assert p.context_snapshot_ref == "ctx-0001"
        assert p.use_case == "assessment_interpretation"
        assert p.data_class == "SYNTHETIC"
        assert p.latency_ms >= 0

    async def test_latency_is_measured_not_defaulted(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT}, delay_seconds=0.05)
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        assert draft.provenance.latency_ms >= 40

    async def test_reported_model_wins_over_the_configured_one(self) -> None:
        """Vendors silently alias and upgrade models. Provenance must say what
        actually answered, otherwise the explanation describes a model that never
        ran."""
        provider = FakeProvider(
            {"assessment_interpretation": VALID_OUTPUT},
            model="vendor-actually-served-this",
            model_version="2026-08-01",
        )
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        assert draft.provenance.model == "vendor-actually-served-this"
        assert draft.provenance.model_version == "2026-08-01"

    @pytest.mark.parametrize(
        "field_name",
        [
            "provider_id",
            "model",
            "model_version",
            "prompt_version",
            "schema_version",
            "context_snapshot_ref",
            "use_case",
        ],
    )
    def test_provenance_cannot_be_constructed_with_a_blank_identity_field(
        self, field_name: str
    ) -> None:
        kwargs: dict[str, object] = {
            "provider_id": "p",
            "model": "m",
            "model_version": "1",
            "prompt_version": "v1",
            "schema_version": "s1",
            "context_snapshot_ref": "ctx",
            "latency_ms": 10,
            "data_class": "SYNTHETIC",
            "use_case": "u",
        }
        kwargs[field_name] = ""
        with pytest.raises(ValueError, match="incomplete"):
            AiProvenance(**kwargs)  # type: ignore[arg-type]

    def test_confidence_may_be_none_but_never_fabricated(self) -> None:
        """`None` honestly records "the provider reported no calibrated
        confidence". Inventing 0.9 would put a made-up number into a compliance
        record, so the field is nullable rather than defaulted to a plausible
        value."""
        p = AiProvenance(
            provider_id="p",
            model="m",
            model_version="1",
            prompt_version="v1",
            schema_version="s1",
            context_snapshot_ref="ctx",
            latency_ms=1,
            data_class="SYNTHETIC",
            use_case="u",
        )
        assert p.confidence is None

    def test_out_of_range_confidence_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            AiProvenance(
                provider_id="p",
                model="m",
                model_version="1",
                prompt_version="v1",
                schema_version="s1",
                context_snapshot_ref="ctx",
                latency_ms=1,
                data_class="SYNTHETIC",
                use_case="u",
                confidence=1.4,
            )

    def test_request_without_a_context_snapshot_ref_is_rejected(self) -> None:
        """Refused at the request boundary rather than producing an
        unexplainable draft later."""
        with pytest.raises(ValueError, match="context_snapshot_ref"):
            StructuredRequest(
                use_case="u",
                prompt_version="v1",
                schema_version="s1",
                data_class="SYNTHETIC",
                payload={},
                output_schema={"type": "object"},
                context_snapshot_ref="",
            )

    def test_request_without_an_output_schema_is_rejected(self) -> None:
        """No schema means no way to fail closed on a bad response — only the
        option of handing raw prose to the caller."""
        with pytest.raises(ValueError, match="output_schema"):
            StructuredRequest(
                use_case="u",
                prompt_version="v1",
                schema_version="s1",
                data_class="SYNTHETIC",
                payload={},
                output_schema={},
                context_snapshot_ref="ctx",
            )


class TestDraftIsNotABusinessEntity:
    """R9 / `AI_NATIVE_PRINCIPLES.md` §3.5 — `may_mutate_business_state = false`
    must be a fact about the runtime, not a sentence in a document."""

    async def test_gateway_output_is_a_draft(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        assert isinstance(draft, ModelDraft)
        assert draft.status == "DRAFT"
        assert draft.requires_human_confirmation is True

    async def test_may_mutate_business_state_is_false(self) -> None:
        provider = FakeProvider({"assessment_interpretation": VALID_OUTPUT})
        draft = await build(provider).generate_structured(
            make_request(), provider_id="fake-deterministic"
        )
        assert draft.may_mutate_business_state is False

    def test_may_mutate_business_state_cannot_be_set(self) -> None:
        """A read-only property, not a defaulted field. A field could be passed
        `True` at construction; this cannot.

        The exception type is left open (`AttributeError` for a plain property,
        `TypeError` from the frozen dataclass's `__setattr__`) because the property
        that matters is "assignment does not succeed", not which of the two
        mechanisms refuses first.
        """
        draft = ModelDraft(output={}, provenance=_provenance())
        with pytest.raises((AttributeError, TypeError)):
            draft.may_mutate_business_state = True  # type: ignore[misc]
        assert draft.may_mutate_business_state is False

    def test_dataclasses_replace_cannot_reach_it_either(self) -> None:
        """The loophole a `False`-defaulted frozen field would leave open."""
        draft = ModelDraft(output={}, provenance=_provenance())
        with pytest.raises(TypeError):
            dataclasses.replace(draft, may_mutate_business_state=True)  # type: ignore[call-arg]

    def test_draft_carries_no_business_status_vocabulary(self) -> None:
        """A draft has one legal status and no transition out of it. Promotion is a
        domain's Named Action with a human actor (R8/R9), never something the
        gateway's own type can express."""
        field_names = {f.name for f in dataclasses.fields(ModelDraft)}
        assert field_names == {"output", "provenance", "status"}
        draft = ModelDraft(output={}, provenance=_provenance())
        assert not [name for name in dir(draft) if "promote" in name or "approve" in name]

    def test_policy_context_flags_are_fixed(self) -> None:
        context = PolicyContext()
        assert context.human_confirmation_required is True
        assert context.may_mutate_business_state is False


def _provenance() -> AiProvenance:
    return AiProvenance(
        provider_id="p",
        model="m",
        model_version="1",
        prompt_version="v1",
        schema_version="s1",
        context_snapshot_ref="ctx",
        latency_ms=1,
        data_class="SYNTHETIC",
        use_case="u",
    )

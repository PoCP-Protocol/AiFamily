"""IBM ICA Model Gateway wiring — unit + gated livecheck."""

from __future__ import annotations

import os

import pytest

from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.ibm_ica_wiring import (
    IBM_ICA_DEFAULT_MODEL,
    IBM_ICA_LIVECHECK_ENVIRONMENT,
    IBM_ICA_MODEL_API_KEY_ENV_VAR,
    IBM_ICA_MODEL_BASE_URL_ENV_VAR,
    IBM_ICA_PROVIDER_ID,
    build_livecheck_ibm_ica_gateway,
    ibm_ica_credentials_available,
    ibm_ica_provider_record,
    ibm_ica_provider_registry,
)

SCHEMA = {
    "type": "object",
    "required": ["headline", "summary"],
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
    },
}


def test_ibm_ica_record_is_livecheck_only_and_blocks_regulated_data() -> None:
    record = ibm_ica_provider_record()
    assert record.provider_id == IBM_ICA_PROVIDER_ID
    assert record.model == IBM_ICA_DEFAULT_MODEL
    assert record.status == "INTERNAL_APPROVED"
    assert record.approved_environments == (IBM_ICA_LIVECHECK_ENVIRONMENT,)
    assert record.credential_env_var == IBM_ICA_MODEL_API_KEY_ENV_VAR
    assert record.base_url_env_var == IBM_ICA_MODEL_BASE_URL_ENV_VAR

    registry = ibm_ica_provider_registry()
    admitted = registry.admit(
        IBM_ICA_PROVIDER_ID,
        data_class="OPERATIONAL_TEXT",
        environment=IBM_ICA_LIVECHECK_ENVIRONMENT,
    )
    assert admitted.provider_id == IBM_ICA_PROVIDER_ID

    with pytest.raises(ModelGatewayError) as excinfo:
        registry.admit(
            IBM_ICA_PROVIDER_ID,
            data_class="OPERATIONAL_TEXT",
            environment="production",
        )
    assert excinfo.value.kind == "POLICY_REJECTED"

    with pytest.raises(ModelGatewayError) as excinfo:
        registry.admit(
            IBM_ICA_PROVIDER_ID,
            data_class="FAMILY_PRIVATE_TEXT",
            environment=IBM_ICA_LIVECHECK_ENVIRONMENT,
        )
    assert excinfo.value.kind == "POLICY_REJECTED"


def test_ibm_ica_credentials_available_requires_both_vars() -> None:
    assert not ibm_ica_credentials_available({})
    assert not ibm_ica_credentials_available({IBM_ICA_MODEL_API_KEY_ENV_VAR: "sk-x"})
    assert not ibm_ica_credentials_available(
        {IBM_ICA_MODEL_BASE_URL_ENV_VAR: "https://example.invalid/v1"}
    )
    assert ibm_ica_credentials_available(
        {
            IBM_ICA_MODEL_API_KEY_ENV_VAR: "sk-x",
            IBM_ICA_MODEL_BASE_URL_ENV_VAR: "https://example.invalid/v1",
        }
    )


def test_build_livecheck_gateway_fails_closed_without_credentials() -> None:
    with pytest.raises(ModelGatewayError) as excinfo:
        build_livecheck_ibm_ica_gateway(env={})
    assert excinfo.value.kind == "CREDENTIAL_MISSING"


def _livecheck_request() -> StructuredRequest:
    return StructuredRequest(
        use_case="ibm_ica_livecheck",
        prompt_version="v1",
        schema_version="s1",
        data_class="OPERATIONAL_TEXT",
        payload={"task": "ping"},
        output_schema=SCHEMA,
        context_snapshot_ref="ibm-ica-livecheck-ctx",
        request_id="ibm-ica-livecheck-req",
        session_id="ibm-ica-livecheck-sess",
        prompt_execution_plan=PromptExecutionPlan(
            prompt_ref="ibm_ica_livecheck",
            prompt_version="v1",
            template=(
                "Return JSON with keys headline and summary. "
                "headline must be exactly: ica-ok. "
                "summary must mention gpt-5.6-sol."
            ),
            system_policy_ref="ibm-ica-livecheck.v1",
            safety_policy_version="ibm-ica-livecheck.v1",
            knowledge_refs=("ibm-ica-livecheck.v1",),
            asset_digest="a" * 64,
            system_policy="Only produce the requested JSON object. No family data.",
            system_policy_digest="b" * 64,
            knowledge_materials=(
                KnowledgeExecutionPayload(
                    knowledge_ref="ibm-ica-livecheck.v1",
                    content="Operational livecheck only.",
                    source_ref="source:ibm-ica-livecheck",
                    license_ref="license:internal",
                    evidence_level="E3",
                    content_digest="c" * 64,
                ),
            ),
            material_digest="d" * 64,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not ibm_ica_credentials_available(),
    reason=(
        f"{IBM_ICA_MODEL_API_KEY_ENV_VAR} / {IBM_ICA_MODEL_BASE_URL_ENV_VAR} "
        "not set — gated IBM ICA real-model livecheck"
    ),
)
async def test_real_ibm_ica_gpt56_sol_via_model_gateway() -> None:
    gateway = build_livecheck_ibm_ica_gateway(env=os.environ, model="gpt-5.6-sol")
    draft = await gateway.generate_structured(
        _livecheck_request(),
        provider_id=IBM_ICA_PROVIDER_ID,
    )
    assert draft.provenance.provider_id == IBM_ICA_PROVIDER_ID
    assert "gpt-5.6" in (draft.provenance.model or "")
    assert draft.output["headline"] == "ica-ok"
    summary = str(draft.output["summary"]).lower().replace(" ", "")
    assert "gpt-5.6-sol" in summary or "gpt-5.6" in summary

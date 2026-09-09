"""IBM ICA (OpenAI-compatible) wiring for Model Gateway livecheck.

Follows the same gated pattern as `backend/apps/family_api/ai_coach_wiring.py`
for DeepSeek:

* Credentials come only from ``AIFAMILY_MODEL_API_KEY`` /
  ``AIFAMILY_MODEL_BASE_URL`` (R7 — Model Gateway reads them, domains do not).
* Provider is ``INTERNAL_APPROVED`` solely for ``internal_livecheck`` and may
  only receive ``OPERATIONAL_TEXT`` / ``SYNTHETIC`` (no family/minor data until
  《儿童个人信息网络保护规定》第16条 paperwork exists for this vendor path).
* Default served model is ``gpt-5.6-sol`` on IBM Consulting Assistants
  ``servicesessentials`` OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from backend.intelligence.model_gateway.gateway import ModelGateway, build_gateway
from backend.intelligence.model_gateway.provider_registry import (
    DEFAULT_PROVIDER_RECORDS,
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.base import ProviderAdapter
from backend.intelligence.model_gateway.providers.openai_compatible import (
    build_openai_compatible_provider,
)

IBM_ICA_PROVIDER_ID = "ibm-ica-gpt-56"
IBM_ICA_MODEL_API_KEY_ENV_VAR = "AIFAMILY_MODEL_API_KEY"
IBM_ICA_MODEL_BASE_URL_ENV_VAR = "AIFAMILY_MODEL_BASE_URL"
IBM_ICA_DEFAULT_MODEL = "gpt-5.6-sol"
IBM_ICA_LIVECHECK_ENVIRONMENT = "internal_livecheck"
IBM_ICA_DEFAULT_BASE_URL = "https://api.servicesessentials.ibm.com/v1"

_IBM_ICA_RECORD = ProviderRecord(
    provider_id=IBM_ICA_PROVIDER_ID,
    vendor="ibm-ica",
    model=IBM_ICA_DEFAULT_MODEL,
    model_version=IBM_ICA_DEFAULT_MODEL,
    status="INTERNAL_APPROVED",
    approved_environments=(IBM_ICA_LIVECHECK_ENVIRONMENT,),
    # No completed 第16条 assessment for IBM ICA as a delegated processor of
    # family/minor data yet — keep regulated classes closed.
    sub_delegates=None,
    minor_data_allowed=False,
    private_text_allowed=False,
    processing_region="unspecified",
    credential_env_var=IBM_ICA_MODEL_API_KEY_ENV_VAR,
    base_url_env_var=IBM_ICA_MODEL_BASE_URL_ENV_VAR,
    timeout_seconds=60.0,
    notes=(
        "IBM Consulting Assistants (ICA) OpenAI-compatible Chat Completions "
        "adapter for Model Gateway livecheck. Default model gpt-5.6-sol. "
        "sub_delegates is unestablished, so admit() rejects "
        "FAMILY_PRIVATE_TEXT/MINOR_PERSONAL_DATA under 第16条; callable only "
        "for OPERATIONAL_TEXT/SYNTHETIC in internal_livecheck."
    ),
)


def ibm_ica_provider_record() -> ProviderRecord:
    return _IBM_ICA_RECORD


def ibm_ica_provider_registry() -> ProviderRegistry:
    """Default registry plus the IBM ICA GPT-5.6 livecheck record."""

    return ProviderRegistry((*DEFAULT_PROVIDER_RECORDS, _IBM_ICA_RECORD))


def ibm_ica_credentials_available(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return bool(source.get(IBM_ICA_MODEL_BASE_URL_ENV_VAR)) and bool(
        source.get(IBM_ICA_MODEL_API_KEY_ENV_VAR)
    )


def build_livecheck_ibm_ica_gateway(
    *,
    env: dict[str, str] | None = None,
    model: str = IBM_ICA_DEFAULT_MODEL,
) -> ModelGateway:
    """Real IBM ICA-backed gateway for gated livecheck / operator verification.

    Raises ``ModelGatewayError("CREDENTIAL_MISSING", ...)`` when env vars are
    absent — prefer ``ibm_ica_credentials_available`` first in tests.
    """

    provider: ProviderAdapter = build_openai_compatible_provider(
        provider_id=IBM_ICA_PROVIDER_ID,
        model=model,
        base_url_env_var=IBM_ICA_MODEL_BASE_URL_ENV_VAR,
        credential_env_var=IBM_ICA_MODEL_API_KEY_ENV_VAR,
        env=env,
    )
    return build_gateway(
        environment=IBM_ICA_LIVECHECK_ENVIRONMENT,
        providers={IBM_ICA_PROVIDER_ID: provider},
        registry=ibm_ica_provider_registry(),
    )

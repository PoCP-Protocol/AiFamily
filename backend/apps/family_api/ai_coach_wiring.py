"""AI Coach provider wiring — dev/test FakeProvider vs. gated real DeepSeek.

Two callable providers exist:

* `"fake-deterministic"` — always callable in `test`/`development`, used for
  every automated test that does not require a real model. Its output is
  honestly synthetic (see `FakeProvider`'s own docstring): useful for proving
  the gateway/schema/provenance plumbing works, never useful as evidence that
  a real model produced Socratic guidance.

* `"deepseek-coach"` — a real `OpenAICompatibleProvider` against DeepSeek's
  Chat Completions endpoint, registered `INTERNAL_APPROVED` for the narrow
  `internal_livecheck` environment and `OPERATIONAL_TEXT` data class only.

  This repository has **no** completed 《儿童个人信息网络保护规定》第16条
  security assessment or processing agreement for DeepSeek — see
  `provider_registry.py`'s own `openai-compatible-unassessed` entry, which
  documents that gap and is deliberately left non-callable. Real family data
  (`FAMILY_PRIVATE_TEXT` / `MINOR_PERSONAL_DATA`) must not reach this
  provider until that legal work is done; nothing in this module authorises
  it to. `deepseek-coach` is scoped to `OPERATIONAL_TEXT` — a synthetic
  scenario used only to prove the real generative path works end-to-end
  (see `tests/intelligence/experience/test_family_ai_coach_real_model.py`) —
  and to the `internal_livecheck` environment, the same pattern the shipped
  registry already uses for exercising a real adapter without granting it
  production reach.
"""

from __future__ import annotations

import os

from backend.intelligence.model_gateway.gateway import ModelGateway, build_gateway
from backend.intelligence.model_gateway.provider_registry import (
    DEFAULT_PROVIDER_RECORDS,
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.base import ProviderAdapter
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.model_gateway.providers.openai_compatible import (
    build_openai_compatible_provider,
)

AI_COACH_DEEPSEEK_PROVIDER_ID = "deepseek-coach"
AI_COACH_MODEL_BASE_URL_ENV_VAR = "AI_COACH_MODEL_BASE_URL"
AI_COACH_MODEL_API_KEY_ENV_VAR = "AI_COACH_MODEL_API_KEY"
AI_COACH_DEEPSEEK_MODEL = "deepseek-chat"
AI_COACH_LIVECHECK_ENVIRONMENT = "internal_livecheck"

_DEEPSEEK_COACH_RECORD = ProviderRecord(
    provider_id=AI_COACH_DEEPSEEK_PROVIDER_ID,
    vendor="deepseek",
    model=AI_COACH_DEEPSEEK_MODEL,
    model_version=AI_COACH_DEEPSEEK_MODEL,
    status="INTERNAL_APPROVED",
    approved_environments=(AI_COACH_LIVECHECK_ENVIRONMENT,),
    # No completed 第16条 assessment exists for DeepSeek yet, so this record
    # must never claim minor/family-private rights (the constructor itself
    # would refuse that combination — see ProviderRecord.__post_init__).
    sub_delegates=None,
    minor_data_allowed=False,
    private_text_allowed=False,
    processing_region="unspecified",
    credential_env_var=AI_COACH_MODEL_API_KEY_ENV_VAR,
    base_url_env_var=AI_COACH_MODEL_BASE_URL_ENV_VAR,
    timeout_seconds=30.0,
    notes=(
        "Real DeepSeek OpenAI-compatible adapter for the AI Coach real-model "
        "livecheck only. sub_delegates is unestablished, so admit() rejects "
        "FAMILY_PRIVATE_TEXT/MINOR_PERSONAL_DATA for this provider under "
        "《儿童个人信息网络保护规定》第16条 exactly like the shipped "
        "openai-compatible-unassessed entry; it is callable only for "
        "OPERATIONAL_TEXT in internal_livecheck, which is the scope this "
        "capability's real-model verification test uses."
    ),
)


def ai_coach_provider_registry() -> ProviderRegistry:
    """The default registry plus the AI Coach's own DeepSeek record.

    Built from `DEFAULT_PROVIDER_RECORDS` rather than replacing the shipped
    registry, so `fake-deterministic` and the existing
    `openai-compatible-unassessed` livecheck record remain available to any
    other caller sharing this registry instance.
    """

    return ProviderRegistry((*DEFAULT_PROVIDER_RECORDS, _DEEPSEEK_COACH_RECORD))


def build_dev_ai_coach_gateway(*, environment: str = "development") -> ModelGateway:
    """FakeProvider-backed gateway for dev/test composition roots."""

    return build_gateway(
        environment=environment,
        providers={"fake-deterministic": FakeProvider(provider_id="fake-deterministic")},
        registry=ai_coach_provider_registry(),
    )


def deepseek_coach_credentials_available(env: dict[str, str] | None = None) -> bool:
    """True only when both AI Coach DeepSeek environment variables are set.

    Used by the gated real-model test to skip rather than fail when the
    operator has not supplied credentials — see
    `tests/intelligence/experience/test_family_ai_coach_real_model.py`.
    """

    source = os.environ if env is None else env
    return bool(source.get(AI_COACH_MODEL_BASE_URL_ENV_VAR)) and bool(
        source.get(AI_COACH_MODEL_API_KEY_ENV_VAR)
    )


def build_livecheck_deepseek_coach_gateway(
    *, env: dict[str, str] | None = None
) -> ModelGateway:
    """Real DeepSeek-backed gateway for the gated real-model verification test.

    Raises `ModelGatewayError("CREDENTIAL_MISSING", ...)` if the environment
    variables are absent — callers should check
    `deepseek_coach_credentials_available` first (the test does, via
    `pytest.mark.skipif`) rather than relying on this raising.
    """

    provider: ProviderAdapter = build_openai_compatible_provider(
        provider_id=AI_COACH_DEEPSEEK_PROVIDER_ID,
        model=AI_COACH_DEEPSEEK_MODEL,
        base_url_env_var=AI_COACH_MODEL_BASE_URL_ENV_VAR,
        credential_env_var=AI_COACH_MODEL_API_KEY_ENV_VAR,
        env=env,
    )
    return build_gateway(
        environment=AI_COACH_LIVECHECK_ENVIRONMENT,
        providers={AI_COACH_DEEPSEEK_PROVIDER_ID: provider},
        registry=ai_coach_provider_registry(),
    )

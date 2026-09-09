"""Development consent adapter exercises the same live fail-closed gate."""

import pytest

from backend.intelligence.agi_vertical_dev_wiring import (
    DevVerticalConsent,
    build_dev_vertical_family_growth_runtime,
)
from backend.intelligence.agi_vertical_runtime import VerticalRuntimeError


@pytest.mark.asyncio
async def test_dev_consent_revocation_takes_effect_before_next_generation() -> None:
    runtime = build_dev_vertical_family_growth_runtime(environment="test")
    consent = runtime._consent  # noqa: SLF001 - white-box proof of live adapter
    assert isinstance(consent, DevVerticalConsent)

    await runtime.run(
        family_need_id="need-1",
        path_id="path-1",
        run_id="run-1",
        family_id="family-a",
        knowledge_ref="vertical-growth.v1",
    )
    consent.revoke("family-a")
    with pytest.raises(VerticalRuntimeError, match="CONSENT_NOT_ACTIVE"):
        await runtime.run(
            family_need_id="need-2",
            path_id="path-2",
            run_id="run-2",
            family_id="family-a",
            knowledge_ref="vertical-growth.v1",
        )


def test_dev_consent_restore_is_explicit() -> None:
    consent = DevVerticalConsent()
    consent.revoke("family-a")
    consent.restore("family-a")
    assert "family-a" not in consent._revoked_families  # noqa: SLF001

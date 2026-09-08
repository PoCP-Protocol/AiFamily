from __future__ import annotations

import pytest

from backend.domains.family_need.application.vertical_agi_context import (
    read_vertical_agi_context,
)
from backend.domains.family_need.domain.value_objects import DataClass


class NeedRepository:
    async def get_need(self, *, tenant_id, family_id, need_id):
        class Context:
            consent_version = "consent-v1"
            subject_person_ids = ("child-1",)
            data_class = DataClass.MINOR_PERSONAL_DATA

        class Need:
            context = Context()
            need_id = "need-1"
            version = 3
            statement = "孩子很难开始作业"
            desired_outcome = "减少反复催促"
            category = type("Category", (), {"value": "EDUCATION"})()
            emotional_gate = type("Gate", (), {"value": "E0_WELCOME"})()

        return Need()


@pytest.mark.asyncio
async def test_reads_real_family_need_into_vertical_context_without_model_call():
    context = await read_vertical_agi_context(
        NeedRepository(),
        tenant_id="tenant-1",
        family_id="family-1",
        family_need_id="need-1",
    )
    assert context.values["need_statement"] == "孩子很难开始作业"
    assert context.values["family_need_id"] == "need-1"
    assert context.context_snapshot_ref.startswith("family-ai-coach-context:")
    assert context.consent_version == "consent-v1"

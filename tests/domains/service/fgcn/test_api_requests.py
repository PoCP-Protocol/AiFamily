from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.domains.service.fgcn.api.requests import AssignmentProposalRequest


def test_assignment_proposal_rejects_ai_as_service_provider() -> None:
    with pytest.raises(ValidationError):
        AssignmentProposalRequest(
            proposal_id="proposal-ai-provider",
            draft_id="draft-ai-provider",
            provenance_ref="model-draft:ai-provider",
            provider_id="ai-provider",
            assignee_kind="AI",
        )

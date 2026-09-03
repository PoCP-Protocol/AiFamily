"""Immutable prompt assets used by the governed AI runtime.

Prompt assets are configuration *data*, not executable instructions.  They are
kept in their own runtime package so callers can resolve a reviewed version
without importing a provider SDK or a business-domain repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PromptStatus = Literal["DRAFT", "REVIEW", "PUBLISHED", "RETIRED"]


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """One immutable prompt version.

    A version is content-addressed by ``(prompt_ref, version)``.  Updating a
    published prompt is intentionally impossible: create a new bundle and
    register it instead.  ``agent_id`` and ``use_case`` are mandatory because
    a prompt copied between agents is a policy bypass, even if its text is the
    same.
    """

    prompt_ref: str
    version: str
    use_case: str
    agent_id: str
    template: str
    system_policy_ref: str
    knowledge_refs: tuple[str, ...]
    input_contract_ref: str
    output_schema_ref: str
    safety_policy_version: str
    locale: str
    author: str
    reviewer: str | None = None
    status: PromptStatus = "DRAFT"
    effective_at: datetime | None = None
    retired_at: datetime | None = None
    change_reason: str = ""

    def __post_init__(self) -> None:
        required = (
            self.prompt_ref,
            self.version,
            self.use_case,
            self.agent_id,
            self.template,
            self.system_policy_ref,
            self.input_contract_ref,
            self.output_schema_ref,
            self.safety_policy_version,
            self.locale,
            self.author,
        )
        if not all(required):
            raise ValueError("PromptBundle identity, policy and content fields are required")
        if self.status not in {"DRAFT", "REVIEW", "PUBLISHED", "RETIRED"}:
            raise ValueError(f"unknown prompt status: {self.status}")
        refs = tuple(self.knowledge_refs)
        if any(not ref for ref in refs):
            raise ValueError("PromptBundle.knowledge_refs cannot contain blank references")
        object.__setattr__(self, "knowledge_refs", refs)
        if (
            self.retired_at is not None
            and self.effective_at is not None
            and self.retired_at <= self.effective_at
        ):
            raise ValueError("PromptBundle.retired_at must be after effective_at")
        if self.status == "PUBLISHED":
            if self.effective_at is None:
                raise ValueError("a published prompt requires effective_at")
            if not self.reviewer:
                raise ValueError("a published prompt requires reviewer")
        if self.status in {"REVIEW", "RETIRED"} and not self.change_reason:
            raise ValueError(f"{self.status.lower()} prompt requires change_reason")

    @property
    def prompt_text(self) -> str:
        """Compatibility name for callers that call the body ``prompt_text``."""

        return self.template

    @property
    def is_effective(self) -> bool:
        """Whether this version can be selected at its declared instant."""

        return self.status == "PUBLISHED" and self.effective_at is not None

    def effective_at_time(self, at: datetime) -> bool:
        """Return true only for an aware instant inside the publication window."""

        if at.tzinfo is None or self.effective_at is None or self.effective_at.tzinfo is None:
            return False
        if self.status != "PUBLISHED" or at < self.effective_at:
            return False
        return self.retired_at is None or at < self.retired_at


# Data architecture documents call the same object ``PromptVersion``.  Keep a
# type-level alias so provenance and registry callers can use either vocabulary
# without creating a second representation.
PromptVersion = PromptBundle

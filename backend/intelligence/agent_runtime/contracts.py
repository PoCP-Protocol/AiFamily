"""Provider-neutral contracts for the governed Agent Runtime.

The runtime owns orchestration metadata only.  It deliberately has no domain
repository and no provider SDK dependency: a model is reached through the
``StructuredGenerationPort`` defined here and implemented by Model Gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from backend.intelligence.model_gateway.contracts import (
    DataClass,
    ModelDraft,
    StructuredRequest,
)


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Static declaration of what an agent is allowed to do.

    Dynamic, family-scoped permissions belong to :class:`AgentAuthorization`;
    this object is the reviewed upper bound.  ``may_mutate_business_state`` is
    a property rather than a writable field so an Agent Runtime instance can
    never be configured to write canonical facts.
    """

    agent_id: str
    name: str
    allowed_skills: frozenset[str] = field(default_factory=frozenset)
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    allowed_use_cases: frozenset[str] = field(default_factory=frozenset)
    context_policy: str = ""
    safety_policy: str = ""
    human_handoff_policy: str = ""
    budget_policy: str = ""

    def __post_init__(self) -> None:
        if not self.agent_id or not self.name:
            raise ValueError("AgentDefinition.agent_id and name are required")
        if not self.context_policy or not self.safety_policy:
            raise ValueError("AgentDefinition context_policy and safety_policy are required")
        if not self.human_handoff_policy or not self.budget_policy:
            raise ValueError(
                "AgentDefinition human_handoff_policy and budget_policy are required"
            )

    @property
    def may_mutate_business_state(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class AgentAuthorization:
    """A revocable, time-bounded authorization for one agent and one scope."""

    authorization_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    allowed_use_cases: frozenset[str]
    allowed_tools: frozenset[str]
    issued_by: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    budget: AuthorizationBudget
    policy_version: str
    reason: str
    audit_ref: str

    def __post_init__(self) -> None:
        required = (
            self.authorization_id,
            self.agent_id,
            self.tenant_id,
            self.family_id,
            self.issued_by,
            self.policy_version,
            self.reason,
            self.audit_ref,
        )
        if not all(required):
            raise ValueError("AgentAuthorization identity, policy and audit fields are required")
        if self.expires_at <= self.issued_at:
            raise ValueError("AgentAuthorization.expires_at must be after issued_at")
        if self.revoked_at is not None and self.revoked_at < self.issued_at:
            raise ValueError("AgentAuthorization.revoked_at cannot precede issued_at")

    def is_valid_at(self, now: datetime) -> bool:
        """Return validity using a timezone-aware instant; invalid clocks deny."""

        if now.tzinfo is None or self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            return False
        return self.issued_at <= now < self.expires_at and (
            self.revoked_at is None or now < self.revoked_at
        )


@dataclass(frozen=True, slots=True)
class AuthorizationBudget:
    """Upper bounds for one authorization lease.

    The runtime currently consumes ``max_steps``.  Cost accounting remains a
    gateway concern; an optional ``max_cost_micros`` is carried for a future
    ledger without granting additional authority.
    """

    max_steps: int = 1
    max_cost_micros: int | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("AuthorizationBudget.max_steps must be at least 1")
        if self.max_cost_micros is not None and self.max_cost_micros < 0:
            raise ValueError("AuthorizationBudget.max_cost_micros must not be negative")


@dataclass(frozen=True, slots=True)
class AgentTask:
    """A single provider-neutral generation task submitted to an agent."""

    request_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    use_case: str
    context_snapshot_ref: str
    prompt_version: str
    schema_version: str
    data_class: DataClass
    payload: dict[str, Any]
    output_schema: dict[str, Any]
    prompt_ref: str | None = None
    schema_ref: str | None = None
    input_refs: tuple[str, ...] = ()
    requested_tools: frozenset[str] = field(default_factory=frozenset)
    estimated_steps: int = 1

    def __post_init__(self) -> None:
        if not all(
            (
                self.request_id,
                self.agent_id,
                self.tenant_id,
                self.family_id,
                self.use_case,
                self.context_snapshot_ref,
                self.prompt_version,
                self.schema_version,
            )
        ):
            raise ValueError("AgentTask identity, use_case and request metadata are required")
        if not self.output_schema:
            raise ValueError("AgentTask.output_schema is required")
        if not isinstance(self.input_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip() for ref in self.input_refs
        ):
            raise ValueError("AgentTask.input_refs must be an immutable tuple of non-empty refs")
        if self.estimated_steps < 1:
            raise ValueError("AgentTask.estimated_steps must be at least 1")


class AgentExecutionPort(Protocol):
    """The only execution dependency of Agent Runtime.

    Model Gateway implements this protocol.  Keeping it structural prevents
    agents from importing a provider SDK or constructing a provider adapter.
    """

    async def generate_structured(self, request: StructuredRequest) -> ModelDraft:
        ...


# Descriptive alias retained for callers that want to emphasize the gateway's
# structured-generation contract rather than the Agent Runtime boundary.
StructuredGenerationPort = AgentExecutionPort


@dataclass(frozen=True, slots=True)
class AgentRun:
    """An immutable execution result; it is not a business fact."""

    run_id: str
    request_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    use_case: str
    draft: ModelDraft
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def may_mutate_business_state(self) -> bool:
        return False

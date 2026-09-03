"""Fail-closed, provider-neutral Prompt Registry."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from .contracts import PromptBundle, PromptStatus


class PromptRegistryError(RuntimeError):
    """Base error for prompt lookup and lifecycle violations."""


class PromptNotFound(PromptRegistryError):
    """Raised when no effective, correctly bound prompt exists."""


class PromptAlreadyRegistered(PromptRegistryError):
    """Raised when a version identity is registered twice."""


class PromptBindingError(PromptRegistryError):
    """Raised when use-case/agent binding is missing or ambiguous."""


class PromptRegistry:
    """An in-memory first adapter with durable-registry semantics.

    The adapter is deliberately small, but it preserves the semantics a SQL
    implementation must keep: immutable version identities, explicit lifecycle
    transitions, effective-time filtering and fail-closed binding checks.
    """

    _TRANSITIONS: dict[PromptStatus, frozenset[PromptStatus]] = {
        "DRAFT": frozenset({"REVIEW", "RETIRED"}),
        "REVIEW": frozenset({"PUBLISHED", "RETIRED"}),
        "PUBLISHED": frozenset({"RETIRED"}),
        "RETIRED": frozenset(),
    }

    def __init__(self, *, bundles: tuple[PromptBundle, ...] = ()) -> None:
        self._bundles: dict[tuple[str, str], PromptBundle] = {}
        self._superseded: set[tuple[str, str]] = set()
        for bundle in bundles:
            self.register(bundle)

    def register(self, bundle: PromptBundle) -> PromptBundle:
        key = (bundle.prompt_ref, bundle.version)
        if key in self._bundles:
            raise PromptAlreadyRegistered(
                f"PROMPT_ALREADY_REGISTERED:{bundle.prompt_ref}:{bundle.version}"
            )
        self._bundles[key] = bundle
        return bundle

    def get(self, prompt_ref: str, version: str) -> PromptBundle | None:
        return self._bundles.get((prompt_ref, version))

    def transition(
        self,
        prompt_ref: str,
        version: str,
        status: PromptStatus,
        *,
        effective_at: datetime | None = None,
        retired_at: datetime | None = None,
        reviewer: str | None = None,
        change_reason: str = "",
    ) -> PromptBundle:
        """Create and register a new immutable lifecycle snapshot.

        The original object remains in the registry under its version identity;
        lifecycle transitions therefore never silently rewrite an audit record.
        A transition receives a new version (for example ``v1`` → ``v1.1``)
        rather than modifying ``v1`` in place.
        """

        current = self.get(prompt_ref, version)
        if current is None:
            raise PromptNotFound(f"PROMPT_NOT_FOUND:{prompt_ref}:{version}")
        if status not in self._TRANSITIONS[current.status]:
            raise PromptRegistryError(f"INVALID_PROMPT_TRANSITION:{current.status}->{status}")
        if status == "PUBLISHED" and effective_at is None:
            effective_at = datetime.now(UTC)
        new_version = f"{version}.{status.lower()}"
        while (prompt_ref, new_version) in self._bundles:
            new_version = f"{new_version}.1"
        updated = replace(
            current,
            version=new_version,
            status=status,
            effective_at=effective_at if effective_at is not None else current.effective_at,
            retired_at=retired_at,
            reviewer=reviewer if reviewer is not None else current.reviewer,
            change_reason=change_reason,
        )
        # A same version cannot be replaced.  Registering a new immutable
        # version preserves the old object for audit/replay while making it
        # ineligible for future effective lookup.
        self._superseded.add((prompt_ref, version))
        return self.register(updated)

    def find(
        self,
        use_case: str,
        agent_id: str,
        prompt_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> PromptBundle | None:
        """Best-effort lookup; no unbound or non-effective version is returned."""

        instant = at if at is not None else datetime.now(UTC)
        candidates = [
            bundle
            for bundle in self._bundles.values()
            if bundle.use_case == use_case
            and bundle.agent_id == agent_id
            and (prompt_ref is None or bundle.prompt_ref == prompt_ref)
            and (version is None or bundle.version == version)
            and (bundle.prompt_ref, bundle.version) not in self._superseded
            and bundle.effective_at_time(instant)
        ]
        if len(candidates) > 1:
            # Two effective versions would make provenance nondeterministic.
            raise PromptBindingError(
                f"AMBIGUOUS_EFFECTIVE_PROMPT:{use_case}:{agent_id}:{prompt_ref or '*'}"
            )
        return candidates[0] if candidates else None

    def resolve(
        self,
        use_case: str,
        agent_id: str,
        prompt_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> PromptBundle:
        """Resolve a prompt or fail closed with an explicit error."""

        if not use_case or not agent_id:
            raise PromptBindingError("PROMPT_BINDING_REQUIRED:use_case_and_agent_id")
        bundle = self.find(
            use_case=use_case,
            agent_id=agent_id,
            prompt_ref=prompt_ref,
            version=version,
            at=at,
        )
        if bundle is None:
            raise PromptNotFound(
                f"PROMPT_NOT_FOUND_OR_NOT_EFFECTIVE:{use_case}:{agent_id}:"
                f"{prompt_ref or '*'}:{version or '*'}"
            )
        return bundle

    resolve_prompt = resolve

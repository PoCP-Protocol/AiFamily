"""Feedback adapter for the vertical family-growth runtime."""

from __future__ import annotations

import inspect
from typing import Any

from backend.intelligence.experience.run_http import RunScope


class LedgerFeedbackPort:
    """Read feedback from the canonical Experience Ledger only."""

    def __init__(self, ledger: Any, scope_factory) -> None:  # noqa: ANN001
        self._ledger = ledger
        self._scope_factory = scope_factory

    async def latest(
        self, *, family_need_id: str, family_id: str | None = None
    ) -> tuple[str, ...]:
        scope = self._scope_factory(family_id or family_need_id)
        if inspect.isawaitable(scope):
            scope = await scope
        if not isinstance(scope, RunScope):
            raise ValueError("vertical feedback scope must be RunScope")
        value = self._ledger.feedback_refs(scope=scope, family_need_id=family_need_id)
        if inspect.isawaitable(value):
            value = await value
        return tuple(value)

    async def preferences(self, *, family_id: str, family_need_id: str) -> object | None:
        scope = self._scope_factory(family_id)
        if inspect.isawaitable(scope):
            scope = await scope
        if not isinstance(scope, RunScope):
            raise ValueError("vertical feedback scope must be RunScope")
        reader = getattr(self._ledger, "feedback_preferences", None)
        if not callable(reader):
            return None
        value = reader(scope=scope)
        if inspect.isawaitable(value):
            value = await value
        return value.to_prompt_context() if hasattr(value, "to_prompt_context") else value


class FamilyNeedOutcomeFeedbackPort:
    """Project confirmed FamilyNeed outcomes into bounded learning refs."""

    def __init__(self, repository: Any, scope_factory) -> None:  # noqa: ANN001
        self._repository = repository
        self._scope_factory = scope_factory

    async def latest(
        self, *, family_need_id: str, family_id: str | None = None
    ) -> tuple[str, ...]:
        scope = self._scope_factory(family_id or family_need_id)
        if inspect.isawaitable(scope):
            scope = await scope
        if not isinstance(scope, RunScope):
            raise ValueError("outcome feedback scope must be RunScope")
        outcomes = self._repository.get_outcomes_for_need(
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            need_id=family_need_id,
        )
        if inspect.isawaitable(outcomes):
            outcomes = await outcomes
        return tuple(
            f"outcome:{outcome.outcome_id}:{outcome.decision.value}" for outcome in outcomes
        )

    async def preferences(self, *, family_id: str, family_need_id: str) -> object | None:
        return None


class CombinedFeedbackPort:
    """Merge canonical Ledger feedback and confirmed FamilyNeed outcomes."""

    def __init__(self, *ports: Any) -> None:
        self._ports = tuple(port for port in ports if callable(getattr(port, "latest", None)))

    async def latest(
        self, *, family_need_id: str, family_id: str | None = None
    ) -> tuple[str, ...]:
        refs: list[str] = []
        for port in self._ports:
            try:
                value = port.latest(family_need_id=family_need_id, family_id=family_id)
            except TypeError:
                value = port.latest(family_need_id=family_need_id)
            refs.extend(await value if inspect.isawaitable(value) else value)
        return tuple(dict.fromkeys(refs))

    async def preferences(self, *, family_id: str, family_need_id: str) -> object | None:
        for port in self._ports:
            reader = getattr(port, "preferences", None)
            if callable(reader):
                value = reader(family_id=family_id, family_need_id=family_need_id)
                return await value if inspect.isawaitable(value) else value
        return None


__all__ = ["CombinedFeedbackPort", "FamilyNeedOutcomeFeedbackPort", "LedgerFeedbackPort"]

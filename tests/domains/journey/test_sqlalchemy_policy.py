from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.domains.journey.domain.errors import JourneyForbiddenError
from backend.domains.journey.infrastructure.sqlalchemy_policy import SqlAlchemyJourneyPolicy


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Connection:
    def __init__(self, results):
        self.results = list(results)
        self.statements: list[str] = []

    async def execute(self, statement, parameters):
        self.statements.append(str(statement))
        return self.results.pop(0)


async def test_creation_policy_requires_permission_consents_and_normal_route() -> None:
    connection = Connection(
        [
            Result([SimpleNamespace(ok=1)]),
            Result([SimpleNamespace(subject_person_id="child-1")]),
            Result([SimpleNamespace(purpose=value) for value in sorted({
                "SERVICE",
                "ASSESSMENT",
                "GROWTH_TRACKING",
            })]),
            Result([SimpleNamespace(severity="LOW", disposition="NORMAL")]),
            Result(),
            Result(),
        ]
    )
    policy = SqlAlchemyJourneyPolicy(connection)  # type: ignore[arg-type]
    await policy.assert_creation_preconditions("family-1", "onboarding-1", "actor-1")
    assert len(connection.statements) == 6
    assert any("growth_events" in statement for statement in connection.statements)
    assert any("intervention_episodes" in statement for statement in connection.statements)


async def test_creation_policy_fails_closed_when_one_consent_is_missing() -> None:
    connection = Connection(
        [
            Result([SimpleNamespace(ok=1)]),
            Result([SimpleNamespace(subject_person_id="child-1")]),
            Result(
                [
                    SimpleNamespace(purpose="ASSESSMENT"),
                    SimpleNamespace(purpose="GROWTH_TRACKING"),
                ]
            ),
        ]
    )
    policy = SqlAlchemyJourneyPolicy(connection)  # type: ignore[arg-type]
    with pytest.raises(JourneyForbiddenError, match="missing_required_consent:SERVICE"):
        await policy.assert_creation_preconditions("family-1", "onboarding-1", "actor-1")


async def test_creation_policy_rejects_non_normal_safety_route() -> None:
    connection = Connection(
        [
            Result([SimpleNamespace(ok=1)]),
            Result([SimpleNamespace(subject_person_id="child-1")]),
            Result([SimpleNamespace(purpose=value) for value in sorted({
                "SERVICE",
                "ASSESSMENT",
                "GROWTH_TRACKING",
            })]),
            Result([SimpleNamespace(severity="HIGH", disposition="ESCALATE")]),
        ]
    )
    policy = SqlAlchemyJourneyPolicy(connection)  # type: ignore[arg-type]
    with pytest.raises(JourneyForbiddenError, match="normal_safety_route_not_verified"):
        await policy.assert_creation_preconditions("family-1", "onboarding-1", "actor-1")


async def test_read_policy_denies_unknown_family_manager() -> None:
    policy = SqlAlchemyJourneyPolicy(Connection([Result()]))  # type: ignore[arg-type]
    with pytest.raises(JourneyForbiddenError, match="actor_has_family_manage_permission"):
        await policy.assert_can_read("family-1", "actor-1")

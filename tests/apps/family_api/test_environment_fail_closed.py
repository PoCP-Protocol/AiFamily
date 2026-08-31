"""Environment and OpenAPI gates for synthetic family_api wiring."""

from __future__ import annotations

import pytest

from backend.apps.family_api.dev_wiring import (
    ENV_VAR,
    current_environment,
    is_dev_environment,
)
from backend.apps.family_api.main import create_app
from backend.domains.service.api import dependencies as service_dependencies

SYNTHETIC_AUTH_PATHS = {
    "/auth/account-session",
    "/auth/me",
    "/auth/contexts",
    "/auth/session/revoke",
}


def _assert_no_synthetic_wiring() -> None:
    app = create_app()
    assert SYNTHETIC_AUTH_PATHS.isdisjoint(app.openapi()["paths"])
    assert service_dependencies.get_repository not in app.dependency_overrides
    assert service_dependencies.get_consent_query not in app.dependency_overrides
    assert service_dependencies.get_action_context not in app.dependency_overrides
    assert service_dependencies.get_actor_context not in app.dependency_overrides


def test_unset_environment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert current_environment() == "unset"
    assert is_dev_environment() is False
    _assert_no_synthetic_wiring()


@pytest.mark.parametrize("value", ["", "   ", "prod-eu", "invalid", "production"])
def test_blank_invalid_and_production_environments_fail_closed(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(ENV_VAR, value)

    assert is_dev_environment() is False
    _assert_no_synthetic_wiring()


@pytest.mark.parametrize("value", ["development", "dev", "test"])
def test_explicit_development_and_test_environments_mount_synthetic_wiring(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(ENV_VAR, value)

    app = create_app()
    assert is_dev_environment() is True
    assert SYNTHETIC_AUTH_PATHS.issubset(app.openapi()["paths"])
    assert service_dependencies.get_repository in app.dependency_overrides

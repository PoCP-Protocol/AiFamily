from __future__ import annotations

from datetime import timedelta

import pytest

from backend.workflow_worker.main import WorkflowWorkerSettings, main


def test_worker_settings_require_postgres_and_share_environment_across_stages(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://worker:test@localhost/db")
    monkeypatch.setenv("AIFAMILY_WORKER_CLAIM_OWNER", "workflow-worker:test-1")
    monkeypatch.setenv("AIFAMILY_WORKER_POLL_SECONDS", "0.5")
    monkeypatch.setenv("AIFAMILY_WORKER_BATCH_LIMIT", "25")
    monkeypatch.setenv("AIFAMILY_WORKER_MAX_POLLS", "7")
    monkeypatch.setenv("AIFAMILY_WORKER_DEGRADED_AFTER", "2")
    monkeypatch.setenv("AIFAMILY_WORKER_ACTIVITY_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("AIFAMILY_WORKER_HEALTH_HOST", "127.0.0.1")
    monkeypatch.setenv("AIFAMILY_WORKER_HEALTH_PORT", "9082")

    settings = WorkflowWorkerSettings.from_environment()

    assert settings.claim_owner == "workflow-worker:test-1"
    assert settings.poll_interval == timedelta(milliseconds=500)
    assert settings.batch_limit == 25
    assert settings.accepted_action_max_polls == 7
    assert settings.degraded_after_failed_cycles == 2
    assert settings.activity_timeout == timedelta(seconds=45)
    assert settings.health_host == "127.0.0.1"
    assert settings.health_port == 9082


def test_worker_settings_fail_closed_without_production_database(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    with pytest.raises(RuntimeError, match="requires_postgresql"):
        WorkflowWorkerSettings.from_environment()


def test_default_claim_owner_is_unique_per_process_instance(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://worker:test@localhost/db")
    monkeypatch.delenv("AIFAMILY_WORKER_CLAIM_OWNER", raising=False)

    first = WorkflowWorkerSettings.from_environment().claim_owner
    second = WorkflowWorkerSettings.from_environment().claim_owner

    assert first != second
    assert first.startswith("workflow-worker:")
    assert len(first) <= 128


def test_worker_settings_reject_non_positive_tuning(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://worker:test@localhost/db")
    monkeypatch.setenv("AIFAMILY_WORKER_BATCH_LIMIT", "0")
    with pytest.raises(RuntimeError, match="must_be_positive"):
        WorkflowWorkerSettings.from_environment()


def test_help_does_not_require_runtime_configuration(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as stopped:
        main(["--help"])
    assert stopped.value.code == 0

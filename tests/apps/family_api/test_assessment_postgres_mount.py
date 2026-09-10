from __future__ import annotations

import pytest
from fastapi import FastAPI

from backend.apps.family_api import main


def test_dev_explicit_postgres_installs_durable_assessment_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/aifamily")
    engine = object()
    session_factory = object()
    calls: list[tuple[object, object, object, object]] = []

    monkeypatch.setattr(main, "get_engine", lambda _url: engine)
    monkeypatch.setattr(main, "get_sessionmaker", lambda _url: session_factory)
    monkeypatch.setattr(
        main,
        "SqlAlchemyAssessmentIdentityResolver",
        lambda actual_engine, actual_factory: (actual_engine, actual_factory),
    )
    monkeypatch.setattr(
        main,
        "install_postgres_assessment_http_wiring",
        lambda app, *, engine, identity_resolver, interpretation_factory: calls.append(
            (app, engine, identity_resolver, interpretation_factory)
        ),
    )

    app = FastAPI()
    main._mount_postgres_assessment_persistence(app)

    assert calls == [
        (app, engine, (engine, session_factory), main.DeterministicInterpretationAdapter)
    ]


@pytest.mark.parametrize(
    ("environment", "database_url"),
    [("test", "sqlite+aiosqlite:///:memory:"), ("production", "postgresql://example/aifamily")],
)
def test_non_dev_postgres_or_non_postgres_skips_durable_assessment_seam(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    database_url: str,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", environment)
    monkeypatch.setenv("DATABASE_URL", database_url)
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(main, "install_postgres_assessment_http_wiring", fail_if_called)

    main._mount_postgres_assessment_persistence(FastAPI())

    assert called is False

"""Liveness and readiness endpoints.

`/health` answers "is the process up" — no I/O, always 200 once the app has
started.

`/ready` answers "can this process actually serve traffic" — it exercises a
real database round-trip via `SqlAlchemyUnitOfWork.ping()` so a broken
`DATABASE_URL` or unreachable Postgres shows up as a failing readiness
probe rather than a silently-broken app that reports healthy forever.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    try:
        async with SqlAlchemyUnitOfWork() as uow:
            reachable = await uow.ping()
    except Exception as exc:  # noqa: BLE001 — readiness probe must not leak a 500 traceback
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"database not reachable: {exc}",
        ) from exc

    if not reachable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database ping did not return the expected result",
        )
    return {"status": "ready"}

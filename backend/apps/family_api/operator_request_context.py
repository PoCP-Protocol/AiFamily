"""Shared request-bound bearer dependency for internal operator APIs."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status

from backend.intelligence.evaluation.operator_identity import OperatorIdentityError
from backend.intelligence.evaluation.request_operator_identity import (
    bind_operator_bearer,
    parse_bearer_authorization,
    reset_operator_bearer,
)


async def bind_operator_request_context(request: Request) -> AsyncIterator[None]:
    """Require and bind the caller bearer for one operator-only request."""

    try:
        bearer = parse_bearer_authorization(request.headers.get("authorization"))
    except OperatorIdentityError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="operator_authorization_required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    marker = bind_operator_bearer(bearer)
    try:
        yield None
    finally:
        reset_operator_bearer(marker)


__all__ = ["bind_operator_request_context"]
